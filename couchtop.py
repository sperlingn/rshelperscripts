from re import compile as re_compile
from operator import attrgetter
from ast import literal_eval
from struct import unpack_from
from inspect import getargspec

from .points import (point, BoundingBox, Image_Series, AffineMatrix)
from .case_comment_data import (get_case_comment_data, set_case_comment_data,
                                get_data)
from .dosetools import invalidate_structureset_doses

from .external import (get_current, CompositeAction, Show_YesNo,
                       ArgumentOutOfRangeException,
                       pick_machine, pick_plan, pick_exam)

from .roi import ROI_Builder, ROI

import logging

_logger = logging.getLogger(__name__)

CT_DEFAULT_Y = 20.8
CT_DEFAULT_Y_TOLERANCE = 1
CT_Top_NegativeX = -24
HN_SEARCH_DELTA = 1.

HN_SITES = {"Brain",
            "Head & Neck"}

NON_HN_SITES = {"Left Breast",
                "Right Breast",
                "Thorax",
                "Abdomen",
                "Pelvis",
                "Left Upper Extremity",
                "Right Upper Extremity",
                "Left Lower Extremity",
                "Right Lower Extremity"}

SITE_SHIFT = {"Left Breast": -45.,
              "Right Breast": -45.,
              "Thorax": -30.,
              "Abdomen": -20.,
              "Pelvis": 0.}

MACHINE_SEARCHES = {'Edge':     [['brain', False],  # Brain usually on Edge
                                 ['prostate', False],  # Prostate usually Edge
                                 ['sbrt', True],  # SBRT usually on Edge
                                 ['srs', True]],  # SRS on Edge
                    'TrueBeam': [['breast', True],  # Breast on TB
                                 ['lns', True],  # LNs on TB (grabs prost+LNs)
                                 ['h&n', True],  # H&N always on TB
                                 ['arm', True],  # Extremities on TB
                                 ['extremity', True],
                                 ['whole', True]]}  # Whole brain on TB

PATIENT_ORIENTATIONS = {'TrueBeam': ['FFS']}

DEFAULT_MACHINE = 'TrueBeam'

# Tabletops of known offsets.  Surface ROI is the roi whose upper surface is
# at the height of the CT tabletop.  ROI_Names will be completed when brought
# into the collection.
KNOWN_TOPS = {
    'TrueBeam Couch Model':
        {'surface_roi': 'Surface Shell - TrueBeam',
         'default_offset': {'x': 0., 'y': 0., 'z': 0.},
         'tx_machines': 'TrueBeam'},
    'Edge Couch Model':
        {'surface_roi': 'Outer Shell - Edge',
         'default_offset': {'x': 0., 'y': 0., 'z': 0.},
         'tx_machines': 'Edge'},
    'Edge Head & Neck Model':
        {'surface_roi': 'Outer Shell - Edge H&N',
         'default_offset': {'x': -.1, 'y': -2.33, 'z': 0.4},
         'tx_machines': 'Edge'},
    'TrueBeam Head & Neck Model':
        {'surface_roi': 'Surface Shell - TrueBeam',
         'default_offset': {'x': -0.484, 'y': -2.25, 'z': 0.452},
         'tx_machines': 'TrueBeam'}
}


"""
H&N Board design:
     O ---------# 0
                | = 15.0 cm center to center
                |
  O     O ------#+- 11.2 cm
                | = 12.8 cm center to center
 O       O -----#+- 11.6 cm

 Circle diameter: 2.7 cm

 Simple search finds only the top circle.
 Complex search tries to find four circles.

"""
HN_H1_TO_H2_Z = 15.0
HN_H2_X = 11.2
HN_H_SEP = 12.8
HN_H3_X = 11.6
HN_H_DIAM = 3.4
HN_H1_TO_BOARD_Z = 0.85


# For couch height, appears to always have tabletop at 208mm (-20.8 in RS)
#  Possible tag of interest might include 01F1,100C to correct for image
#  reconstruction center, but might not be relevant for oncology (scans must
#  be centered).


# For regular couch top, the top of the couch should be set to -20.8 in RS.

# For the H&N board, on the TB, the top of the Couch structure should be at
# -20.8 in RS, and the H&N board should be adjusted from that.
#  For the edge, H&N board top should be set to align with the H&N board on the
#  image.  Adjustment to be determined.


