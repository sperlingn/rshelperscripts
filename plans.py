import logging
from .clinicalgoals import copy_clinical_goals
from .external import (CompositeAction as _CompositeAction,
                       rs_getattr as _rs_getattr,
                       rs_hasattr as _rs_hasattr,
                       obj_name as _obj_name)
from .examinations import duplicate_exam as _duplicate_exam
# from .points import point as _point

import copy

_logger = logging.getLogger(__name__)


DUP_MAX_RECURSE = 10


class CallLaterList():
    _fn_list = {}  # Class level list

    def _def_fn(self, *args, **kwargs):
        raise NotImplementedError("Must be initialised first.")

    def __getattr__(self, fn):
        if fn not in self._fn_list:
            self._fn_list[fn] = CallLater()
        return self._fn_list[fn]

    def __call__(self, fn):
        fnname = fn.__name__
        myfn = self.__getattr__(fnname)
        myfn.set_fn(fn)
        return myfn


class CallLater():
    _myfn = None

    def __call__(self, *args, **kwargs):
        return self._myfn(*args, **kwargs)

    def set_fn(self, fn):
        self._myfn = fn


cll = CallLaterList()

_PLAN_PARAM_MAPPING = {
    'PlannedBy': True,
    'Comment': True
}

_PLAN_PARAM_DEFAULT = {
    'PlanName': None,
    'ExaminationName': None,
    'IsMedicalOncologyPlan': False,
    'AllowDuplicateNames': False
}

_BS_PARAM_MAPPING = {
    'Name': 'DicomPlanLabel',
    'ExaminationName': None,  # Needs to be set from new plan
    'MachineName': 'MachineReference.MachineName',
    'Modality': True,
    'TreatmentTechnique': cll.get_technique_from_beamset,
    'PatientPosition': True,
    'NumberOfFractions': 'FractionationPattern.NumberOfFractions',
    'CreateSetupBeams': 'PatientSetup.UseSetupBeams',
    'UseLocalizationPointAsSetupIsocenter': None,
    'UseUserSelectedIsocenterSetupIsocenter': None,
    'Comment': True,
    'RbeModelName': None,
    'EnableDynamicTrackingForVero': None,
    'NewDoseSpecificationPointNames': None,
    'NewDoseSpecificationPoints': None,
    'MotionSynchronizationTechniqueSettings': None,
    'Custom': None,
    'ToleranceTableLabel': None
}

_BS_PARAM_DEFAULT = {
    'ExaminationName': '',  # Needs to be set from new plan
    'UseLocalizationPointAsSetupIsocenter': False,
    'UseUserSelectedIsocenterSetupIsocenter': False,
    'RbeModelName': None,
    'NewDoseSpecificationPointNames': [],
    'NewDoseSpecificationPoints': [],
    'MotionSynchronizationTechniqueSettings': None,
    'Custom': None,
    'ToleranceTableLabel': None
}


_RX_POI_PARAM_MAPPING = {
    'PoiName': 'OnStructure.Name',
    'DoseValue': True,
    'RelativePrescriptionLevel': True}
_RX_ROI_PARAM_MAPPING = {
    'RoiName': 'OnStructure.Name',
    'DoseVolume': True,
    'PrescriptionType': True,
    'DoseValue': True,
    'RelativePrescriptionLevel': True}
_RX_SITE_PARAM_MAPPING = {
    'Description': True,
    'NameOfDoseSpecificationPoint': 'OnDoseSpecificationPoint.Name',
    'DoseValue': True,
    'RelativePrescriptionLevel': True}

_RX_TYPES_SET = {
    'AverageDose',
    'DoseAtVolume',
    'MedianDose',
    'NearMaximumDose',
    'NearMinimumDose'}

_TECHNIQUES_SET = {
    'Conformal',
    'SMLC',
    'VMAT',
    'DMLC',
    'StaticArc',
    'ConformalArc',
    'TomoHelical',
    'TomoDirect',
    'CyberKnife',
    'ProtonPencilBeamScanning',
    'LineScanning',
    'UniformScanning',
    'Wobbling',
    'SingleScattering',
    'DoubleScattering',
    'ApplicatorAndCutout',
    'CarbonPencilBeamScanning',
    'BNCT'
}

