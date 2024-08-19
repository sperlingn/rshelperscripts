from pickle import dumps, loads
from lzma import compress, decompress, LZMAError
from base64 import b64encode, b64decode
import re
import logging

from .external import CompositeAction, obj_name

_logger = logging.getLogger(__name__)
# Based on:
# dicom.nema.org/medical/dicom/current/output/chtml/part05/chapter_9.html
UID_RE = re.compile(r'(0|[1-9][0-9]*)(\.(0|[1-9][0-9]*))*')


def filter_lines(lines, re=UID_RE):
    # Returns lines matching re and those that don't.

    return ([line for line in lines if re.match(line)],
            [line for line in lines if not re.match(line)])


def beamset_validation_checkraise(beam_set):
    if not beamset_validation_check(beam_set):
        raise UserWarning("Can't set comment, beamset is not yet saved.")


def beamset_validation_check(beam_set):
    return (beam_set.ModificationInfo and beam_set.ModificationInfo.DicomUID)


def set_validation_comment(plan, beam_set, validation_type, status=True):
    # beamset_validation_checkraise(beam_set)

    try:
        existing = plan.Comments.split('\n')
    except (TypeError, AttributeError):
        existing = []

    uid_lines, str_lines = filter_lines(existing)

    # Check for existance of a Validated line.
    plan_uids = {bs.ModificationInfo.DicomUID for bs in plan.BeamSets
                 if bs.ModificationInfo}

    # Get current list of UIDs from validation_line
    # Current format for validation: "<UID>: <Type>[, <Type>...]"
    validated_uids = {line.split(':')[0].strip():
                      set(map(str.strip, line.split(':')[1].split(',')))
                      for line in uid_lines}

    # Only append those lines that are valid in the current plan
    # This should catch when plans change and have already been validated
    for uid in set(validated_uids) - plan_uids:
        del validated_uids[uid]

    if beamset_validation_check(beam_set):
        this_uid = beam_set.ModificationInfo.DicomUID

        if status:
            try:
                validated_uids[this_uid].add(validation_type)
            except (AttributeError, ValueError, TypeError, KeyError):
                validated_uids[this_uid] = {validation_type}
        elif (this_uid in validated_uids and
              validation_type in validated_uids[this_uid]):
            validated_uids[this_uid].discard(validation_type)

    lines = [line.strip() for line in str_lines if line.strip()]

    for uid in validated_uids:
        validations = ', '.join(sorted(validated_uids[uid]))
        lines.append(f"{uid}: {validations}")

    _logger.debug(f"Set plan.Comments to {lines}")

    action_name = "Added " if status else "Removed "
    action_name += (f"validation note for '{validation_type}' "
                    f"in plan comment for plan [{obj_name(plan)}]")
    with CompositeAction(action_name):
        plan.Comments = '\n'.join(lines)


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
    data = get_data(icase.Comments, first)
    _logger.debug("{data=}")
    return data


def set_case_comment_data(icase, data, name='', replace=True):
    """
    Store the data in the case.Comments as a base64 string.
    """
    comment_str = icase.Comments

    new_comment = build_data_str(comment_str, data, name, replace)

    _logger.debug(f"setting '{name}': '{data}'")

    try:
        with CompositeAction("Updating Case Comment String with encoded data"):
            icase.Comments = new_comment
    except Exception as e:
        _logger.warning(str(e), exc_info=True)
