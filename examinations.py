from .external import (dcmread, uid, SuspendCompositeAction, obj_name,
                       get_unique_name)

from datetime import datetime

import tempfile

import os
from copy import deepcopy

import logging
_logger = logging.getLogger(__name__)


_SCRIPTED_EXPORT_FOR_EXAM = {
    'AnonymizationSettings': None,
    'Connection': None,
    'ExportFolderPath': None,
    'Examinations': [],
    'RtStructureSetsForExaminations': [],
    'RtStructureSetsReferencedFromBeamSets': [],
    'BeamSets': [],
    'RtRadiationSetForBeamSets': [],
    'RtRadiationsForBeamSets': [],
    'PhysicalBeamSetDoseForBeamSets': [],
    'EffectiveBeamSetDoseForBeamSets': [],
    'PhysicalBeamDosesForBeamSets': [],
    'EffectiveBeamDosesForBeamSets': [],
    'SpatialRegistrationForExaminations': [],
    'DeformableSpatialRegistrationsForExaminations': [],
    'TreatmentBeamDrrImages': [],
    'SetupBeamDrrImages': [],
    'DicomFilter': None,
    'IgnorePreConditionWarnings': True,
    'RayGatewayTitle': None,
    # 'TransferSyntaxOverride': None,
    'ExportAsBdspDose': False
}

_IMPORT_PARAMS = {
    'Path': None,
    'SeriesOrInstances': [],
    'CaseName': None
}


_EXCLUDED_ROI_TYPES = ['Support', 'Bolus']

SERIES_ADD = 31415


def duplicate_exam(patient, icase, exam_in, copy_structs=True,
                   exam_name_out=None):
    export_params = deepcopy(_SCRIPTED_EXPORT_FOR_EXAM)

    new_uid_root = uid.generate_uid()[0:-13]
    # Raystation throws a fit is the series UID is 64 characters long
    new_series_uid = uid.generate_uid('.'.join([new_uid_root, '0', '']))[0:-2]
    new_image_uid_root = '.'.join([new_uid_root, '1'])

    with tempfile.TemporaryDirectory() as tempdir:
        export_params['ExportFolderPath'] = tempdir
        export_params['Examinations'].append(exam_in.Name)

        _logger.debug(f"{export_params}")
        icase.ScriptableDicomExport(**export_params)

        _logger.info(f"Saved exam to {tempdir}.")

        study_uid = None
        patient_id = None

        # TODO: Modify InstanceCreationDate, InstancCreationTime, SeriesNumber,
        # etc. as well.

        for imgn, fn in enumerate(os.listdir(tempdir)):
            full_fn = os.path.join(tempdir, fn)
            if os.path.isfile(full_fn):
                print(full_fn)

                new_image_uid = uid.generate_uid('.'.join([new_image_uid_root,
                                                           str(imgn), '']))

                img = dcmread(full_fn)

                if not study_uid:
                    study_uid = img.StudyInstanceUID
                    patient_id = img.PatientID

                img.SeriesInstanceUID = new_series_uid
                img.SOPInstanceUID = new_image_uid
                img.SeriesNumber += SERIES_ADD

                # Indicate that this is a SECONDARY image (from NMEA: "is the
                #   image a SECONDARY Image; an image created after the initial
                #   patient examination"
                img.ImageType[1] = "SECONDARY"

                now = datetime.now()

                img.InstanceCreationDate = now.strftime('%Y%m%d')
                img.InstanceCreationTime = now.strftime('%H%M%S.%f')

                _logger.info(f"Writing {full_fn} with "
                             f"new SOPUID {new_image_uid}")
                img.save_as(full_fn)

        series_info = {'PatientID': str(patient_id),
                       'StudyInstanceUID': str(study_uid),
                       'SeriesInstanceUID': new_series_uid}

        import_params = deepcopy(_IMPORT_PARAMS)
        import_params['Path'] = tempdir.replace('\\', '/')
        import_params['SeriesOrInstances'].append(series_info)
        import_params['CaseName'] = icase.CaseName
        _logger.debug(f"{import_params=}")
        with SuspendCompositeAction("Importing Dicom data"):
            warnings = patient.ImportDataFromPath(**import_params)
        if warnings:
            _logger.warning(f'Import warnings: {warnings}')

    exams_out = [exam for exam in icase.Examinations
                 if exam.Series[0].ImportedDicomUID == new_series_uid]

    if not exams_out:
        raise Exception("Failed to find new exam in case")

    exam_out = exams_out[0]

    exam_name_out = exam_name_out if exam_name_out else obj_name(exam_in)
    exam_out.Name = get_unique_name(exam_name_out, icase.Examinations)

    if copy_structs:
        roi_names = [roi.Name for roi in icase.PatientModel.RegionsOfInterest
                     if roi.Type not in _EXCLUDED_ROI_TYPES]
        copy_params = {
            'SourceExamination': exam_in,
            'TargetExaminationNames': [exam_out.Name],
            'RoiNames': roi_names,
            'ImageRegistrationNames': [],
            'TargetExaminationNamesToSkipAddedReg': [exam_out.Name]
        }
        icase.PatientModel.CopyRoiGeometries(**copy_params)

    return exam_out
