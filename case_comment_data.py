from pickle import dumps, loads
from lzma import compress, decompress, LZMAError
from base64 import b64encode, b64decode
import logging

from .external import CompositeAction

_logger = logging.getLogger(__name__)


def dumps_64(obj):
    try:
        return b64encode(compress(dumps(obj))).decode('utf-8')
    except Exception as e:
        _logger.info(str(e), exc_info=True)
        return None


def loads_64(instr):
    try:
        return loads(decompress(b64decode(instr)))
    except (LZMAError, ValueError, TypeError):
        pass
    except Exception as e:
        _logger.exception(e)

    return None


def get_case_comment_data(icase, first=False):
    """
    Pulls first pickled data in the case comment field.
    """
    odata = {}
    try:
        for line in icase.Comments.splitlines():
            data = loads_64(line)
            if data:
                if first:
                    return data
                else:
                    odata.update(data)
    except Exception as e:
        _logger.info(str(e), exc_info=True)

    return odata


def set_case_comment_data(icase, data, name='', replace=True):
    comment_str = icase.Comments.splitlines()
    o_str = []
    if isinstance(data, dict) and not name:
        odict = dict(data)
    else:
        odict = {name: data}

    if replace:
        existing_dict = {}
        for line in comment_str:
            existingdata = loads_64(line)
            if existingdata:
                if isinstance(existingdata, dict):
                    existing_dict.update(existingdata)
                else:
                    _logger.warning("Data in comment string wasn't a dict. "
                                    f"Dropping from stream. ({existingdata})")
            else:
                o_str.append(line)
        existing_dict.update(odict)
        odict = existing_dict
    else:
        o_str = comment_str

    o_str.append(dumps_64(odict))

    try:
        with CompositeAction("Updating Case Comment String with encoded data"):
            icase.Comments = '\n'.join(o_str)
    except Exception as e:
        _logger.warning(str(e), exc_info=True)
