from struct import unpack, calcsize
from gzip import open as gzopen, GzipFile
from io import BytesIO, SEEK_CUR
import logging

# PyDICOM read (might not be present)
from .external import dcmread


logger = logging.getLogger(__name__)

# Dicom data store in RS is in a gzipped format with multiple files stuck
# together.  There are some (seemingly) standard headers for the file data, and
# the format is contructed from what could be assessed.

# Unknown Header (01 00 00 00 00 FF FF FF FF ... 01 00 00 00)   |      27 Bytes
# UInt32:   Number of files in set = N                          |       4 Bytes
# 2 bytes?: Unknown Always 07 02                                |       2 Bytes
# For each image: (5 bytes)                                     |   N * 5 Bytes
#   09:         Unknown                                         |
#   UIint32:    Image number (starts at 2?)                     |
# For each Image:                                               |
#   0F:         Unknown                                         |       1 Byte
#   UInt32:     Image number                                    |       4 Bytes
#   UInt32:     Bytes in image = M                              |       4 Bytes
#   02:         Unknown (Always 02)                             |       1 Byte
#   xxx:        DICOM Data                                      |       M Bytes
#                                                               |             .


class DCM_IO(GzipFile):

    def __init__(self, *args, **kwargs):
        pass

    def __new__(cls, obj):
        if isinstance(obj, cls.__bases__[0]):
            obj.__class__ = cls
            return obj
        else:
            raise ValueError("Must be an instance "
                             "of {cls.__bases__[0].__name__}")

    def unpack_read(self, pack_str):
        pack_str = f"={pack_str}"
        n_bytes = calcsize(pack_str)
        logger.debug(f"Reading '{pack_str}' ({n_bytes} bytes)")
        return unpack(pack_str, self.read(n_bytes))

    def unpack_readrepeat(self, pack_str, count):
        fpackstr = pack_str * count
        return self.unpack_read(fpackstr)


def read_dataset(img_stack, dcm_number=0):
    """
    Read the DicomDataSet from the img_stack and returns a pydicom object
    containing the non-pixel data for image number <img_number>.
    """
    # TODO: Allow to search by SOP Instance UID
    try:
        dicoms = []
        with DCM_IO(gzopen(BytesIO(img_stack.DicomDataSet), 'rb')) as dcm_io:
            # Skip first 27 bytes of header (no idea what they are)
            header_bytes = dcm_io.read(27)
            logger.debug(f"Header from DicomDataSet: {header_bytes!r}")

            # FIXME: Should we check ohseven and ohtwo?
            n_dcms, ohseven, ohtwo = dcm_io.unpack_read("Lbb")
            logger.debug(f"{n_dcms = }")

            # Probably ignore this too?
            dcm_listing = dcm_io.unpack_readrepeat("bL", n_dcms)
            if dcm_listing is None:
                logger.debug("dcmlisting empty?")

            for i in range(dcm_number + 1 if dcm_number != -1 else n_dcms):
                # ???: For some reason, dcm_no starts at 2?
                ohf, dcm_no, dcm_size, ohtwo = dcm_io.unpack_read("bLLb")
                if ohf != 0x0f or ohtwo != 0x02:
                    pos = dcm_io.tell()
                    logger.warning(
                        f"Malformed data in image. {i}.\n"
                        f"Expected (0x0F DCM_NO DCM_SIZE, 0x02)\n"
                        f"Got: ({ohf:2X} {dcm_no} {dcm_size} {ohtwo:2X}\n"
                        f"At position: {pos} ({pos:2X})")
                    raise ValueError("Malformed data in image.")

                # MAGIC: Works if dcm_number is negative to capture all images.
                if dcm_number - i <= 0:
                    dcm_bytes = BytesIO(dcm_io.read(dcm_size))
                    dcm = dcmread(dcm_bytes)
                    dicoms.append(dcm)
                else:
                    dcm_io.seek(dcm_size, SEEK_CUR)
        return dicoms
    except Exception as e:
        logger.exception(e)
        return None
