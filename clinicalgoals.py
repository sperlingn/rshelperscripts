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