# Data stored in DICOM tag (01F7,1027) on Philips PET/CT Simulator (as a
# c-style struct:
"""
struct DCM_TAG_01F7_1027
{ // All values Little Endian in this data, likely depends on 0002,0010
    double CouchLong ;              // Absolute Couch logitudinal position for
                                    // this slice in mm
    UInt64 msSinceAcquisitionTime ; // Number of ms since 0008,0032
    UInt64 InstanceNumber ;         // Slice number
    UInt64 PreviousInstanceNumber ; // Instance number for preceding slice
    UInt64 Unknown_1 ;              // Unknown, so far appears to always be 0
}

"""

# DICOM Search
PRIV_01F7_1027 = (0x01F7, 0x1027)
HEURISTIC_OFFSET = 1526


def guess_couchtop_z(series):
    """
    Guesses the z coordinate of the couch top based on specific dicom tags.
    Tags don't currently populate correctly, so work on reading them by hand.
    """
    try:

        img_dcm = series.DICOM

        CZ_raw = img_dcm[PRIV_01F7_1027].value

        couchZabs = unpack_from("f", CZ_raw)[0]
        sliceloc = img_dcm.SliceLocation.real
        ipp = img_dcm.ImagePositionPatient[2].real

        cdist = sliceloc - couchZabs
        abs_couch_pos = cdist + HEURISTIC_OFFSET
        ippscale = ipp / sliceloc

        couch_z = (abs_couch_pos * ippscale) / 10.
        _logger.debug('Locals:\n\t'
                      f'{CZ_raw=}\n\t'
                      f'{couchZabs=}\n\t'
                      f'{sliceloc=}\n\t'
                      f'{ipp=}\n\t'
                      f'{cdist=}\n\t'
                      f'{abs_couch_pos=}\n\t'
                      f'{ippscale=}\n\t'
                      f'{couch_z=}')

        return couch_z
    except Exception:
        _logger.exception("Problem reading CT data")
        return None


def guess_board_x_center(series, couch_y):
    search_y = couch_y + HN_SEARCH_DELTA

    init_guess = point(x=HN_H2_X, y=search_y)
    # TODO: Put this in a try-except and fail to a new z for
    # finding the width.
    # Need to account for top hole not being on image
    guess_edges = series.find_edges(search_start=init_guess,
                                    direction='-z', z_avg=0.05)
    guess_holes = series.holes_by_width(edges=guess_edges,
                                        width=HN_H_DIAM,
                                        tolerance=1.)
    if guess_holes:
        init_guess.z = guess_holes[-1].center.z
    else:
        init_guess.z = (series.Corner.z
                        + (max(series.SlicePositions)/2))

    width_edges = series.find_edges(search_start=init_guess,
                                    direction='x')

    if width_edges:
        x_offset = (width_edges[-1][1].x + width_edges[0][0].x)/2
    else:
        x_offset = 0
        _logger.debug(f"{x_offset=}")
        return x_offset


def guess_machine(icase):
    """
    Guess the machine based on the icase.BodySite.  Since we usually only get
        to this when we don't have a plan, only try to used values present in
        the case (BodySite, CaseName, Diagnosis, Comments?)
    """
    snd = (icase.BodySite + icase.CaseName + icase.Diagnosis).lower()
    machine = DEFAULT_MACHINE
    for mach, strings in MACHINE_SEARCHES.items():
        for s in strings:
            if s[0] in snd:
                if s[1]:  # If we have a definitive answer, return now
                    return mach
                else:  # Answer might be overriden later, set and continue
                    machine = mach
    return pick_machine(default=machine).Alias


def test_for_hn(icase, series):
    """
    Test the case for if it is likely to have a H&N board used.
    Simple tests first (e.g. if the case is a pelvis, return False) followed by
        potentially searching for indicators of H&N board from tabletop
        position.
        Also test for patient orientation.  If FFS, assume it isn't H&N.
    """
    if icase.BodySite in HN_SITES:
        return True
    elif icase.BodySite in NON_HN_SITES:
        return False
    else:
        # More complicated, need to test if there is a HN board.
        # For now, warn using warnings
        msg = ("Couldn't determine if this is a H&N patient from site '{}'\n"
               "Should this be an H&N patient?").format(icase.BodySite)
        title = "H&N Board in use?"
        isHN = Show_YesNo(msg, title, ontop=True)
        return bool(isHN)

        _logger.warning("Testing for H&N board by searching image is not "
                        f"implemented yet.  Treatment Site {icase.BodySite} "
                        "is insufficient for use in determination.")
    return False


