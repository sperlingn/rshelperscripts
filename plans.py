import logging
from .clinicalgoals import copy_clinical_goals
from .external import (CompositeAction as CompositeAction, ObjectDict,
                       params_from_mapping, get_machine, obj_name, clamp,
                       rs_getattr, rs_hasattr, sequential_dedup_return_list,
                       dup_object_param_values, CallLaterList, get_unique_name,
                       Show_OK, renumber_beams)
from .examinations import duplicate_exam as _duplicate_exam
from .roi import ROI_Builder
from .i18n import BEAMNAME_QUADRANT_TO_NAME, BEAMNAME_BREAST_SC_PA
from difflib import get_close_matches
# from .points import point as _point

_logger = logging.getLogger(__name__)

# Anything within BEAM_ANGLE_PROX_LIMIT of a cardinal angle is presumed
#  to be that angle.
BEAM_ANGLE_PROX_LIMIT = 5.1

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
    'ExaminationName': 'PatientSetup.CollisionProperties.'
                       'ForExaminationStructureSet.OnExamination.Name',
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
    'ExaminationName': None,  # Needs to be set from new plan
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
    # 'CyberKnifeCollimationType': None,
    # 'CyberKnifeNodeSetName': None,
    # 'CyberKnifeRampVersion': None,
    # 'CyberKnifeAllowIncreasedPitchCorrection': None,
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
    # 'CyberKnifeCollimationType': None,
    # 'CyberKnifeNodeSetName': None,
    # 'CyberKnifeRampVersion': None,
    # 'CyberKnifeAllowIncreasedPitchCorrection': None
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

    with CompositeAction(f"Create duplicate plan {plan_out_name}"):
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
        tempname = get_unique_name('TEMP_BS', plan_in.BeamSets)
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

    return plan_out


def copy_bs(plan_in, beamset_in, plan_out,
            examination_name=None, exclude_segments=False,
            forced_machine=None):
    _logger.debug(f"Copying {beamset_in} to {plan_out} as new beamset.")

    params = params_from_beamset(beamset_in, examination_name)

    if forced_machine is not None:
        params['MachineName'] = forced_machine

    _logger.debug(f"Adding new beamset with {params=}")

    final_technique = params['TreatmentTechnique']

    plan_out.AddNewBeamSet(**params)

    beamset_out = plan_out.BeamSets[params['Name']]

    copy_rx(beamset_in, beamset_out)

    if 'Arc' in beamset_in.DeliveryTechnique and \
            not native_copy_ok(beamset_in, beamset_out):
        # Some type of arc, for now beamset_out must be set to conformal arc to
        # allow creation of segments.
        beamset_out.SetTreatmentTechnique(Technique='ConformalArc')

    copy_beams(plan_in, beamset_in, plan_out, beamset_out,
               exclude_segments=exclude_segments)

    # After copying beams, set technique back to intended.
    if params['TreatmentTechnique'] != final_technique:
        beamset_out.SetTreatmentTechnique(Technique=final_technique)

    # Dose Grid
    dg_params = params_from_dosegrid(beamset_in.GetDoseGrid())
    beamset_out.UpdateDoseGrid(**dg_params)

    return beamset_out


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

    return rx_out


def beam_opt_settings_from_plan(plan, beamset, beam):
    bsid = beamset.UniqueId
    for opt in plan.PlanOptimizations:
        # Skip if this is not an opt for this plan.
        if bsid not in (obs.UniqueId for obs in opt.OptimizedBeamSets):
            continue
        for tx_setup in opt.OptimizationParameters.TreatmentSetupSettings:
            if tx_setup.ForTreatmentSetup.UniqueId != bsid:
                # Not for this beamset, skip.
                continue
            for beamsetting in tx_setup.BeamSettings:
                # Name should be unique in a plan, but we can't compare using
                # ForBeam == beam because they are references to objects and
                # could be different.
                if beamsetting.ForBeam.Name == beam.Name:
                    return beamsetting
    return None


def get_opts_for_bs(plan, beamset):
    # Returns a list of PlanOptmizations that optimize this beamset.
    bsid = beamset.UniqueId
    return [opt for opt in plan.PlanOptimizations
            if (bsid in (obs.UniqueId for obs in opt.OptimizedBeamSets) and
                bsid in (tx_setup.ForTreatmentSetup.UniqueId for tx_setup in
                         opt.OptimizationParameters.TreatmentSetupSettings))]