_BEAM_PHOTON_STATIC_PARAM_MAPPING = {
    'BeamQualityId': True,
    'CyberKnifeCollimationType': None,
    'CyberKnifeNodeSetName': None,
    'CyberKnifeRampVersion': None,
    'CyberKnifeAllowIncreasedPitchCorrection': None,
    'IsocenterData': cll.get_iso_from_beam,
    'Name': True,
    'Description': True,
    'GantryAngle': True,
    'CouchRotationAngle': True,
    'CouchPitchAngle': True,
    'CouchRollAngle': True,
    'CollimatorAngle': 'InitialCollimatorAngle'
}

_BEAM_PHOTON_STATIC_DEFAULT = {
    'CyberKnifeCollimationType': None,
    'CyberKnifeNodeSetName': None,
    'CyberKnifeRampVersion': None,
    'CyberKnifeAllowIncreasedPitchCorrection': None
}

_BEAM_PHOTON_ARC_PARAM_MAPPING = {
    'ArcStopGantryAngle': True,
    'ArcRotationDirection': True,
    'BeamQualityId': True,
    'IsocenterData': cll.get_iso_from_beam,
    'Name': True,
    'Description': True,
    'GantryAngle': True,
    'CouchRotationAngle': True,
    'CouchPitchAngle': True,
    'CouchRollAngle': True,
    'CollimatorAngle': 'InitialCollimatorAngle'
}

_BEAM_PHOTON_ARC_DEFAULT = {
}


_ISOCENTER_PARAM_MAPPING = {
    'Position': True,
    'Name': 'Annotation.Name',
    'NameOfIsocenterToRef': 'Annotation.Name',
    'Color': 'Annotation.DisplayColor'
}


_OPTIMIZATION_FN_PARAM_MAPPING = {
    'FunctionType': cll.get_opt_fn_type,
    'RoiName': 'ForRegionOfInterest.Name',
    'IsConstraint': None,
    'RestrictAllBeamsIndividually': None,
    'RestrictToBeam': None,
    'IsRobust': 'UseRobustness',
    'RestrictToBeamSet': None,
    'UseRbeDose': None
}


_OPTIMIZATION_FN_DEFAULT = {
    'IsConstraint': False,
    'RestrictAllBeamsIndividually': False,
    'RestrictToBeam': None,
    'IsRobust': True,
    'RestrictToBeamSet': None,
    'UseRbeDose': False
}


_OPTIMIZATION_FN_TYPES = {
    'MinDose',
    'MaxDose',
    'MinDvh',
    'MaxDvh',
    'UniformDose',
    'MinEud',
    'MaxEud',
    'TargetEud',
    'DoseFallOff',
    'UniformityConstraint'
}


_OPTIMIZATION_FN_PARAM_EXCLUDE = {
    'LqModelParameters',
    'DoseGridStructuresSource',
    'ForTargetRoi',
    'OfTargetDoseGridRoi'
}


_ARC_BEAM_OPT_PARAM_MAPPING = {
    'CreateDualArcs': cll.is_dual_arcs,
    'FinalGantrySpacing': 'FinalArcGantrySpacing',
    'MaxArcDeliveryTime': True,
    'BurstGantrySpacing': True,
    'MaxArcMU': True
}


# List of attributes in the segment to copy
_ARC_SEGMENT_COPY_SET = {
    'JawPositions',
    'LeafPositions',
    'DoseRate',
    'RelativeWeight'
}


_DOSEGRID_PARAM_MAPPING = {
    'Corner': True,
    'VoxelSize': True,
    'NumberOfVoxels': 'NrVoxels'
}


def param_from_mapping(obj, param_map, default_map=None):
    if default_map:
        params = copy.deepcopy(default_map)
    else:
        params = {}

    map_p = {key: (param_map[key](obj) if callable(param_map[key])
                   else (_rs_getattr(obj, key) if _rs_hasattr(obj, key) else
                         _rs_getattr(obj, param_map[key])))
             for key in param_map
             if key and (callable(param_map[key])
                         or _rs_hasattr(obj, param_map[key])
                         or _rs_hasattr(obj, key))}

    params.update(map_p)
    return params


