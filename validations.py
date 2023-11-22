from .external import (Show_OK, Show_YesNo, MB_Icon, MB_Result,
                       CompositeAction, Show_Warning, obj_name)
from .case_comment_data import (set_validation_comment,
                                beamset_validation_checkraise)
from .collision_rois import check_collision
from .collision_dialog import check_collision_dialog
import logging
import sys
import inspect

_logger = logging.getLogger(__name__)

JAW_LIMIT = 0.5

JAW_VALIDATION_STR = 'Jaw'
COLLISION_VALIDATION_STR = 'Collision'


class SegmentViolation:
    seg = None
    violations = None
    _VIOLATION_TYPES = ['Jaw', 'MLC']

    def __init__(self, seg, violations):
        self.seg = seg
        self.violations = {t: False for t in self._VIOLATION_TYPES}
        self.add_violation(violations)

    def set_violations(self, violation_type, status=True, clear=True):
        new_violations = f'{violation_type}'.lower()
        for t in self._VIOLATION_TYPES:
            if t.lower() in new_violations:
                self.violations[t] = bool(status)
            elif clear:
                self.violations[t] = False

    def add_violation(self, violation_type):
        self.set_violations(violation_type, clear=False)

    def remove_violation(self, violation_type):
        self.set_violations(violation_type, status=False, clear=False)

    def __str__(self):
        return f'{self.seg.SegmentNumber+1}'

    def fix_jaw(self):
        if self.violations['Jaw']:
            gap_x = JAW_LIMIT - (self.seg.JawPositions[1]
                                 - self.seg.JawPositions[0])
            gap_y = JAW_LIMIT - (self.seg.JawPositions[3]
                                 - self.seg.JawPositions[2])
            jp = [j for j in self.seg.JawPositions]
            if gap_x > 0:
                jp[0] -= gap_x / 2
                jp[1] += gap_x / 2

            if gap_y > 0:
                jp[2] -= gap_y / 2
                jp[3] += gap_y / 2

            self.seg.JawPositions = jp

            self.remove_violation('jaw')

    def fix_violations(self):
        if self.violations['Jaw']:
            self.fix_jaw()
        if self.violations['MLC']:
            self.fix_mlc()

    def fix_mlc(self):
        raise NotImplementedError

    def __bool__(self):
        return any(self.violations.values())


class ViolationDict(dict):
    def add_violation(self, beam, segment, violation_type):
        if beam not in self:
            self[beam] = {}

        if segment in self[beam]:
            self[beam][segment].add_violation(violation_type)
        else:
            self[beam][segment] = SegmentViolation(segment, violation_type)

    def __str__(self):
        return '\n'.join(['Violation: Beam [{}]: CP [{}]'.format(
            obj_name(beam), ', '.join([f'{s}' for s in segments.values()]))
            for beam, segments in self.items()])

    def __bool__(self):
        if len(self) > 0:
            # Might not actually have violations, check all.
            return any([self[b][v] for b in self for v in self[b]])

        return False

    def fix_violations(self):
        with CompositeAction(f"Fixing Violations ({self})"):
            for beam in self:
                for segment in self[beam]:
                    self[beam][segment].fix_violations()


def check_jaw(beam_set):
    violations = ViolationDict()
    for beam in beam_set.Beams:
        for seg in beam.Segments:
            if min(abs(seg.JawPositions[0] - seg.JawPositions[1]),
                   abs(seg.JawPositions[2] - seg.JawPositions[3])) < JAW_LIMIT:
                violations.add_violation(beam, seg, 'Jaw')

    return violations


def fix_jaw(beam_set):
    with CompositeAction('Fix Jaw Gap'):
        for beam in beam_set.Beams:
            for seg in beam.Segments:
                gap_x = JAW_LIMIT - (seg.JawPositions[1] - seg.JawPositions[0])
                gap_y = JAW_LIMIT - (seg.JawPositions[3] - seg.JawPositions[2])
                jp = [j for j in seg.JawPositions]
                if gap_x > 0:
                    jp[0] -= gap_x / 2
                    jp[1] += gap_x / 2

                if gap_y > 0:
                    jp[2] -= gap_y / 2
                    jp[3] += gap_y / 2

                seg.JawPositions = jp


def validate_jaw(plan, beam_set, silent=False, fix_errors=False):
    beamset_validation_checkraise(beam_set)
    errorlist = check_jaw(beam_set)
    if not silent:
        if not errorlist:
            Show_OK("No collisions.", "Jaw collision status", ontop=True)
        else:
            outtext = ('Failed Jaw validation on the following CPs: '
                       f'{errorlist}\n')

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
        errorlist.fix_violations()
        set_validation_comment(plan, beam_set, JAW_VALIDATION_STR)
    else:
        _logger.debug("Didn't fix, so remove Jaw passing if it is here.")
        set_validation_comment(plan, beam_set, JAW_VALIDATION_STR, False)


def validate_collision(plan, beam_set, silent=False):
    try:
        beamset_validation_checkraise(beam_set)
        can_update_comment = True
    except UserWarning as warn:
        if silent:
            raise warn
        else:
            can_update_comment = False

    if silent:
        status = check_collision(plan, beam_set, silent=True,
                                 retain=False, retain_on_fail=False)
    else:
        status = check_collision_dialog(plan, beam_set)

    if status['UpdateComment'] and can_update_comment:
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

    try:
        for name, validation_fn in validations.items():
            _logger.info(f'Running {name}.')
            for beam_set_loop in beam_sets:
                validation_fn(plan, beam_set_loop, silent)
    except UserWarning as warn:
        _logger.warning(f"Failed to check {beam_set_loop} in {plan}",
                        exc_info=True)
        Show_Warning(f"{warn}", "Can't Validate beamset.")