def native_copy_ok(beamset_in, beamset_out):
    # Check if the native copy beamset function would throw an exception
    # without running it (having an exception occur inside of a CompositeAction
    # and trying to catch that exception will crash RS)
    COMPARATORS = ["PatientSetup.CollisionProperties"
                   ".ForExaminationStructureSet.OnExamination.Name",
                   "MachineReference.MachineName",
                   "DeliveryTechnique",
                   "PlanGenerationTechnique",
                   "Modality"]

    bs_list = {attr: [rs_getattr(bs, attr) for bs
                      in [beamset_in, beamset_out]] for attr in COMPARATORS}
    _logger.debug(f"{bs_list=}")

    return all([rs_getattr(beamset_in, attr) == rs_getattr(beamset_out, attr)
                for attr in COMPARATORS])


def copy_beams(plan_in, beamset_in, plan_out, beamset_out, # noqa: C901
               exclude_segments=True):
    _logger.debug(f"Copying beams from {beamset_in} to {beamset_out}.")

    if native_copy_ok(beamset_in, beamset_out):
        beamset_out.CopyBeamsFromBeamSet(BeamSetToCopyFrom=beamset_in,
                                         BeamsToCopy=None)
        return
    else:
        _logger.debug("Failed native copy method, try brute force method.",
                      exc_info=True)

    if beamset_in.Modality == 'Photons':
        # Will have to test which one later, for now just use PhotonBeam
        params_from_beam = params_from_photon_beam
    else:
        raise NotImplementedError("Only photons supported at this time.")

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

    tgt_map = {}
    try:
        tgt_builder = ROI_Builder(beam_set=beamset_out, Type='Ptv')

    except IndexError:
        tgt_builder = None
        _logger.warning("No target ROIs, we will be unable to create "
                        "segments for arc beams")

    # Use list(beamset_in.Beams) to freeze list of beams in case we are copying
    # into the same beamset.
    beam_in_list = list(beamset_in.Beams)
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

        # Need to set optmization settings for this beam in order to build
        # control points.
        beamsetting_in = beam_opt_settings_from_plan(plan_in, beamset_in,
                                                     beam_in)
        beamsetting_out = beam_opt_settings_from_plan(plan_out, beamset_out,
                                                      beam_out)

        if 'Arc' in beam_in.DeliveryTechnique:
            acp_in = beamsetting_in.ArcConversionPropertiesPerBeam
            acp_out = beamsetting_out.ArcConversionPropertiesPerBeam
            arc_params = params_from_mapping(acp_in,
                                             _ARC_BEAM_OPT_PARAM_MAPPING)

            # TODO: Arc params saying "No changes to save" breaks this
            # Right now, instead of using exception handling, check each item
            # try:
            #     acp_out.EditArcBasedBeamOptimizationSettings(**arc_params)
            # except InvalidOperationException:
            #     _logger.error('Reached error in setting arc_params.\n'
            #                   f'Beam: {obj_name(beam_in)}\n'
            #                   f'{acp_in=}\n{acp_out=}\n{arc_params=}',
            #                   exc_info=True)

            n_arc_params = params_from_mapping(acp_out,
                                               _ARC_BEAM_OPT_PARAM_MAPPING)
            if arc_params != n_arc_params:
                _logger.debug(f"Updating arc params for beam"
                              f" '{obj_name(beam_out)}'"
                              f" from {n_arc_params} to {arc_params}")
                acp_out.EditArcBasedBeamOptimizationSettings(**arc_params)
            else:
                _logger.debug(f"Arc params for beam '{obj_name(beam_out)}'"
                              " unchanged, not updating.")

        if not exclude_segments and len(beam_in.Segments) > 0:
            MU_out = beam_in.BeamMU if beam_in.BeamMU > 0 else 999
            # Copy segments for beam
            if 'Arc' in beam_in.DeliveryTechnique and tgt_builder:
                # Arcs need to have the segments built

                # Make a small target box at isocenter
                if iso_name not in tgt_map:
                    roi = tgt_builder.CreateROI(f'{iso_name}_Box')
                    roi.create_box(center=params['IsocenterData']['Position'])

                    tgt_map[iso_name] = roi

                tgt = tgt_map[iso_name].Name

                beam_out.SetTreatOrProtectRoi(RoiName=tgt)
                beamset_out.GenerateConformalArcSegments(Beams=[beam_out.Name])
                copy_arc_segments(beam_in, beam_out)
                beam_out.RemoveTreatOrProtectRoi(RoiName=tgt)
            elif 'SMLC' in beam_in.DeliveryTechnique:
                # SMLC will need a beam to be made for each segment then have
                # those merged
                merge_dest = beam_out.Name
                mergers = []
                beam_seg_out = beam_out
                for i, seg in enumerate(beam_in.Segments):
                    if i != 0:
                        # Need to make beam for additional segments
                        params['Name'] = get_unique_name(f'{merge_dest}[{i}]',
                                                         beamset_out.Beams)
                        mergers.append(params['Name'])
                        create_beam(**params)
                        beam_seg_out = beamset_out.Beams[params['Name']]

                    beam_seg_out.ConformMlc()
                    beam_seg_out.Segments[0].JawPositions = seg.JawPositions
                    beam_seg_out.Segments[0].LeafPositions = seg.LeafPositions

                    # Set MU to 1, will be fixed on merged beam.
                    beam_seg_out.BeamMU = MU_out * seg.RelativeWeight

                if mergers:
                    # Had more than one segment, need to merge.
                    beamset_out.MergeBeamSegments(TargetBeamName=merge_dest,
                                                  MergeBeamNames=mergers)

                beam_out.BeamMU = beam_in.BeamMU
            else:
                _logger.warning(
                    f"Delivery Technique '{beam_in.DeliveryTechnique}' is not "
                    f"supported for copying segments on beam '{beam_in.Name}'."
                    "  Segments will not be copied.")
            beam_out.BeamMU = MU_out

    for tgt in tgt_map:
        tgt_map[tgt].DeleteRoi()

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

    with CompositeAction("Copy Optimizations from "
                         f"{plan_in.Name} to {plan_out.Name}"):
        for opt_in, opt_out in zip(plan_in.PlanOptimizations,
                                   plan_out.PlanOptimizations):
            copy_optimizations(opt_in, opt_out)


