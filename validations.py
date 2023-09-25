from .external import Show_OK, Show_YesNo, MB_Icon, MB_Result, CompositeAction
from .case_comment_data import set_validation_comment
from .collision_rois import check_collision
from .collision_dialog import check_collision_dialog
import logging
import sys
import inspect

_logger = logging.getLogger(__name__)

JAW_LIMIT = 0.5

JAW_VALIDATION_STR = 'Jaw'
COLLISION_VALIDATION_STR = 'Collision'


def check_jaw(beam_set):
    violations = {}
    for beam in beam_set.Beams:
        for seg in beam.Segments:
            if abs(seg.JawPositions[0] - seg.JawPositions[1]) < JAW_LIMIT:
                if beam.Name not in violations:
                    violations[beam.Name] = []
                violations[beam.Name].append(f'{seg.SegmentNumber+1}')

    output = ['Violation: Beam [{}]: CP [{}]'.format(beam, ', '.join(segments))
              for beam, segments in violations.items()]

    return output


def fix_jaw(beam_set):
    with CompositeAction('Fix Jaw Gap'):
        for beam in beam_set.Beams:
            for seg in beam.Segments:
                gap_d = JAW_LIMIT - (seg.JawPositions[1] - seg.JawPositions[0])
                if gap_d > 0:
                    jp = (seg.JawPositions[0] - (gap_d/2),
                          seg.JawPositions[0] + (gap_d/2),
                          seg.JawPositions[2], seg.JawPositions[3])
                    seg.JawPositions = jp


def validate_jaw(plan, beam_set, silent=False, fix_errors=False):
    errorlist = check_jaw(beam_set)
    if not silent:
        if not errorlist:
            Show_OK("No collisions.", "Jaw collision status", ontop=True)
        else:
            outtext = 'Failed Jaw validation on the following CPs:\n'
            outtext += '\n'.join(errorlist)

            if fix_errors:
                outtext += '\nFixing jaw gaps.'
                Show_OK(outtext, 'Jaw collision status',
                        ontop=True, icon=MB_Icon.Error)
            else:
                outtext += '\nDo you wish to fix these?'
                response = Show_YesNo(outtext, 'Jaw collision status',
                                      ontop=True, icon=MB_Icon.Error)
                fix_errors = response == MB_Result.Yes

    if not errorlist:
        set_validation_comment(plan, beam_set, JAW_VALIDATION_STR)
    elif fix_errors:
        fix_jaw(beam_set)
        set_validation_comment(plan, beam_set, JAW_VALIDATION_STR)
    else:
        # Didn't fix, so remove Jaw passing if it is here.
        set_validation_comment(plan, beam_set, JAW_VALIDATION_STR, False)


def validate_collision(plan, beam_set, silent=False):
    if silent:
        status = check_collision(plan, beam_set, silent=True,
                                 retain=False, retain_on_fail=False)
    else:
        status = check_collision_dialog(plan, beam_set)

    if status['UpdateComment']:
        status = status['status']
        _logger.info(f"Updating validation status for plan to {status}.")
        set_validation_comment(plan, beam_set,
                               COLLISION_VALIDATION_STR, status)


def run_all_validations(plan, beam_set=None, silent=False):
    # Runs all validations currently in the scope of the file.
    validations = {name: obj for name, obj
                   in inspect.getmembers(sys.modules[__name__])
                   if (inspect.isfunction(obj) and name[0:9] == 'validate_')}

    # If we aren't given a beam_set, do it for all of the beamsets in the plan.
    if beam_set:
        beam_sets = [beam_set]
    else:
        beam_sets = [bs for bs in plan.BeamSets]

    for name, validation_fn in validations.items():
        _logger.info(f'Running {name}.')
        for beam_set_loop in beam_sets:
            validation_fn(plan, beam_set_loop, silent)