def find_table_height(series, resolution=None, search_start=None,
                      x_avg=None, z_avg=1., default=CT_DEFAULT_Y):
    """
    Find the table surface from image.
    """
    # Search start from CT_Top_NegativeX, let it find the middle for z, and
    # we are searching in y.
    search_start = search_start if search_start else {'x': CT_Top_NegativeX,
                                                      'y': None,
                                                      'z': None}
    x_avg = x_avg if x_avg else series.PixelSize.x
    y_avg = resolution if resolution else None

    # Minimum value for a peak to be considered real
    threshold = -200

    # For any prone images, get the other side of the edge
    is_rising = series.ColumnDirection.y == -1

    try:
        edge_pairs = series.find_edges(search_start=search_start,
                                       x_avg=x_avg,
                                       y_avg=y_avg,
                                       z_avg=z_avg,
                                       direction='-y',
                                       threshold=threshold)

        _logger.debug(f"{edge_pairs=}")
        for edge_pair in edge_pairs:
            edge = edge_pair[not is_rising]
            # Only return if it seems reasonable.
            if abs(CT_DEFAULT_Y - edge.y) <= CT_DEFAULT_Y_TOLERANCE:
                return edge.y

    except (ValueError, IndexError, SystemError, TypeError):
        _logger.exception("Couldn't find top height, using default.")

    return default


def get_or_find_table_height(series, /, icase=None, resolution=None,
                             search_start=None, x_avg=None, z_avg=1.,
                             default=CT_DEFAULT_Y, force=False, store=True):

    fth_kwarg_list, _, _, _ = getargspec(find_table_height)
    fth_kwargs = {k: v for k, v in locals().items() if k in fth_kwarg_list}

    if not icase:
        return find_table_height(**fth_kwargs)

    case_data = get_case_comment_data(icase)

    case_couch_y = case_data.get('couch_y', {})

    if series.UID in case_couch_y and not force:
        return case_couch_y[series.UID]
    else:
        couch_y = find_table_height(**fth_kwargs)
        case_couch_y[series.UID] = couch_y

    if store:
        set_case_comment_data(name='couch_y', data=case_couch_y, icase=icase)

    return couch_y