def copy_optimizations(opt_in, opt_out):
    with CompositeAction(f"Copy Optimizations from {opt_in} to {opt_out}"):
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
            # raise NotImplementedError
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


def calc_conformity_indices(fd, external, tgt, rx):
    if fd.DoseValues is None:
        _logger.warning("No dose computed, unable to calculate indicies")
        return None

    rxivol, rx50ivol = fd.GetRelativeVolumeAtDoseValues(RoiName=external,
                                                        DoseValues=[rx,
                                                                    rx / 2])

    _logger.debug(f"{rxivol=} {rx50ivol=}")
    pctTV_piv, = fd.GetRelativeVolumeAtDoseValues(RoiName=tgt,
                                                  DoseValues=[rx])

    _logger.debug(f"{pctTV_piv=}")
    d2, d98, d50 = fd.GetDoseAtRelativeVolumes(RoiName=tgt,
                                               RelativeVolumes=[.02, .98, .5])

    _logger.debug(f"{[d2, d98, d50]=}")
    ev = fd.GetDoseGridRoi(RoiName=external).RoiVolumeDistribution.TotalVolume
    tv = fd.GetDoseGridRoi(RoiName=tgt).OfRoiGeometry.GetRoiVolume()

    tv_piv = pctTV_piv * tv

    PCI = ((tv_piv)**2) / (rxivol * ev * tv)

    GI = rx50ivol / rxivol

    RTOGCI = (rxivol * ev) / tv

    HI = (d2 - d98) / d50

    return {'ROI': tgt,
            'ROIvol': tv,
            'PCI': PCI,
            'GI': GI,
            'RTOGCI': RTOGCI,
            'HI': HI}


def beamset_rxinfo(beamset):
    ppdr = beamset.Prescription.PrimaryPrescriptionDoseReference
    rxinfo = {'Dose': ppdr.DoseValue,
              'nFx': beamset.FractionationPattern.NumberOfFractions,
              'ROI': obj_name(rs_getattr(ppdr, "OnStrucure", ""))}
    rxinfo['Dose/fx'] = rxinfo['Dose'] / rxinfo['nFx']

    return rxinfo


