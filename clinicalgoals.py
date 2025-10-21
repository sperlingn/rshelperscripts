import logging
from collections import defaultdict

from .external import CompositeAction, rs_hasattr

_logger = logging.getLogger(__name__)

_PARAM_MAPPING = {
    'GoalCriteria': 'GoalCriteria',
    'GoalType': 'Type',
    'AcceptanceLevel': 'AcceptanceLevel',
    'ParameterValue': 'ParameterValue',
    'IsComparativeGoal': 'IsComparativeGoal',
    'Priority': 'Priority'
}

_MINUSES = [m + s + 'TV' for m in ['-', ' - '] for s in 'PCG']


def params_from_fn(fn):
    params = {key: getattr(fn.PlanningGoal, _PARAM_MAPPING[key])
              for key in _PARAM_MAPPING
              if rs_hasattr(fn.PlanningGoal, _PARAM_MAPPING[key])}

    params['RoiName'] = fn.ForRegionOfInterest.Name

    return params


def get_minuses(structure_set):
    rois = structure_set.RoiGeometries.Keys
    return {k: v for k, v in
            {s: [ms for ms in rois if ms in [s+m for m in _MINUSES]]
             for s in rois}.items() if v}


def fns_to_dup(eval_fns, minuses_dict):
    fnmap = defaultdict(list)
    for fn in [fn for fn in eval_fns
               if fn.ForRegionOfInterest.Name in minuses_dict]:
        fnmap[fn.ForRegionOfInterest.Name].append(fn)
    # Reset to normal dict behavior by reverting default_factory from list
    fnmap.default_factory = None
    return fnmap


def add_minus_goals(plan):
    eval_setup = plan.TreatmentCourse.EvaluationSetup
    eval_fns = eval_setup.EvaluationFunctions
    structure_set = plan.GetTotalDoseStructureSet()

    rois_to_minuses_map = get_minuses(structure_set)

    rois_to_fn_map = fns_to_dup(eval_fns, rois_to_minuses_map)

    with CompositeAction("Add clinical goals for <X - [PCG]TV>"):
        for roi_name in rois_to_fn_map:
            for fn in rois_to_fn_map[roi_name]:
                fnparams = params_from_fn(fn)
                for roi_minus_name in rois_to_minuses_map[roi_name]:
                    fnparams['RoiName'] = roi_minus_name
                    eval_setup.AddClinicalGoal(**fnparams)


def copy_clinical_goal(goal_in, evalsetup_out):
    fnparams = params_from_fn(goal_in)

    print(f"{fnparams=}")
    _logger.debug(f"{fnparams=}")
    evalsetup_out.AddClinicalGoal(**fnparams)


def copy_clinical_goals(plan_in, plan_out):
    evalsetup_in = plan_in.TreatmentCourse.EvaluationSetup
    evalsetup_out = plan_out.TreatmentCourse.EvaluationSetup

    # Clear plan_out clinical goals
    existing_goals = [fn for fn in evalsetup_out.EvaluationFunctions]
    for fn in existing_goals:
        evalsetup_out.DeleteClinicalGoal(FunctionToRemove=fn)

    uniq_fns = [{k: v for (k, v) in unq_fn} for unq_fn in
                {frozenset(params_from_fn(fn).items())
                 for fn in evalsetup_in.EvaluationFunctions}]

    _logger.debug(f"Copying goals: {uniq_fns}")
    for fn_params in uniq_fns:
        evalsetup_out.AddClinicalGoal(**fn_params)


class ClinicalGoal():
    _fn = None
    evals = None
    # This will be much easier with template strings when we can move to
    # python 3.14...159265
    GoalCriteria = {'AtLeast': '>',
                    'AtMost': '<'}
    GoalStrings = {
        'AverageDose': '_Dmean {goaldir} {al}cGy: {value}cGy',
        'VolumeAtDose': '_V{pv}cGy {goaldir} {al:.2%}: {value:.2%}',
        'DoseAtVolume': '_D{pv:.0%} {goaldir} {al}cGy: {value}cGy',
        'DoseAtPoint': '_D {goaldir} {al}cGy: {value}cGy',
        'AbsoluteVolumeAtDose': '_V{pv}cGy {goaldir} {al}cc: {value}cc',
        'DoseAtAbsoluteVolume': '_D{pv}cc {goaldir} {al}cGy: {value}cGy',
        'ConformityIndex': '_CI {goaldir} {al}: {value}',
        'HomogeneityIndex': '_HI {goaldir} {al}: {value}'
    }

    # TODO: Add subscripting for an evaluation to allow a return of the string
    # of that (and add it to the eval list)

    def __init__(self, rs_dose_eval_fn, dose=None):
        self._fn = rs_dose_eval_fn
        self._gcgvfed = self._fn.GetClinicalGoalValueForEvaluationDose
        self.evals = {}

        if dose:
            self.eval_dose(dose)

    def eval_dose(self, dose, scaledose=False):
        eval_dose = self._gcgvfed(DoseDistribution=dose,
                                  ScaleFractionDoseToBeamSet=scaledose)
        self.evals[dose.Name] = eval_dose
        return eval_dose

    @property
    def name(self):
        if self._fn.ForRegionOfInterest:
            return self._fn.ForRegionOfInterest.Name
        elif self._fn.OfPoiGeometry:
            return self._fn.OfPoiGeometry.OfPoi.Name

    def __str__(self):
        # Do the pretty printing
        pg = self._fn.PlanningGoal
        params = {'pv': getattr(pg, 'ParameterValue', None),
                  'al': getattr(pg, 'AcceptanceLevel', None),
                  'goaldir': self.GoalCriteria[pg.GoalCriteria]}

        strs = {dosename: self.GoalStrings[pg.Type].format(value=val, **params)
                for dosename, val in self.evals.items()}

        if len(strs) == 1:
            return f'{self.name}{next(iter(strs.values()))}'
        else:
            return '\n'.join(f'{dn}: {self.name}{strs[dn]}' for dn in strs)