class CouchTop(object):
    Name = ""

    ROI_Names = None
    default_offset = (0, 0, 0)
    tx_machines = None
    surface_roi = None
    _tx_machines_set = None
    _board_offset = None

    roi_geometries = None
    template = None
    isValid = False
    _desc_re = re_compile(r'(?:Offset:\s(?P<Offset>\d+)'
                          r'|Tx Machines:\s(?P<TxMachines>.*)$'
                          r'|Surface:\s"(?P<Surface>[^"]+)")')

    _updateable = ['surface_roi', 'tx_machines', 'default_offset']

    _bounding_box = None

    inActiveSet = False

    def __init__(self, Name,
                 default_offset=None, surface_roi=None, tx_machines=None,
                 patient_db=get_current("PatientDB"), structure_set=None):
        self.Name = Name
        _logger.debug(f"Building CouchTop with: {Name=}, {default_offset=}, "
                      f"{surface_roi=}, {tx_machines=}")

        try:
            self.template = patient_db.LoadTemplatePatientModel(
                templateName=Name, lockMode='Read')

            rois = self.template.PatientModel.RegionsOfInterest
            self.ROI_Names = {roi.Name for roi in rois}

            self._build_from_description()

            params = {k: v for k, v in locals().items()
                      if k in self._updateable}
            self.update_params(**params)

            self.isValid = self.surface_roi in self.ROI_Names

            if structure_set:
                self.update()

        except SystemError:
            # No template in patient_db by this name.
            pass

    def update_params(self, **kwargs):
        # Filter against those parameters that we have deemed safe to update.
        updated = False
        try:
            for k in (k for k in kwargs if k in self._updateable
                      and kwargs[k] is not None):
                setattr(self, k, kwargs[k])
                _logger.debug(f"Updated {self.Name}.{k}={kwargs[k]}")
                updated = True
        except (ValueError, KeyError, IndexError):
            _logger.debug("Error updating parameters.", exc_info=True)

        return updated

    def _build_from_description(self):  # noqa: C901
        if self.template.Description:
            # First see if there is data stored in base64
            data = get_data(self.template.Description)
            if data:
                _logger.debug(f"Found stored params in description {data=}")
                if self.update_params(**data):
                    return

            for m in self._desc_re.finditer(self.template.Description):
                if m.group('Surface'):
                    self.surface_roi = m.group('Surface')
                if m.group('Offset'):
                    try:
                        offset = literal_eval(m.group('Offset'))
                        if isinstance(offset, float):
                            self.default_offset = point(y=offset)
                        elif isinstance(offset, tuple):
                            self.default_offset = point(*offset)
                    except (ValueError, TypeError, SyntaxError,
                            MemoryError, RecursionError):
                        self.default_offset = point()
                    except Exception as e:
                        _logger.exception(e)
                if m.group('TxMachines'):
                    self.tx_machines = m.group('TxMachines')

    @staticmethod
    def machine_set(inmachinename):
        try:
            inset = inmachinename._tx_machines_set
            return inset
        except AttributeError:
            pass

        if isinstance(inmachinename, str):
            name = inmachinename.lower()
        else:
            name = '\n'.join(inmachinename).lower()

        # replace all newlines with ',', get rid of spaces, then split on ','
        nameiter = name.replace('\n', ',').replace(' ', '').split(',')
        return set(nameiter)

    @property
    def _tx_machines_set(self):
        return self.machine_set(self.tx_machines)

    @property
    def isHN(self):
        return "HN" in "".join(self.ROI_Names).replace("&", "")

    @property
    def Top_offset(self):
        try:
            x_offset = self.boundingbox.center.x
            _logger.debug(f"{self.default_offset=}, {x_offset=}")
            offset = point(self.default_offset)
            offset.x -= x_offset
            return offset
        except Exception as e:
            _logger.info(str(e), exc_info=True)
            return self.default_offset

    @property
    def boundingbox(self):
        if self._bounding_box is None:
            self._bounding_box = BoundingBox(self.roi_geometries.values())
            _logger.debug(f"Rebuilding...\n\t{self._bounding_box}")
            try:
                _logger.debug('\n\t'.join('{}: {}'.format(g.OfRoi.Name,
                                                          g.GetBoundingBox())
                                          for g in
                                          self.roi_geometries.values()))
            except Exception:
                pass
        return self._bounding_box.copy()

    def get_transform(self, structure_set, offset):
        # get from position of top, need ROIs to be present.

        pt_pos = structure_set.OnExamination.PatientPosition

        if pt_pos[2] == 'S':
            pt = offset + self.Top_offset - point.Y() * self.boundingbox.lower
        elif pt_pos[2] == 'P':
            pt = offset + self.Top_offset - point.Y() * self.boundingbox.upper
        _logger.debug("Transform calculation.\n\t"
                      f'pt = {offset} + {self.Top_offset} - '
                      f'point.Y() * {self.boundingbox.lower}\n\t'
                      f'{pt = }')

        transform = AffineMatrix(pt)

        _logger.debug(f'{transform}')

        return transform.rs_matrix

    def _apply_transform(self, structure_set, transform):
        for roi in self.ROI_Names:
            structure_set.RoiGeometries[roi].OfRoi.TransformROI3D(
                Examination=structure_set.OnExamination,
                TransformationMatrix=transform)

        self._bounding_box = None

    def correct_orientation(self, structure_set, icase):
        pt_pos = structure_set.OnExamination.PatientPosition
        couch_pos = self.template.StructureSetExaminations[0].PatientPosition

        if pt_pos not in ('HFS', 'FFS', 'HFP', 'FFP'):
            raise RuntimeError(f"Patient orientation '{pt_pos}'"
                               " is not supported at this time.")

        if pt_pos == couch_pos:
            return

        amat = AffineMatrix()
        if pt_pos[0] != couch_pos[0]:
            # HFx vs FFx, yaw 180
            amat.yaw = 180.

        if pt_pos[2] != couch_pos[2]:
            # xxS vs xxP, roll 180
            amat.roll = 180.

        transform = amat.rs_matrix

        self._apply_transform(structure_set, transform)

    @property
    def create_opts(self):
        source_exam_name = self.template.StructureSetExaminations[0].Name
        return {'SourceTemplate': self.template,
                'SourceExaminationName': source_exam_name,
                'SourceRoiNames': list(self.ROI_Names),
                #  Rest are default options
                'SourcePoiNames': [],
                'AssociateStructuresByName': True,
                'TargetExamination': None,
                'InitializationOption': "AlignImageCenters"}

    def add_to_case(self, icase=None, examination=None,
                    couch_y=CT_DEFAULT_Y, match_z=True, force_z=None):
        if icase is None:
            icase = get_current("Case")
        if examination is None:
            examination = icase.PatientModel.Examinations[0]

        structure_set = icase.PatientModel.StructureSets[examination.Name]
        case_data = get_case_comment_data(icase)

        if 'board_offset' in case_data:
            CouchTop._board_offset = case_data['board_offset']

        with CompositeAction("Add couch '{}' to plan.".format(self.Name)):
            create_opts = self.create_opts
            create_opts['TargetExamination'] = examination
            icase.PatientModel.CreateStructuresFromTemplate(**create_opts)
            self._bounding_box = None

            self.update(structure_set)

            self.correct_orientation(structure_set=structure_set,
                                     icase=icase)

            self.move_rois(structure_set=structure_set,
                           couch_y=couch_y,
                           match_z=match_z,
                           force_z=force_z,
                           icase=icase)

            self.trim_rois(icase, structure_set)

        if 'board_offset' not in case_data and CouchTop._board_offset:
            case_data['board_offset'] = CouchTop._board_offset
            set_case_comment_data(data=case_data,
                                  icase=icase,
                                  replace=True)

    def trim_rois(self, icase, structure_set, keeptop=False):
        if not structure_set.OutlineRoiGeometry:
            _logger.warning("No patient outline, not trimming couch model.")
            return False

        patient_bb = BoundingBox(structure_set.OutlineRoiGeometry)
        box_bb = self.boundingbox + patient_bb

        box_bb.limitz(patient_bb, self.isHN or keeptop)

        roi_builder = ROI_Builder(icase.PatientModel, structure_set)

        with CompositeAction(f"Trim couch ROIs ({self.Name})"):
            box = roi_builder.CreateROI('box')
            box.create_box(**box_bb.box_geometry_params(margin=0))
            for roi in self._rois.values():
                roi.ab_intersect(rois_a=roi, rois_b=box)

            if _logger.level != logging.DEBUG:
                box.DeleteRoi()

            surface = self._rois[self.surface_roi]
            for roi in self._rois.values():
                if roi == surface:
                    continue
                roi.ab_subtraction(rois_a=roi, rois_b=surface)

            self._bounding_box = None

    def update(self, structure_set):
        struct_rois = structure_set.RoiGeometries.Keys
        self._rois = {roi.OfRoi.Name: ROI(roi, structure_set) for roi in
                      structure_set.RoiGeometries
                      if roi.OfRoi.Name in self.ROI_Names}
        self.roi_geometries = {roi_name: structure_set.RoiGeometries[roi_name]
                               for roi_name in self.ROI_Names
                               if roi_name in struct_rois}
        self._bounding_box = None

    @classmethod
    def get_board_offset_from_image(cls, series, couch_y):
        """
        Searches for coordinate of top of board.
        Simple search looks only for the central hole.
        Complex search tries to identify the side holes as well and estimate
          based on the positions of the 4 side holes.  This method is preferred
          as CT scans often cut off the top of the board.
        """
        if cls._board_offset and series.UID in cls._board_offset:
            _logger.debug(f"Found offset in class: {cls._board_offset}")
            return cls._board_offset[series.UID].copy()

        z = series.Corner.z + max(series.SlicePositions)

        # To start, get a guess at the first hole, then find the center
        # of the H&N Board in the X direction.  We will then move the
        # search points based on any shift in this image.

        try:
            _logger.debug(f"Searching for board center at height {couch_y}")
            x_offset = guess_board_x_center(series, couch_y)
            _logger.debug(f"Found board center at {x_offset}")
        except (TypeError, ValueError, IndexError, Warning):
            _logger.warning("Couldn't find center of board, assuming 0.")
            x_offset = 0.

        search_y = couch_y - HN_SEARCH_DELTA
        try:
            search_point = point(x=x_offset, y=search_y)
            _logger.debug(f"Searching for top center hole at {search_point}")
            # Search for top center hole (tc)
            tc_edges = series.find_edges(search_start=search_point,
                                         direction='-z', z_avg=0.05)

            tc_holes = series.holes_by_width(edges=tc_edges,
                                             width=HN_H_DIAM,
                                             tolerance=0.1)

            tc_holes_s = sorted(tc_holes, key=attrgetter('z'), reverse=True)

            tc_hole_z = tc_holes_s[0].z

            _logger.debug(f"Found start of board at {tc_holes_s[0]}.")

            # Naively assume that the first point is the start of the
            # board
            z = tc_hole_z + HN_H1_TO_BOARD_Z
        except Exception:
            _logger.warning("Couldn't find central hole, trying other holes",
                            exc_info=True)
            try:
                # Ignore the central hole and look instead for the side holes.
                tp_search_start = point(x=HN_H2_X + x_offset, y=search_y)
                tn_search_start = point(x=-HN_H2_X + x_offset, y=search_y)

                bp_search_start = point(x=HN_H3_X + x_offset, y=search_y)
                bn_search_start = point(x=-HN_H3_X + x_offset, y=search_y)

                # Logic will now start with each rising edge in tp_search and
                # look for a falling edge that is the right distance away
                # (HN_H_DIAM +- some margin)  If that works, it will try to
                # find corresponding points that are within the sensible
                # distances for each other hole.
                tp_edges = series.find_edges(search_start=tp_search_start,
                                             direction='-z', z_avg=0.05)
                tn_edges = series.find_edges(search_start=tn_search_start,
                                             direction='-z', z_avg=0.05)
                bp_edges = series.find_edges(search_start=bp_search_start,
                                             direction='-z', z_avg=0.05)
                bn_edges = series.find_edges(search_start=bn_search_start,
                                             direction='-z', z_avg=0.05)

                tp_holes = series.holes_by_width(edges=tp_edges,
                                                 width=HN_H_DIAM,
                                                 tolerance=1.)
                tn_holes = series.holes_by_width(edges=tn_edges,
                                                 width=HN_H_DIAM,
                                                 tolerance=1.)
                bp_holes = series.holes_by_width(edges=bp_edges,
                                                 width=HN_H_DIAM,
                                                 tolerance=1.)
                bn_holes = series.holes_by_width(edges=bn_edges,
                                                 width=HN_H_DIAM,
                                                 tolerance=1.)

                agz = attrgetter('z')

                tp_holes_s = sorted(tp_holes, key=agz, reverse=True)
                tn_holes_s = sorted(tn_holes, key=agz, reverse=True)
                bp_holes_s = sorted(bp_holes, key=agz, reverse=True)
                bn_holes_s = sorted(bn_holes, key=agz, reverse=True)

                tp_hole_z = tp_holes_s[0].z
                tn_hole_z = tn_holes_s[0].z

                top_hole_z = (tp_hole_z + tn_hole_z) / 2

                bp_hole_z = [h.z for h in bp_holes_s
                             if h.z < top_hole_z - (2 * HN_H_DIAM)][0]
                bn_hole_z = [h.z for h in bn_holes_s
                             if h.z < top_hole_z - (2 * HN_H_DIAM)][0]

                bot_hole_z = (bp_hole_z + bn_hole_z) / 2

                if _logger.level <= logging.DEBUG:
                    global __DEBUG__TB__
                    __DEBUG__TB__ = locals()

                # Check a few features to make sure that the holes are sensible
                if ((abs(bn_hole_z - bp_hole_z) > HN_H_DIAM / 2
                     or abs(tn_hole_z - tp_hole_z) > HN_H_DIAM / 2)):
                    # Holes aren't aligned with eachother, not the same holes
                    # or the board is way to rotated, fail out.
                    _logger.warning(f"Holes not aligned: "
                                    f"{tn_hole_z}, {tp_hole_z}, "
                                    f"{bn_hole_z}, {bp_hole_z}")
                    raise Warning("Holes not aligned in Z.")
                else:
                    _logger.debug("Holes are aligned in the Z direction to "
                                  f"within {HN_H_DIAM/2} distance.")

                if abs(abs(top_hole_z - bot_hole_z) - HN_H_SEP) > HN_H_DIAM:
                    # Holes aren't spaced right, no further checking yet
                    # TODO: Possibly look for additional hole pairs that do
                    # match.
                    _logger.warning(f"Holes not spaced correctly:"
                                    f" {top_hole_z}, {bot_hole_z}")
                    raise Warning("Holes not spaced correctly.")
                else:
                    _logger.debug("Holes appear to be spaced correctly.")

                # Finally, these look right so return the location of the top
                # of the board from these holes.  Include the distance from
                # hole center of the top hole to the edge of the board.
                _logger.debug("Holes for distance:\n\t"
                              f"{tn_hole_z=}, {tp_hole_z=},\n\t"
                              f"{bn_hole_z=}, {bp_hole_z=}")

                z = (((top_hole_z + bot_hole_z + HN_H_SEP) / 2)
                     + HN_H1_TO_H2_Z + HN_H1_TO_BOARD_Z)
            except IndexError:
                raise Warning("Failed to find correct holes.")
                pass

        offset = point(x_offset, 0, z)
        _logger.debug(f"{offset=}")
        # MAGIC: Store the search result in the class so we don't have to do it
        # again.
        if not cls._board_offset:
            _logger.debug("Creating cls._board_offset")
            cls._board_offset = {}

        _logger.debug(f"Storing cls._board_offset[series] = {offset}")
        cls._board_offset[series.UID] = offset.copy()

        return offset

    def get_hn_offset(self, series, couch_y, ct_z):
        _logger.debug(f"Had {ct_z=}, find x_offset")
        try:
            return self.get_board_offset_from_image(series, couch_y)
        except (TypeError, ValueError, Warning):
            # Couldn't find the board, so make sure we don't remove any
            # of the couch by setting the bottom edge to be at the
            # bottom of the CT.
            _logger.warning("Couldn't find H&N board position."
                            "  Board should be positioned manually.")
            pass

        offset = point()
        try:
            offset.x = guess_board_x_center(series, couch_y)
        except (TypeError, ValueError):
            _logger.warning("Couldn't center H&N board position.")

        if ct_z:
            offset.z = ct_z

        return offset

    def get_offset(self, structure_set, couch_y, icase, force_z=None):
        if force_z is None:
            examination = structure_set.OnExamination
            series = Image_Series(examination.Series[0])

            couch_bb = self.boundingbox

            ct_z = guess_couchtop_z(series)

            # Default to move the bottom of the board to the bottom of the CT
            offset = point.Z() * (couch_bb.upper.z +
                                  (series.minz - couch_bb.lower.z))

            if self.isHN:
                offset = self.get_hn_offset(series, couch_y, ct_z)
            elif ct_z:
                offset.z = ct_z
            else:
                # Not H&N, not simple search, figure out from body site?
                if icase is None:
                    icase = get_current("Case")

                if icase.BodySite in SITE_SHIFT:
                    _logger.debug("Can't determine origin from CT, shifting "
                                  "based on treatment site: "
                                  f"{icase.BodySite} = "
                                  f"{SITE_SHIFT[icase.BodySite]}")
                    offset.z += SITE_SHIFT[icase.BodySite]

            offset -= point.Z() * couch_bb.upper.z
        else:
            try:
                offset = point(z=float(force_z))
            except (ValueError, TypeError):
                offset = point(force_z)

        offset += point.Y() * couch_y
        _logger.debug(f"{offset=}")
        return offset

    def move_rois(self, structure_set, couch_y=CT_DEFAULT_Y,
                  match_z=True, force_z=None, icase=None):

        # Invalidate to force recomputing of boundingbox
        self._bounding_box = None

        offset = self.get_offset(structure_set,
                                 couch_y, icase, force_z)

        if not match_z:
            offset.z = 0

        transform = self.get_transform(structure_set, offset)

        self._apply_transform(structure_set, transform)

    def remove_from_case(self, remove_existing=True):
        if self.roi_geometries:
            with CompositeAction("Remove {self.Name} couch from case."):
                for geom in self.roi_geometries.values():
                    if geom.PrimaryShape:
                        if remove_existing:
                            geom.DeleteGeometry()
                        else:
                            geom.OfRoi.DeleteRoi()

    def machine_matches(self, inmachinename):
        inmachines = self.machine_set(inmachinename)
        if not inmachines:
            return False

        # First check if there is an exact name matching between the two sets.
        if inmachines & self._tx_machines_set:
            return True

        # Next check it either has a substring that matches with a name in
        # either set.
        for inmach in inmachines:
            for mymach in self._tx_machines_set:
                if inmach in mymach or mymach in inmach:
                    return True

        # Must not match
        return False

    def __getitem__(self, item):
        return getattr(self, item)

    def __setitem__(self, item, value):
        return setattr(self, item, value)