@cll
def get_technique_from_beamset(beamset):
    if beamset.PlanGenerationTechnique == 'Imrt':
        if beamset.DeliveryTechnique == 'DynamicArc':
            return 'VMAT'
        elif beamset.DeliveryTechnique == 'SMLC':
            return 'SMLC'
        elif beamset.DeliveryTechnique == 'DMLC':
            return 'DMLC'

    elif beamset.PlanGenerationTechnique == 'Conformal':
        if beamset.DeliveryTechnique == 'SMLC':
            return 'Conformal'
        elif beamset.DeliveryTechnique == 'StaticArc':
            return 'StaticArc'
        elif beamset.DeliveryTechnique == 'DynamicArc':
            return 'ConformalArc'

    else:
        raise NotImplementedError("Couldn't determine beamset delivery")


@cll
def get_iso_from_beam(beam):
    iso = beam.Isocenter
    iso_params = param_from_mapping(iso, _ISOCENTER_PARAM_MAPPING)
    return iso_params


@cll
def is_dual_arcs(arc_conv_settings):
    if arc_conv_settings.NumberOfArcs != 1:
        return True
    else:
        return False


@cll
def get_opt_fn_type(opt_fn):
    dfp = opt_fn.DoseFunctionParameters
    fntype = None
    if _rs_hasattr(dfp, 'FunctionType'):
        _logger.debug(f"{opt_fn} had {dfp.FunctionType=}")
        fntype = dfp.FunctionType
    elif _rs_hasattr(dfp, 'PenaltyType'):
        _logger.debug(f"{opt_fn} had {dfp.PenaltyType=}, "
                      "FunctionType set to 'DoseFallOff'")
        fntype = 'DoseFallOff'
    else:
        _logger.error(f"{opt_fn} did not have FunctionType or PenaltyType.")

    return fntype


def get_unique_name(obj, container):
    if isinstance(container, set):
        limiting_set = container
    elif _rs_hasattr(container, 'Keys'):
        limiting_set = set(container.Keys)
    else:
        try:
            limiting_set = set(map(_obj_name, container))
        except (ValueError, AttributeError):
            limiting_set = set(container)

    o_name = f'{obj}'
    n = 0
    while o_name in limiting_set:
        o_name = f'{obj} ({n})'
        n += 1

    return o_name


def params_from_beamset(beamset, examination_name=None):

    # Fill with easily obtainable values first.
    params = param_from_mapping(beamset, _BS_PARAM_MAPPING, _BS_PARAM_DEFAULT)

    params['TreatmentTechnique'] = get_technique_from_beamset(beamset)

    for dsp in beamset.DoseSpecificationPoints:
        params['NewDoseSpecificationPointNames'].append(dsp.Name)
        params['NewDoseSpecificationPoints'].append(dsp.Coordinates)

    if examination_name:
        params['ExaminationName'] = examination_name

    return params


def params_from_dosegrid(dosegrid):
    params = param_from_mapping(dosegrid, _DOSEGRID_PARAM_MAPPING)
    return params


