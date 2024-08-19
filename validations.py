from .external import (Show_OK, Show_YesNo, MB_Icon, MB_Result, get_current,
                       CompositeAction, Show_Warning, obj_name)
from .case_comment_data import (set_validation_comment,
                                beamset_validation_check)
from .collision_rois import check_collision
from .collision_dialog import check_collision_dialog
from .couchtop import CouchTopCollection
import logging
import sys
import inspect
from collections import defaultdict

_logger = logging.getLogger(__name__)

JAW_LIMIT = 0.5

JAW_KEY = 'Jaw'
COLLISION_KEY = 'Collision'
COUCH_KEY = 'Couchtop'


class ValidationResult:
    _passes = None
    violation = None
    message = ""
    key = ""
    fixed = False
    update_comment = True

    def __init__(self, passes=None, violation=None, message=None, key='Unk',
                 update_comment=True):
        self._passes = passes
        self.violation = violation
        self.key = key
        self.update_comment = update_comment
        self.message = str(message if message is not None else violation)

    @property
    def passes(self):
        return bool(self._passes if self._passes is not None
                    else not self.violation)

    def __bool__(self):
        return bool(self.passes)

    def __str__(self):
        if self.fixed:
            return f'{self.message} (Corrected)'
        else:
            return self.message

    def __repr__(self):
        return (f'{self.__class__.__name__}('
                f'passes={self._passes}, '
                f'violation="{self.violation}", '
                f'message="{self.message}", '
                f'key={self.key}, '
                f'update_comment={self.update_comment})')


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


class ViolationDict(defaultdict):
    violations_by_type = None

    def __init__(self, *args, **kwargs):
        super().__init__(dict, *args, **kwargs)

        self.violations_by_type = defaultdict(lambda: defaultdict(list))

    def add_violation(self, beam, segment, violation_type):
        if beam not in self:
            self[beam] = {}

        if segment in self[beam]:
            self[beam][segment].add_violation(violation_type)
        else:
            self[beam][segment] = SegmentViolation(segment, violation_type)

        self.violations_by_type[violation_type][beam].append(
            str(segment.SegmentNumber+1))

    def __str__(self):
        return '\n'.join(['{} Violation for Beam [{}]: CPs [{}]'.format(
            violation_type,
            obj_name(beam),
            ','.join(segments))
            for violation_type, beams in self.violations_by_type.items()
            for beam, segments in beams.items()])
        return '\n'.join(['Violations: Beam [{}]: CP [{}]'.format(
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
        errorlist = check_jaw(beam_set)
        errorlist.fix_violations()
    return errorlist


def validate_jaw(plan, beam_set, silent=False, fix_errors=False):
    errorlist = check_jaw(beam_set)
    validation = ValidationResult(violation=errorlist, key=JAW_KEY)
    if not silent:
        if validation:
            Show_OK("No collisions.", "Jaw collision status", ontop=True)
        else:
            outtext = ('Failed Jaw validation on the following CPs: '
                       f'{validation}\n')

            if fix_errors:
                outtext += '\nFixing jaw gaps.'
                Show_OK(outtext, 'Jaw collision status',
                        ontop=True, icon=MB_Icon.Error)
            else:
                outtext += '\nDo you wish to fix these?'
                response = Show_YesNo(outtext, 'Jaw collision status',
                                      ontop=True, icon=MB_Icon.Error)
                fix_errors = response == MB_Result.Yes

    if validation:
        pass
    elif fix_errors:
        errorlist.fix_violations()
        validation.fixed = True

        # Won't be able to set the comment without a save before hand, but
        # likely shouldn't save without user review.  At least we should
        # indicate that the violation has been repaired.

        validation.update_comment = False
    else:
        _logger.debug("Didn't fix, so remove Jaw passing if it is here.")

    return validation


def validate_collision(plan, beam_set, silent=False):
    can_update_comment = beamset_validation_check(beam_set)

    if silent:
        coll_result = check_collision(plan, beam_set, silent=True,
                                      retain=False, retain_on_fail=False)
    else:
        coll_result = check_collision_dialog(plan, beam_set)

    update_comment = can_update_comment and coll_result['UpdateComment']

    return ValidationResult(passes=not coll_result['status'],
                            violation=coll_result,
                            message=coll_result['overlaps'],
                            key=COLLISION_KEY,
                            update_comment=update_comment)


def validate_couch(plan, beam_set, silent=False, icase=None):
    key = COUCH_KEY
    cp = beam_set.PatientSetup.CollisionProperties
    structure_set = cp.ForExaminationStructureSet
    machine = beam_set.MachineReference.MachineName

    icase = icase if icase is not None else get_current('Case')

    try:
        tops = CouchTopCollection(structure_set=structure_set,
                                  use_known=True)
        expected_top = tops.determine_top(machine=machine, icase=icase)

        built_tops = tops.built_tops

        if not expected_top.isBuilt:
            violation = (f'Expected top {expected_top.Name} is not present.\n'
                         f'Status:\n'
                         f'\tRois present: {expected_top.isPresent}\n'
                         f'\tRois built: {expected_top.isBuilt}')
        elif len(built_tops) != 1:
            violation = f'Too many tops in plan.  Found {len(built_tops)}:\n'
            violation += '\n'.join([f'{top.Name}' for top in built_tops])
        else:
            violation = None
    except Exception as e:
        violation = f'Had exception in couch identification:\n{e}'

    return ValidationResult(violation=violation, key=key)


def run_all_validations(plan, beam_set=None, silent=False, show_on_fail=True):
    # Runs all validations currently in the scope of the file.
    validations = {name: obj for name, obj
                   in inspect.getmembers(sys.modules[__name__])
                   if (inspect.isfunction(obj) and name[0:9] == 'validate_')}

    # If we aren't given a beam_set, do it for all of the beamsets in the plan.
    if beam_set:
        beam_sets = [beam_set]
    else:
        beam_sets = [bs for bs in plan.BeamSets]

    fails = []
    not_updatable = defaultdict(list)
    try:
        for name, validation_fn in validations.items():
            _logger.info(f'Running {name}.')
            for bs_iter in beam_sets:
                status = validation_fn(plan, bs_iter, silent)
                if not status:
                    fails.append(status)

                _logger.info(f'Updating validation status of {status.key}'
                             f' for plan [{obj_name(plan)}] to {status}.')
                set_validation_comment(plan, bs_iter, status.key, bool(status))
                if not beamset_validation_check(bs_iter):
                    _logger.info(f'beamset {obj_name(bs_iter)} is not saved,'
                                 f' cannot update comment key.')
                    ident = f'{obj_name(plan)} -- {obj_name(bs_iter)}'
                    not_updatable[ident].append(status)

    except UserWarning as warn:
        _logger.warning(f"Failed to check {bs_iter} in {plan}",
                        exc_info=True)
        Show_Warning(f"{warn}", "Can't Validate beamset.")

    if silent and show_on_fail:
        # Silent, but still show message box on failure.
        if fails:
            _logger.debug(f"{fails=}")
            message = (f'Failed to validate plan "{obj_name(plan)}".\n'
                       'Encountered the following failures:\n\n')
            message += '\n'.join([f'{f!s}' for f in fails])
            Show_Warning(caption="Failed Validation", message=message)

        if not_updatable:
            message = 'Could not set comment on the following beamsets:\n\n'
            message += '\n'.join([(f' {ident} -- ' +
                                   ', '.join([f'{status.key}' for status
                                              in statuses if status]))
                                  for ident, statuses
                                  in not_updatable.items()])
            Show_Warning(caption="Failed update", message=message)