def beamset_conformity_indices(beamset, roi=None, dose=None):
    if beamset.FractionDose.DoseValues is None:
        _logger.warning("No dose computed, unable to calculate indicies")
        return None

    rxinfo = beamset_rxinfo(beamset)

    fd = beamset.FractionDose
    rx = dose / rxinfo['nFx'] if dose else rxinfo['Dose/fx']
    tgt = obj_name(roi) if roi else rxinfo['ROI']
    external = obj_name(beamset.GetStructureSet().OutlineRoiGeometry.OfRoi)

    return calc_conformity_indices(fd, external, tgt, rx)


@sequential_dedup_return_list
def block_from_leaves(beam):
    lp = beam.Segments[0].LeafPositions
    lcp = beam.UpperLayer.LeafCenterPositions
    jx1, jx2, jy1, jy2 = beam.Segments[0].JawPositions

    return [{'x': clamp(jx1, xpos, jx2), 'y': clamp(jy1, ypos, jy2)}
            for n, bank in enumerate(lp)
            for xpos, ypos in zip(bank[::n*2-1], lcp[::n*2-1])]


def banks_for_heart(beam, pm=None):
    # You can dictate the logic to get only the bank that matters, but for now
    # this will return both left and right.
    return [0, 1]

    # TODO: For proper checking, should check patient model for orientation,
    # laterality of target, etc.
    if 270 < beam.GantryAngle < 360:
        return [0]
    elif 0 < beam.GantryAngle < 90:
        return [1]


def calc_max_heart_distance(bs, heart_name="Heart"):

    pm = bs.PatientSetup.CollisionProperties.ForPatientModel
    roi_names = pm.RegionsOfInterest.Keys
    heart_roi = get_close_matches(heart_name, roi_names, 1, cutoff=0)[0]

    mhds = {}

    if hasattr(CompositeAction, 'isactive') and CompositeAction.isactive:
        raise UserWarning(f'Function {__name__} performs actions which break '
                          'active CompositeAction(s).  '
                          'Do not use from within a CompositeAction')

    try:
        with CompositeAction("Check MHD (will roll back changes)"):
            # Start a composite action which we will cancel out of by raising
            # an exception

            # Unset all blocking ROIs, just in case.
            for roi in roi_names:
                bs.ClearROIFromTreatOrProtectUsageForAllBeams(RoiName=roi)

            # Store the pre split list of beam names in case bs.Beams changes
            # (depends on if iter(Beams) is a view on beams, or a fixed list at
            # execution time, unknown implementation feature so play it safe)
            beams_pre_split = bs.Beams.Keys

            for beam_name in beams_pre_split:
                beam = bs.Beams[beam_name]
                banks = banks_for_heart(beam)

                # Should be able to clear any blocks using this, but it
                # BeamCreationRules doesn't exist under the beam_set in
                # scripting...

                # bcr = bs.BeamCreationRules
                # bmshapes = bcr.BeamModifierCreationRules[beam.Name]
                # for bmsp in bmshapes.BeamModifierShapeProperties:
                #     bmsp.DeleteVirtualBlock()

                contour = block_from_leaves(beam)
                bs.AddVirtualBlock(Beam=beam.Name,
                                   Contour=contour,
                                   Type='Treat')

                if len(beam.Segments) != 1:
                    bs.SplitBeamSegmentsIntoBeams(BeamName=beam_name)

                beam.ConformMlc()

                ilp = beam.Segments[0].LeafPositions

                # Block the heart
                beam.SetTreatOrProtectRoi(RoiName=heart_roi)
                beam.ConformMlc()

                hlp = beam.Segments[0].LeafPositions

                # The DICOM leaf coordinate system is absolute in RS, so if the
                # left bank closed (bank 0) when we blocked, then the hlp will
                # be greater than the ilp for those leaves, conversely for the
                # right bank (bank 1) the ilp would be greater than the hlp.
                #
                # Might need some logic to check that the leaves outside of the
                # jaws didn't move and contirbute to this.  Leaf positions
                # available in beam.UpperLayer
                maxdiff = (max(hlp[0]-ilp[0]), max(ilp[1]-hlp[1]))

                mhds[beam.Name] = tuple(maxdiff[i] for i in banks)

            raise Warning("Just to bail on the composite action...")

    except Warning:
        pass

    return mhds