def dup_object_param_values(obj_in, obj_out,
                            includes=None, excludes=[], sub_objs=[], _depth=0):
    if _depth > DUP_MAX_RECURSE:
        raise RecursionError(f"{__name__} too deep ({_depth} layers),"
                             " this may be a self referential object.")

    sub_obj_depth = max([s.count('.') for s in sub_objs] + [0])
    if sub_obj_depth > DUP_MAX_RECURSE:
        raise ValueError(f"Subobjects too deep ({sub_obj_depth} > "
                         f"{DUP_MAX_RECURSE}): {sub_objs=}")

    # TODO: Consider exclududing any objects which are PyScriptObjects unless
    # explicitly included.

    # Get the list of sub_objects we might be acting on.
    sub_o_set = {sub_o for sub_o in sub_objs if _rs_hasattr(obj_out, sub_o)}

    # Objects to act on directly, copying everything in them.
    sub_o_root_set = {sub_o for sub_o in sub_o_set if '.' not in sub_o}

    # Objects who have a deep component to be acted on later in the recursed
    # dup_obj_param_values call.
    sub_o_deep_set = {sub_o for sub_o in sub_o_set if '.' in sub_o}
    sub_o_deep_root_set = {sub_o.split('.', 1)[0] for sub_o in sub_o_deep_set}

    # All roots, including shallow, shallow+deep, and deep only
    sub_o_all_root_set = sub_o_root_set | sub_o_deep_root_set

    # Mapping of sub_objs to pass to later dup_obj_param_values calls.
    sub_o_deep_set_map = {o_root: {sub_sub_o.split('.', 1)[1] for sub_sub_o
                                   in sub_o_deep_set
                                   if sub_sub_o.split('.', 1)[0] == o_root}
                          for o_root in sub_o_all_root_set}

    # Objects with deep sets but no root set to copy (Handle differently from
    # the normal objects
    sub_o_deep_only_root_set = sub_o_deep_root_set - sub_o_root_set

    # If passed a sub object with its own sub objects, assume that we cannot
    # use it in the list of params to be copied alone.
    top_excludes = sub_o_root_set | sub_o_deep_root_set | set(excludes)

    if includes is None:
        top_includes = set(dir(obj_out))
    else:
        top_includes = {inc for inc in includes if '.' not in inc}

    params = {p for p in top_includes if p not in top_excludes}
    for param in params:
        value = _rs_getattr(obj_in, param)
        setattr(obj_out, param, value)
        _logger.debug(f'{"":->{_depth}s}{"":>>{_depth>0:d}s}Set'
                      f' {param}={value} on {obj_out}')

    # Loop through objects to be copied
    for sub_obj in sub_o_root_set:
        sub_in = _rs_getattr(obj_in, sub_obj)
        sub_out = _rs_getattr(obj_out, sub_obj)

        # Explicitly requested objects to copy.
        sub_sub_objs = sub_o_deep_set_map[sub_obj]  # This may be an empty set

        # Exclude anything already excluded in the dot notation
        sub_excludes = {exc.split('.', 1)[1] for exc in excludes
                        if '.' in exc and sub_obj == exc.split('.', 1)[0]}

        sub_includes = None
        if includes:
            sub_includes = {inc.split('.', 1)[1] for inc in includes
                            if '.' in inc and inc.split('.', 1)[0] == sub_obj}

        if not sub_includes and sub_obj not in sub_o_deep_only_root_set:
            sub_includes = None

        # Add excludes for all objects in root that are not in the sub_sub_objs
        # list if this is a member of the sub_o_deep_only_root_set.
        dup_object_param_values(sub_in,
                                sub_out,
                                includes=sub_includes,
                                excludes=sub_excludes,
                                sub_objs=sub_sub_objs,
                                _depth=_depth+1)
    return None


def copy_plan_to_duplicate_exam(patient, icase, plan_in):
    exam_in = plan_in.BeamSets[0].GetPlanningExamination()
    exam_out = _duplicate_exam(patient, icase, exam_in)

    return copy_plan_to_exam(icase, plan_in, exam_out)


def copy_plan_to_exam(icase, plan_in, exam_out):
    plan_params = param_from_mapping(plan_in, _PLAN_PARAM_MAPPING,
                                     _PLAN_PARAM_DEFAULT)

    plan_out_name = get_unique_name(f'{plan_in.Name} (dup)',
                                    icase.TreatmentPlans)

    plan_params['ExaminationName'] = exam_out.Name

    plan_params['PlanName'] = plan_out_name
    with _CompositeAction("Create duplicate plan {plan_out_name}"):
        # First create an empty plan on the new exam.
        icase.AddNewPlan(**plan_params)
        copy_plan_to_plan(plan_in, icase.TreatmentPlans[plan_out_name])

    return icase.TreatmentPlans[plan_out_name]


def copy_plan_to_plan(plan_in, plan_out):
    if len(plan_out.BeamSets) > 1:
        raise NotImplementedError("Only supports copying into empty plan")

    tempbs = plan_out.BeamSets[0]
    tempname = get_unique_name('TEMP_BS', plan_out.BeamSets)
    tempbs.DicomPlanLabel = tempname

    destination_exam = tempbs.GetPlanningExamination()

    # Purge the tempbs of beams to fix isocenter crash.
    tempbs.ClearBeams(RemoveBeams=True,
                      ClearBeamModifiers=True,
                      BeamNames=None)

    for bs in plan_in.BeamSets:
        copy_bs(plan_in, bs, plan_out, destination_exam.Name)

    # Done with the placeholder beamset.
    tempbs.DeleteBeamSet()

    copy_clinical_goals(plan_in, plan_out)

    copy_plan_optimizations(plan_in, plan_out)