class CouchTopCollection(object):
    Tops = None
    HN_Tops = None
    Normal_Tops = None
    _DB_Tops = None
    _keys = None

    def __init__(self, tops=None, use_known=True,
                 patient_db=get_current("PatientDB")):
        self._DB_Tops = {tmpl['Name']: tmpl for tmpl
                         in patient_db.GetPatientModelTemplateInfo()}

        if tops:
            _logger.debug(f"Building from incoming tops: {tops}")
            self.Tops = {k: CouchTop(k, **v) for k, v in tops.items()}
        elif use_known:
            _logger.debug(f"Building from known tops: {KNOWN_TOPS}")
            self.Tops = {k: CouchTop(k, **v) for k, v in KNOWN_TOPS.items()}
        else:
            _logger.debug(f"Building from DB Tops: {self._DB_Tops}")
            self.Tops = {k: CouchTop(k) for k in self._DB_Tops}

        self.update()

    @property
    def keys(self):
        return self._keys

    def __getitem__(self, item):
        if isinstance(item, int):
            return self.Tops[self.keys[item]]
        return self.Tops[item]

    def __iadd__(self, newitem):
        self.Add(newitem)
        return self

    def __iter__(self):
        return iter(self.Tops)

    def __next__(self):
        return self.Tops.__next__()

    # TODO: Implement later
    def Add(self, newitem):
        raise NotImplementedError("Adding top to collection not built.")

    def update(self, patient_db=get_current("PatientDB"), structure_set=None):
        self.HN_Tops = {}
        self.Normal_Tops = {}
        self._keys = sorted([top for top in self.Tops
                             if self.Tops[top].isValid])
        for topname, top in self.Tops.items():
            if top.isValid:
                if structure_set:
                    self[topname].update(structure_set)
                if top.isHN:
                    self.HN_Tops[topname] = top
                else:
                    self.Normal_Tops[topname] = top

    def get_other_machines_tops(self, inTop):
        if isinstance(inTop, str) and inTop in self.Tops:
            inTop = self.Tops[inTop]

        return {name: top for name, top in self.Tops.items() if
                top.isHN == inTop.isHN and
                not inTop.machine_matches(top)}

    def get_tops_in_structure_set(self, structure_set):
        plan_roi_names = set(structure_set.RoiGeometries.Keys)
        models_present = []
        for top_name in self:
            self[top_name].update(structure_set)
            if set(self[top_name]['ROI_Names']) <= plan_roi_names:
                models_present.append(self[top_name])

        # If we have any H&N tops in the model, we should only return the
        # subset that are H&N tops. (elminates name collisions for non H&N
        # tops)
        HN_tops = [m for m in models_present if m.isHN]
        if HN_tops:
            return HN_tops

        return models_present

    def get_first_top(self, machine, isHN=False):
        topset = self.HN_Tops if isHN else self.Normal_Tops
        if not machine:
            # Don't have a machine name, just return the first top. (Maybe a
            # bad guess?)
            return self.Tops[sorted(topset)[0]]
        for top in sorted(topset):
            if self.Tops[top].machine_matches(machine):
                return self.Tops[top]

    def __str__(self):
        return '{}: [{}]'.format(self.__class__.__name__,
                                 ', '.join(map(str, self.Tops)))

    def __repr__(self):
        return str(self)


