import logging
from .clinicalgoals import copy_clinical_goals
from .external import (CompositeAction as _CompositeAction, ObjectDict,
                       params_from_mapping, get_machine,
                       rs_getattr, rs_hasattr,
                       dup_object_param_values, CallLaterList, get_unique_name)
from .examinations import duplicate_exam as _duplicate_exam
# from .points import point as _point

_logger = logging.getLogger(__name__)

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
#    'CyberKnifeCollimationType': None,
#    'CyberKnifeNodeSetName': None,
#    'CyberKnifeRampVersion': None,
#    'CyberKnifeAllowIncreasedPitchCorrection': None,
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
    #'CyberKnifeCollimationType': None,
    #'CyberKnifeNodeSetName': None,
    #'CyberKnifeRampVersion': None,
    #'CyberKnifeAllowIncreasedPitchCorrection': None
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

_OPTIMIZATION_PARAM_EXCLUDE = {
}

_OPTIMIZATION_PARAM_SUBOBJS = {
    'Algorithm',
    'DoseCalculation',
    'DoseCalculation.OptimizationDoseAlgorithm',
    'DoseMimicParameters',
    'FineTuneOptimizationSettings',
    'RobustnessParameters.DensityUncertaintyParameters',
    'RobustnessParameters.PatientGeometryUncertaintyParameters',
    'RobustnessParameters.PositionUncertaintyParameters',
    'RobustnessParameters.RobustComputationSettings',
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
    iso_params = params_from_mapping(iso, _ISOCENTER_PARAM_MAPPING)
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
    if rs_hasattr(dfp, 'FunctionType'):
        _logger.debug(f"{opt_fn} had {dfp.FunctionType=}")
        return dfp.FunctionType
    elif rs_hasattr(dfp, 'PenaltyType'):
        _logger.debug(f"{opt_fn} had {dfp.PenaltyType=}, "
                      "FunctionType set to 'DoseFallOff'")
        return 'DoseFallOff'
    else:
        raise Warning(f"{opt_fn} did not have FunctionType or PenaltyType.")


def params_from_beamset(beamset, examination_name=None):

    # Fill with easily obtainable values first.
    params = params_from_mapping(beamset, _BS_PARAM_MAPPING, _BS_PARAM_DEFAULT)

    for dsp in beamset.DoseSpecificationPoints:
        params['NewDoseSpecificationPointNames'].append(dsp.Name)
        params['NewDoseSpecificationPoints'].append(dsp.Coordinates)

    if examination_name:
        params['ExaminationName'] = examination_name

    return params


def params_from_dosegrid(dosegrid):
    return params_from_mapping(dosegrid, _DOSEGRID_PARAM_MAPPING)


def params_from_rx(rx):
    # Get params list from mapping and type of Rx.
    if rx.PrescriptionType == 'DoseAtPoint':
        # Could be either Poi or Site
        if rs_hasattr(rx, 'OnDoseSpecificationPoint'):
            rx_type = 'Site'
            mapping = _RX_SITE_PARAM_MAPPING
        else:
            rx_type = 'Poi'
            mapping = _RX_POI_PARAM_MAPPING
    else:
        rx_type = 'Roi'
        mapping = _RX_ROI_PARAM_MAPPING

    params = params_from_mapping(rx, mapping)

    params['RxType'] = rx_type

    return params


def params_from_photon_beam(beam):

    if 'Arc' in beam.DeliveryTechnique:
        create_beam = 'CreateArcBeam'
        mapping = _BEAM_PHOTON_ARC_PARAM_MAPPING
        defaults = _BEAM_PHOTON_ARC_DEFAULT
    else:
        create_beam = 'CreatePhotonBeam'
        mapping = _BEAM_PHOTON_STATIC_PARAM_MAPPING
        defaults = _BEAM_PHOTON_STATIC_DEFAULT

    # Fill with easily obtainable values first.
    params = params_from_mapping(beam, mapping, defaults)

    # Define which function will be used.
    params['CreateFn'] = create_beam

    return params


def params_from_optimization(opt_fn):
    # Fill with easily obtainable values first.
    params = params_from_mapping(opt_fn, _OPTIMIZATION_FN_PARAM_MAPPING,
                                 _OPTIMIZATION_FN_DEFAULT)

    return params


def params_from_plan(plan):
    plan_params = params_from_mapping(plan, _PLAN_PARAM_MAPPING,
                                      _PLAN_PARAM_DEFAULT)
    return plan_params


def copy_plan_to_duplicate_exam(patient, icase, plan_in,
                                exam_out_name=None, exclude_segments=True,
                                forced_machine=None):
    exam_in = plan_in.BeamSets[0].GetPlanningExamination()
    exam_out = _duplicate_exam(patient, icase, exam_in,
                               exam_name_out=exam_out_name)

    return copy_plan_to_exam(icase, plan_in, exam_out,
                             exclude_segments=exclude_segments,
                             forced_machine=forced_machine)


def copy_plan_to_exam(icase, plan_in, exam_out, exclude_segments=False,
                      forced_machine=None):
    plan_params = params_from_plan(plan_in)

    plan_out_name = get_unique_name(f'{plan_in.Name} (dup)',
                                    icase.TreatmentPlans)

    plan_params['ExaminationName'] = exam_out.Name

    plan_params['PlanName'] = plan_out_name

    with _CompositeAction("Create duplicate plan {plan_out_name}"):
        # First create an empty plan on the new exam.
        _logger.debug(f"Add new plan with {plan_params=}")
        plan_out = icase.AddNewPlan(**plan_params)
        copy_plan_to_plan(plan_in, plan_out, exam_out,
                          exclude_segments=exclude_segments,
                          forced_machine=forced_machine)

    return icase.TreatmentPlans[plan_out_name]


def copy_plan_to_plan(plan_in, plan_out,
                      exam_out=None, exclude_segments=False,
                      forced_machine=None):

    tempbs = None
    if len(plan_out.BeamSets) > 1:
        raise NotImplementedError("Only supports copying into empty plan")

    elif len(plan_out.BeamSets) == 1:
        # We have a placeholder beamset, prepare it.
        tempbs = plan_out.BeamSets[0]
        tempname = get_unique_name('TEMP_BS', plan_out.BeamSets)
        tempbs.DicomPlanLabel = tempname

        exam_out = exam_out if exam_out else tempbs.GetPlanningExamination()

        # Purge the tempbs of beams to fix isocenter crash.
        tempbs.ClearBeams(RemoveBeams=True,
                          ClearBeamModifiers=True,
                          BeamNames=None)

    for bs in plan_in.BeamSets:
        copy_bs(plan_in, bs, plan_out, exam_out.Name,
                exclude_segments=exclude_segments,
                forced_machine=forced_machine)

    # Done with the placeholder beamset.
    if tempbs:
        tempbs.DeleteBeamSet()

    copy_clinical_goals(plan_in, plan_out)

    copy_plan_optimizations(plan_in, plan_out)


def copy_bs(plan_in, beamset_in, plan_out,
            examination_name=None, exclude_segments=False,
            forced_machine=None):
    _logger.debug(f"Copying {beamset_in} to {plan_out} as new beamset.")

    params = params_from_beamset(beamset_in, examination_name)

    if forced_machine is not None:
        params['MachineName'] = forced_machine

    _logger.debug(f"Adding new beamset with {params=}")

    final_technique = params['TreatmentTechnique']
    if 'Arc' in beamset_in.DeliveryTechnique:
        # Some type of arc, for now beamset_out must be set to conformal arc to
        # allow creation of segments.
        params['TreatmentTechnique'] = 'ConformalArc'

    plan_out.AddNewBeamSet(**params)

    beamset_out = plan_out.BeamSets[params['Name']]

    copy_rx(beamset_in, beamset_out)

    copy_beams(plan_in, beamset_in, plan_out, beamset_out,
               exclude_segments=exclude_segments)

    # After copying beams, set technique back to intended.
    if params['TreatmentTechnique'] != final_technique:
        beamset_out.SetTreatmentTechnique(Technique=final_technique)

    # Dose Grid
    dg_params = params_from_dosegrid(beamset_in.GetDoseGrid())
    beamset_out.UpdateDoseGrid(**dg_params)


def copy_rx(beamset_in, beamset_out):
    _logger.debug(f"Copying Prescriptions from {beamset_in} to {beamset_out}.")

    rx_in = beamset_in.Prescription
    rx_out = beamset_out.Prescription
    if not rs_hasattr(rx_in, 'PrescriptionDoseReferences'):
        _logger.debug(f"{beamset_in} has no prescriptions, skipping")
        return False

    # Use Dose References.
    doserefs = list(rx_in.PrescriptionDoseReferences)

    prim_rx_ref = rx_in.PrimaryPrescriptionDoseReference
    prim_uid = prim_rx_ref.DoseReferenceIdentifier.UID

    if (rx_out.PrescriptionDoseReferences and
            len(rx_out.PrescriptionDoseReferences) > 0):
        for rx in rx_out.PrescriptionDoseReferences:
            rx.DeletePrescriptionDoseReference()

    for rx in doserefs:
        is_primary = rx.DoseReferenceIdentifier.UID == prim_uid
        params = params_from_rx(rx)

        fn_type = params.pop('RxType')
        fn = rs_getattr(beamset_out, f'Add{fn_type}PrescriptionDoseReference')
        _logger.debug(f'Adding {fn_type} Rx to {beamset_out}: {params}')
        fn(**params)

        if is_primary:
            out_refs = rx_out.PrescriptionDoseReferences
            last_rx = out_refs[len(out_refs) - 1]
            last_rx.SetPrimaryPrescriptionDoseReference()


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
               exclude_segments=True):
    _logger.debug(f"Copying beams from {beamset_in} to {beamset_out}.")

    if beamset_in.Modality == 'Photons':
        # Will have to test which one later, for now just use PhotonBeam
        params_from_beam = params_from_photon_beam
    else:
        raise NotImplementedError("Only photons supported at this time.")

    pm_out = beamset_out.PatientSetup.CollisionProperties.ForPatientModel

    existing_iso_set = {beam.Isocenter.Annotation.Name
                        for beamset in plan_in.BeamSets
                        for beam in beamset.Beams}
    _logger.debug(f"{existing_iso_set=}")

    iso_map = {}

    machine_in = get_machine(beamset_in.MachineReference.MachineName)
    machine_out = get_machine(beamset_out.MachineReference.MachineName)

    energy_map = {e: machine_out.closest_energy(e)
                  for e in machine_in.photon_energies}

    _logger.debug(f"{energy_map=}")

    # Use list(beamset_in.Beams) to freeze list of beams in case we are copying
    # into the same beamset.
    beam_in_list = list(beamset_in.Beams)
    beam_out_list = []
    for beam_in in beam_in_list:
        params = params_from_beam(beam_in)

        _logger.debug(f"Copying {beam_in.Name} with {params=}.")

        create_beam = rs_getattr(beamset_out, params['CreateFn'])
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

        params['BeamQualityId'] = energy_map[params['BeamQualityId']]

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
            arc_params = params_from_mapping(acp_in,
                                             _ARC_BEAM_OPT_PARAM_MAPPING)

            acp_out.EditArcBasedBeamOptimizationSettings(**arc_params)
        else:
            exclude_segments = True

    # Need to generate Segments for all beams at once or it will fail.
    if exclude_segments:
        _logger.debug("Not asked to copy segments, done copying beams.")
        return None

    target_rois = [s.Name for s in pm_out.RegionsOfInterest
                   if (rs_hasattr(s, 'OrganData.OrganType')
                       and (rs_getattr(s, 'OrganData.OrganType') ==
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
    if opt_in.Objective is None:
        return
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

    # Duplicate basic objects first
    dup_object_param_values(optparam_in, optparam_out,
                            excludes=_OPTIMIZATION_PARAM_EXCLUDE,
                            sub_objs=_OPTIMIZATION_PARAM_SUBOBJS)

    # Build matching TSS based on TSS.ForTreatmentSetup.DicomPlanName
    tss_dict_in = ObjectDict(optparam_in.TreatmentSetupSettings)
    tss_dict_out = ObjectDict(optparam_out.TreatmentSetupSettings)

    # Copy TreatmentSetupSettings
    for tss_name in tss_dict_out & tss_dict_in:
        copy_opt_tss(tss_dict_in[tss_name], tss_dict_out[tss_name])

    # For robustness, try adding any additional exams present ing the
    # PatientGeometryUncertaintyParameters.Examinations collection.
    try:
        rob_in = optparam_in.RobustnessParameters
        if len(rob_in.PatientGeometryUncertaintyParameters.Examinations) > 0:
            # TODO: For robustness, we will need to call
            # optparam_out.SaveRobustnessParameters to set the examinations.
            #raise NotImplementedError
            pass
    except (TypeError, AttributeError):
        pass


def copy_opt_tss(tss_in, tss_out):
    _logger.debug(f"Copying TreatmentSetupSettings {tss_in} to {tss_out}")

    # Copy SegmentConversion objects
    dup_object_param_values(tss_in.SegmentConversion,
                            tss_out.SegmentConversion,
                            sub_objs=['ArcConversionProperties'])

    # Build matching BeamSettings based on obj_name(BS.ForBeam)
    bss_dict_in = ObjectDict(tss_in.BeamSettings)
    bss_dict_out = ObjectDict(tss_out.BeamSettings)

    for bss_name in bss_dict_in & bss_dict_out:
        dup_object_param_values(bss_dict_in[bss_name], bss_dict_out[bss_name],
                                sub_objs=['ArcConversionPropertiesPerBeam'])