def copy_bs(plan_in, beamset_in, plan_out, examination_name=None):
    _logger.debug(f"Copying {beamset_in} to {plan_out} as new beamset.")

    params = params_from_beamset(beamset_in, examination_name)

    _logger.debug(f"Adding new beamset with {params=}")

    final_technique = params['TreatmentTechnique']
    if 'Arc' in beamset_in.DeliveryTechnique:
        # Some type of arc, for now beamset_out must be set to conformal arc to
        # allow creation of segments.
        params['TreatmentTechnique'] = 'ConformalArc'

    plan_out.AddNewBeamSet(**params)

    beamset_out = plan_out.BeamSets[params['Name']]

    copy_rx(beamset_in, beamset_out)

    copy_beams(plan_in, beamset_in, plan_out, beamset_out)

    # After copying beams, set technique back to intended.
    if params['TreatmentTechnique'] != final_technique:
        beamset_out.SetTreatmentTechnique(Technique=final_technique)

    # Dose Grid
    dg_params = params_from_dosegrid(beamset_in.GetDoseGrid())
    beamset_out.UpdateDoseGrid(**dg_params)


def params_from_rx(rx):
    # Get params list from mapping and type of Rx.
    if rx.PrescriptionType == 'DoseAtPoint':
        # Could be either Poi or Site
        if _rs_hasattr(rx, 'OnDoseSpecificationPoint'):
            rx_type = 'Site'
            mapping = _RX_SITE_PARAM_MAPPING
        else:
            rx_type = 'Poi'
            mapping = _RX_POI_PARAM_MAPPING
    else:
        rx_type = 'Roi'
        mapping = _RX_ROI_PARAM_MAPPING

    params = param_from_mapping(rx, mapping)

    params['RxType'] = rx_type

    return params


def copy_rx(beamset_in, beamset_out):
    _logger.debug(f"Copying Prescriptions from {beamset_in} to {beamset_out}.")

    rx_in = beamset_in.Prescription
    rx_out = beamset_out.Prescription
    if not _rs_hasattr(rx_in, 'PrescriptionDoseReferences'):
        _logger.debug(f"{beamset_in} has no prescriptions, skipping")
        return False

    # Use Dose References.
    doserefs = list(rx_in.PrescriptionDoseReferences)

    prim_rx_ref = rx_in.PrimaryPrescriptionDoseReference
    prim_uid = prim_rx_ref.DoseReferenceIdentifier.UID

    if (rx_out.PrescriptionDoseReferences and
            len(rx_out.PrescriptionDoseReferences) > 0):
        for rx in rx_out:
            rx.DeletePrescriptionDoseReference()

    for rx in doserefs:
        is_primary = rx.DoseReferenceIdentifier.UID == prim_uid
        params = params_from_rx(rx)

        fn_type = params.pop('RxType')
        fn = _rs_getattr(beamset_out, f'Add{fn_type}PrescriptionDoseReference')
        _logger.debug(f'Adding {fn_type} Rx to {beamset_out}: {params}')
        fn(**params)

        if is_primary:
            out_refs = rx_out.PrescriptionDoseReferences
            last_rx = out_refs[len(out_refs) - 1]
            last_rx.SetPrimaryPrescriptionDoseReference()


def photon_params_from_beam(beam):

    if 'Arc' in beam.DeliveryTechnique:
        create_beam = 'CreateArcBeam'
        mapping = _BEAM_PHOTON_ARC_PARAM_MAPPING
        defaults = _BEAM_PHOTON_ARC_DEFAULT
    else:
        create_beam = 'CreatePhotonBeam'
        mapping = _BEAM_PHOTON_STATIC_PARAM_MAPPING
        defaults = _BEAM_PHOTON_STATIC_DEFAULT

    # Fill with easily obtainable values first.
    params = param_from_mapping(beam, mapping, defaults)

    # Define which function will be used.
    params['CreateFn'] = create_beam

    return params


def params_from_optimization(opt_fn):
    # Fill with easily obtainable values first.
    params = param_from_mapping(opt_fn, _OPTIMIZATION_FN_PARAM_MAPPING,
                                _OPTIMIZATION_FN_DEFAULT)

    return params