def addcouchtoexam(icase, examination=None, plan=None,
                   patient_db=get_current("PatientDB"), remove_existing=False,
                   **kwargs):

    if plan:
        examination = plan.GetTotalDoseStructureSet().OnExamination
    elif not examination:
        examination = pick_exam()

    structure_set = icase.PatientModel.StructureSets[examination.Name]
    series = Image_Series(examination.Series[0])

    tops = CouchTopCollection(use_known=True)

    existing_tops = tops.get_tops_in_structure_set(structure_set)

    # Remove all existing tops.
    if existing_tops and remove_existing:
        with CompositeAction("Remove Existing Tops"):
            invalidate_structureset_doses(icase=icase,
                                          structure_set=structure_set)
            while existing_tops:
                existing_tops.pop().remove_from_case(remove_existing)

    if 'couch_y' in kwargs:
        top_height = kwargs['couch_y']
        del kwargs['couch_y']
    else:
        top_height = get_or_find_table_height(series, icase=icase)

    isHN = test_for_hn(icase, series)

    machine = ''
    try:
        if plan is None:
            _logger.warning("No plan selected, trying first plan.")
            plan = pick_plan()
        machine = plan.BeamSets[0].MachineReference.MachineName
        _logger.debug(f"Found machine {machine = }")
    except (ArgumentOutOfRangeException, IndexError):
        _logger.info("Couldn't determine machine. "
                     "Guessing based on the current case.")
        machine = guess_machine(icase)

    top = tops.get_first_top(machine=machine, isHN=isHN)

    with CompositeAction(f"Add {top.Name} to case"):
        top.add_to_case(icase, examination, top_height, **kwargs)

        try:
            for beamset in plan.BeamSets:
                beamset.SetDefaultDoseGrid(VoxelSize=point(0.2))
        except (AttributeError, TypeError):
            _logger.warning("Unable to reset default dose grid size for plan.",
                            exc_info=True)

    return top
