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


def get_data(text, first=False):
    """
    Pulls pickled data in the string field.  If first is True, stops after the
    first successful unpickling.
    Will also split data along spaces and tabs, as both are disallowed in
    base64 and may be needed for single line fields.
    """
    odata = {}
    try:
        for line in text.split():
            data = loads_64(line)
            if data:
                if first:
                    return data
                else:
                    odata.update(data)
    except Exception as e:
        _logger.info(str(e), exc_info=True)

    return odata


def build_data_str(existing_text='', data=None, name='', replace=True):
    if isinstance(existing_text, str):
        existing_text = existing_text.splitlines()
    elif isinstance(existing_text, list) or isinstance(existing_text, tuple):
        existing_text = list(*existing_text)
    else:
        existing_text = []

    o_str = []
    if isinstance(data, dict) and not name:
        odict = dict(data)
    else:
        odict = {name: data}

    if replace:
        existing_dict = {}
        for line in existing_text:
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
        o_str = existing_text

    o_str.append(dumps_64(odict))

    return '\n'.join(o_str)


def get_case_comment_data(icase, first=False):
    """
    Pulls first pickled data in the case comment field.
    """
    return get_data(icase.Comments, first)


def set_case_comment_data(icase, data, name='', replace=True):
    """
    Store the data in the case.Comments as a base64 string.
    """
    comment_str = icase.Comments

    new_comment = build_data_str(comment_str, data, name, replace)

    try:
        with CompositeAction("Updating Case Comment String with encoded data"):
            icase.Comments = new_comment
    except Exception as e:
        _logger.warning(str(e), exc_info=True)