def beam_opt_settings_from_plan(plan, beam):
    for opt in plan.PlanOptimizations:
        for tx_setup in opt.OptimizationParameters.TreatmentSetupSettings:
            for beamsetting in tx_setup.BeamSettings:
                # Name should be unique in a plan, but we can't compare using
                # ForBeam == beam because they are references to objects and
                # could be different.
                if beamsetting.ForBeam.Name == beam.Name:
                    return beamsetting
    return None


def copy_beams(plan_in, beamset_in, plan_out, beamset_out,
               copy_segments=False):
    _logger.debug(f"Copying beams from {beamset_in} to {beamset_out}.")

    if beamset_in.Modality == 'Photons':
        # Will have to test which one later, for now just use PhotonBeam
        params_from_beam = photon_params_from_beam
    else:
        raise NotImplementedError("Only photons supported at this time.")

    pm_out = beamset_out.PatientSetup.CollisionProperties.ForPatientModel

    existing_iso_set = {beam.Isocenter.Annotation.Name
                        for beamset in plan_in.BeamSets
                        for beam in beamset.Beams}
    _logger.debug(f"{existing_iso_set=}")

    iso_map = {}

    # Use list(beamset_in.Beams) to freeze list of beams in case we are copying
    # into the same beamset.
    beam_in_list = list(beamset_in.Beams)
    beam_out_list = []
    for beam_in in beam_in_list:
        params = params_from_beam(beam_in)

        _logger.debug(f"Copying {beam_in.Name} with {params=}.")

        create_beam = _rs_getattr(beamset_out, params['CreateFn'])
        del params['CreateFn']

        # Handle potential duplicate beams
        params['Name'] = get_unique_name(params['Name'], beamset_out.Beams)

        iso_name = params['IsocenterData']['Name']

        if iso_name in existing_iso_set:
            if iso_name not in iso_map:
                iso_map[iso_name] = get_unique_name(iso_name, existing_iso_set)

            _logger.debug(f"{iso_map=}, {iso_name=}")
            params['IsocenterData']['Name'] = iso_map[iso_name]
            params['IsocenterData']['NameOfIsocenterToRef'] = iso_map[iso_name]

        create_beam(**params)

        beam_out = beamset_out.Beams[params['Name']]
        beam_out_list.append(beam_out)

        # Need to set optmization settings for this beam in order to build
        # control points.
        beamsetting_in = beam_opt_settings_from_plan(plan_in, beam_in)
        beamsetting_out = beam_opt_settings_from_plan(plan_out, beam_out)

        if 'Arc' in beam_in.DeliveryTechnique:
            acp_in = beamsetting_in.ArcConversionPropertiesPerBeam
            acp_out = beamsetting_out.ArcConversionPropertiesPerBeam
            arc_params = param_from_mapping(acp_in,
                                            _ARC_BEAM_OPT_PARAM_MAPPING)

            acp_out.EditArcBasedBeamOptimizationSettings(**arc_params)

    # Need to generate Segments for all beams at once or it will fail.
    if not copy_segments:
        _logger.debug("Not asked to copy segments, done copying beams.")
        return None

    target_rois = [s.Name for s in pm_out.RegionsOfInterest
                   if (_rs_hasattr(s, 'OrganData.OrganType')
                       and (_rs_getattr(s, 'OrganData.OrganType') ==
                            'Target'))]
    if not target_rois:
        _logger.warning("Asked to copy segments, but there are"
                        " no target ROIs. Skipping.")
        return None

    tgt = target_rois[0]

    beamset_out.SelectToUseROIasTreatOrProtectForAllBeams(RoiName=tgt)
    beamset_out.GenerateConformalArcSegments(Beams=[beam_out.Name for beam_out
                                                    in beam_out_list])

    for beam_in, beam_out in zip(beam_in_list, beam_out_list):
        # Ensure enough MU so segments are computable
        beam_out.BeamMU = beam_in.BeamMU if beam_in.BeamMU > 0 else 1000
        copy_arc_segments(beam_in, beam_out)

    beamset_out.ClearROIFromTreatOrProtectUsageForAllBeams(RoiName=tgt)

    return None


def copy_arc_segments(beam_in, beam_out):
    if len(beam_in.Segments) != len(beam_out.Segments):
        raise ValueError(f"{beam_out.Name} doesn't have the same number of "
                         f"segments as {beam_in.Name} "
                         f"({beam_in.Segments.Count} != "
                         f"{beam_out.Segments.Count}).")

    for seg_in, seg_out in zip(beam_in.Segments, beam_out.Segments):
        dup_object_param_values(seg_in, seg_out,
                                includes=_ARC_SEGMENT_COPY_SET)


