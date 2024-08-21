from .external import get_current, LimitedDict
from .points import point
import logging
_logger = logging.getLogger(__name__)


_ROI_OPTS = {'Name': 'Generated',
             'Color': 'White',
             'Type': 'Undefined',
             'TissueName': None,
             'RbeCellTypeName': None,
             'RoiMaterial': None}


def margin_settings(margin, direction='Expand'):
    return {'Type': direction,
            'Superior': margin, 'Inferior': margin,
            'Anterior': margin, 'Posterior': margin,
            'Right': margin, 'Left': margin}


class ROI_Builder():
    # Class to help build new ROIs
    default_opts = None
    pm = None
    strucsets = None

    def __init__(self, patient_model=None, structure_set=None, beam_set=None,
                 default_opts=None, **kwargs):

        if beam_set:
            coll_prop = beam_set.PatientSetup.CollisionProperties
            self.pm = coll_prop.ForPatientModel

            if not structure_set:
                structure_set = coll_prop.ForExaminationStructureSet

        if patient_model:
            self.pm = patient_model

        if not self.pm:
            self.pm = get_current("Case").PatientModel

        if structure_set:
            self.structsets = [structure_set]
        else:
            self.structsets = [s for s in self.pm.StructureSets]

        self.default_opts = LimitedDict(_ROI_OPTS)
        self.default_opts.update(default_opts)
        self.default_opts.update(kwargs)

    def CreateROI(self, name=None, opts=None, **opts_ovr):
        create_opts = LimitedDict(self.default_opts)

        name = name if name else create_opts['Name']

        create_opts.update(opts)
        create_opts.update(opts_ovr)

        create_opts['Name'] = self.pm.GetUniqueRoiName(DesiredName=name)

        roi = self.pm.CreateRoi(**create_opts)
        geometries = {ss.OnExamination: ss.RoiGeometries[roi.Name]
                      for ss in self.structsets}

        return ROI(roi, geometries)

    def GetOrCreateROI(self, name, opts=None, **opts_ovr):
        if name in self.pm.RegionsOfInterest.Keys:
            roi = self.pm.RegionsOfInterest[name]
            geometries = {ss.OnExamination: ss.RoiGeometries[roi.Name]
                          for ss in self.structsets}

            opts = LimitedDict(opts)
            opts.update(opts_ovr)

            opts.limiter = {attr for attr in dir(roi) if
                            not attr.startswith('_') and not callable(attr)}

            for attr_in in opts:
                setattr(roi, attr_in, opts[attr_in])

            return ROI(roi, geometries)
        else:
            return self.CreateROI(name, opts, **opts_ovr)


class ROI():
    # ROI helper class to store all useful functions in an easy place
    def __init__(self, roi, context=None):
        self._roi = roi
        self._geometries = {}

        if hasattr(roi, 'OfRoi'):
            # Passed an ROI geometry
            self._roi = roi.OfRoi
            if context is None:
                self._geometries[get_current('Examination')] = roi
                return

        if context and hasattr(context, 'RoiGeometries'):
            geom = context.RoiGeometries[self.Name]
            self._geometries[context.OnExamination] = geom
        elif context:
            try:
                self._geometries.update(context)
            except TypeError:
                self._geometries[get_current('Examination')] = context
        else:
            self._geometries[get_current('Examination')] = None

    def create_box(self, size=1, center=0, exam=None, **kwargs):
        params = LimitedDict({'Size': point(size),
                              'Center': point(center),
                              'Examination': None,
                              'Representation': 'TriangleMesh',
                              'VoxelSize': None})

        params.update(kwargs)

        if exam and exam in [exam.Name for exam in self._geometries]:
            exams = [lexam for lexam in self._geometries if lexam.Name == exam]
        elif exam:
            try:
                lexams = list(iter(exam))
            except TypeError:
                lexams = [exam]

            exams = []
            for exam in lexams:
                if hasattr(exam, 'Name') and hasattr(exam, 'EquipmentInfo'):
                    exams += [exam]
                elif isinstance(exam, str):
                    exams += [lexam for lexam in self._geometries
                              if lexam.Name == exam]
        else:
            exams = self._geometries.keys()

        for exam in exams:
            params['Examination'] = exam
            self._roi.CreateBoxGeometry(**params)

    def marginate(self, source_roi, margin):
        margin_opts = {'Examination': None,
                       'MarginSettings': margin_settings(margin),
                       'SourceRoiName': source_roi}
        for exam in self._geometries:
            margin_opts['Examination'] = exam
            self.CreateMarginGeometry(**margin_opts)

    def ab_subtraction(self, exam=None, rois_a=None, rois_b=None):
        self.ab_operation(exam, rois_a, rois_b, operation='Subtraction')

    def ab_intersect(self, exam=None, rois_a=None, rois_b=None):
        self.ab_operation(exam, rois_a, rois_b, operation='Intersection')

    def ab_operation(self, exam, rois_a, rois_b, operation):
        VALID_OPS = ['None',
                     'Union',
                     'Intersection',
                     'Subtraction']
        if operation and operation not in VALID_OPS:
            operation = None
        if not exam and len(self._geometries) == 1:
            exam = [k for k in self._geometries.keys()][0]
        if not isinstance(rois_a, list):
            rois_a = [rois_a]
        if not isinstance(rois_b, list):
            rois_b = [rois_b]

        # Convert any passed ROI or RS ROI into a Name
        rois_a = [roi.Name if hasattr(roi, 'Name') else roi for roi in rois_a]
        rois_b = [roi.Name if hasattr(roi, 'Name') else roi for roi in rois_b]

        exp_a = {'Operation': 'Union',
                 'SourceRoiNames': rois_a,
                 'MarginSettings': margin_settings(0)}

        exp_b = {'Operation': 'Union',
                 'SourceRoiNames': rois_b,
                 'MarginSettings': margin_settings(0)}

        create_geom_opts = {'Examination': exam,
                            'Algorithm': 'Auto',
                            'ExpressionA': exp_a,
                            'ExpressionB': exp_b,
                            'ResultOperation': operation,
                            'ResultMarginSettings': margin_settings(0)}

        self._roi.CreateAlgebraGeometry(**create_geom_opts)

    def check_overlap(self, rois_a, rois_b):
        for exam in self._geometries:
            self.ab_intersect(exam, rois_a, rois_b)
        return all([g.HasContours() for g in self.geoms])

    def importSTL(self, file, matrix, **opts):
        for geom in self.geoms:
            geom.ImportRoiGeometryFromSTL(FileName=file,
                                          TransformationMatrix=matrix,
                                          **opts)

    @property
    def geoms(self):
        for geom in self._geometries.values():
            yield geom

    @property
    def Name(self):
        return self._roi.Name

    @Name.setter
    def Name(self, Name):
        self._roi.Name = Name

    def DeleteRoi(self):
        del self._geometries
        return self._roi.DeleteRoi()

    def DeleteGeometry(self):
        for geom in self.geoms:
            geom.DeleteGeometry()