def get_imrt_beamname(beam, machine, addtableangle=False):
    beam_values = machine.get_beam_presentation_vals(beam)
    table_text = f"T{beam_values['Couch']:0.0f} " if addtableangle else ""
    g_start = f"G{beam_values['Gantry']:0.0f}"
    g_end = (f"-{beam_values['GantryStop']:0.0f}" if
             beam_values['GantryStop'] is not None else "")

    return f"{beam.Number} {table_text}{g_start}{g_end}"


def get_3d_beamname(beam, machine, site, add_quality):
    pt_pos = beam.PatientPosition
    near_cardinal = ((beam.GantryAngle % 90) % (90 - BEAM_ANGLE_PROX_LIMIT)
                     < BEAM_ANGLE_PROX_LIMIT)
    norm_angle = ((-1 if 'Feet' in pt_pos else 1) * beam.GantryAngle
                  + (180 if 'Prone' in pt_pos else 0))
    beam_quad = int((((norm_angle + BEAM_ANGLE_PROX_LIMIT) // 90) % 4)
                    + near_cardinal * 4)

    direction_name = BEAMNAME_QUADRANT_TO_NAME[beam_quad]
    if 'Breast' in site:
        inf_jaw = 2 if 'Head' in pt_pos else 3

        is_half_inf = abs(beam.Segments[0].JawPositions[inf_jaw]) < 0.5
        # Breast, check for 4fld and name best we can.
        if is_half_inf:
            direction_name = BEAMNAME_BREAST_SC_PA[int('PO' in direction_name)]
        else:
            # Inferior jaw is not at 0(ish) so this must be the tangents
            # Name with "1 LAO 18x" e.g.
            if add_quality:
                direction_name += f' {beam.BeamQualityId}x'

    return f"{beam.Number} {direction_name}"


def set_beamnames_to_number(beamset):
    name_map = {beam.Name: str(beam.Number) for beam in beamset.Beams}

    for beamname in name_map:
        while name_map[beamname] in name_map:
            # Need to use an intermediary values
            name_map[beamname] += '_'

    for beamname in name_map:
        beamset.Beams[beamname].Name = name_map[beamname]

    for beam in beamset.Beams:
        if '_' in beam.Name:
            beam.Name = str(beam.Number)


def beamname_map(beamset, icase):
    # Example beam name format:
    # "1 RAO"
    # "5 T0 G121-330"
    # "16 T270 G181-359"

    machine = get_machine(beamset)
    site = icase.BodySite

    if (('Arc' in beamset.DeliveryTechnique or
            'Imrt' in beamset.PlanGenerationTechnique)):
        addtableangle = any([beam.CouchRotationAngle != 0 for
                             beam in beamset.Beams])
        name_map = {beam.Number:
                    {'Name': beam.Name,
                     'NewName': get_imrt_beamname(beam, machine,
                                                  addtableangle)}
                    for beam in beamset.Beams}
    else:
        # 3D Conformal
        add_quality = any([beam.BeamQualityId !=
                           beamset.Beams[0].BeamQualityId
                           for beam in beamset.Beams])
        name_map = {beam.Number:
                    {'Name': beam.Name,
                     'NewName': get_3d_beamname(beam, machine,
                                                site, add_quality)}
                    for beam in beamset.Beams}

    return name_map


def rename_beams(beamset, icase, dialog=True, do_rename=True):
    # Example beam name format:
    # "1 RAO"
    # "5 T0 G121-330"
    # "16 T270 G181-359"

    if do_rename:
        try:
            with CompositeAction('Rename all beams in beamset '
                                 f'"{beamset.DicomPlanLabel}"'):

                renumber_beams(beamset, dialog)

                name_map = beamname_map(beamset, icase)

                set_beamnames_to_number(beamset)

                for beam in beamset.Beams:
                    beam.Name = name_map[beam.Number]['NewName']

                if all([beam['Name'] == beam['NewName']
                        for beam in name_map.values()]):
                    # No changes made, bubble out to keep from changing plan
                    raise Warning("Beams alredy correct, No changes made.")
        except Warning as w:
            if dialog:
                Show_OK(w, "Beam Rename")

    else:
        name_map = beamname_map(beamset, icase)

    return {beam['Name']: beam['NewName']
            for beam in name_map.values()
            if beam['Name'] != beam['NewName']}