def copy_plan_optimizations(plan_in, plan_out):
    _logger.debug("Copying optimization objectives "
                  f"from {plan_in} to {plan_out}.")

    n_opts_in = len(plan_in.PlanOptimizations)
    n_opts_out = len(plan_out.PlanOptimizations)
    _logger.debug(f"{n_opts_in=}, {n_opts_out=}")

    if n_opts_in != n_opts_out:
        raise ValueError("Different number of optimization sets. "
                         "Cannot continue.")

    with _CompositeAction("Copy Optimizations from "
                          f"{plan_in.Name} to {plan_out.Name}"):
        for opt_in, opt_out in zip(plan_in.PlanOptimizations,
                                   plan_out.PlanOptimizations):
            copy_optimizations(opt_in, opt_out)


def copy_optimizations(opt_in, opt_out):
    with _CompositeAction(f"Copy Optimizations from {opt_in} to {opt_out}"):
        copy_opt_functions(opt_in, opt_out)

        copy_opt_parameters(opt_in.OptimizationParameters,
                            opt_out.OptimizationParameters)


def copy_opt_functions(opt_in, opt_out):
    opt_out.ClearConstituentFunctions()

    opt_beamsets_out = [bs.DicomPlanLabel for bs in opt_out.OptimizedBeamSets]
    # Allow list of beamsets to include None for composite or single opts
    opt_beamsets_out.append(None)

    # Copy Constituent Functions
    for fn_in in opt_in.Objective.ConstituentFunctions:
        params = params_from_optimization(fn_in)

        # TODO: Currently we only handle single optimizations, and don't handle
        # beam set dependency.  These require checking the "OfDoseDistribution"
        # value if it is a dependency calc.  They will not appear if it is not
        # for a composite.  There will also be a BackgroundDose member of the
        # optimization object.
        # For Co-opt: Composites will have a
        # "DeleteOnDeletedConstituentFunctions" attribute in the
        # OfDoseDistribution, and individual BS objectives will have
        # "ForBeamSet" in "OfDoseDistribution" linking to BS.
        # Those meant to be composite should have "RestrictToBeamSet" = None
        # while those for individual BS should have "Restrict..." = "<BS.Name>"

        # TODO: Handle robust optimization values.

        if params['RestrictToBeamSet'] not in opt_beamsets_out:
            _logger.warning(f'Unmatched beamset "{params["RestrictToBeamSet"]}'
                            "in opt function {fn_in} ({params=}), skipping.")
            continue

        if params['FunctionType'] not in _OPTIMIZATION_FN_TYPES:
            _logger.warning(f"Unknown input FunctionType in {params=}, "
                            "skipping.")
            continue

        _logger.debug(f"Copying optimization funciton {params=}")
        fn_out = opt_out.AddOptimizationFunction(**params)

        # Will need to copy all of the function values (Excluding those known
        # to cause issues).
        dup_object_param_values(fn_in.DoseFunctionParameters,
                                fn_out.DoseFunctionParameters,
                                excludes=_OPTIMIZATION_FN_PARAM_EXCLUDE)


def copy_opt_parameters(optparam_in, optparam_out):

    # Build matching TSS based on TSS.ForTreatmentSetup.DicomPlanName
    tss_dict_in = {tss.ForTreatmentSetup.DicomPlanLabel: tss for tss
                   in optparam_in.TreatmentSetupSettings}
    tss_dict_out = {tss.ForTreatmentSetup.DicomPlanLabel: tss for tss
                    in optparam_out.TreatmentSetupSettings
                    if tss.ForTreatmentSetup.DicomPlanLabel in tss_dict_in}
    # Copy TreatmentSetupSettings
    for tss_name, tss_out in tss_dict_out.items():
        copy_opt_tss(tss_dict_in[tss_name], tss_out)


def copy_opt_tss(tss_in, tss_out):
    _logger.debug(f"Copying TreatmentSetupSettings {tss_in} to {tss_out}")
    dup_object_param_values(tss_in.SegmentConversion,
                            tss_out.SegmentConversion,
                            sub_objs=['ArcConversionProperties'])
    pass
