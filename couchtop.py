import re
from connect import get_current, CompositeAction  # , set_progress
# import pickle
from points import holes_by_width, point, find_first_edge, find_edges
from operator import attrgetter
from case_comment_data import get_case_comment_data, set_case_comment_data
from ast import literal_eval
from rsdicomread import read_dataset
from struct import unpack_from

import logging

logger = logging.getLogger()


CT_Couch_TopY = 20.8
CT_Top_NegativeX = -24.5
HN_SEARCH_DELTA = -1.

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

SITE_SHIFT = {"Left Breast": 15.,
              "Right Breast": 15.,
              "Thorax": 20.,
              "Abdomen": 35.,
              "Pelvis": 55.,
              "Left Upper Extremity": 0.,
              "Right Upper Extremity": 0.,
              "Left Lower Extremity": 0.,
              "Right Lower Extremity": 0.}

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
        {'Surface_ROI': 'Surface Shell - TrueBeam',
         'Top_offset': {'x': 0., 'y': 0., 'z': 0.},
         'Tx_Machines': 'TrueBeam'},
    'Edge Couch Model':
        {'Surface_ROI': 'Outer Shell - Edge',
         'Top_offset': {'x': 0., 'y': 0., 'z': 0.},
         'Tx_Machines': 'Edge'},
    'Edge Head & Neck Model':
        {'Surface_ROI': 'Outer Shell - Edge H&N',
         'Top_offset': {'x': -.1, 'y': -2.33, 'z': 0.4},
         'Tx_Machines': 'Edge'},
    'TrueBeam Head & Neck Model':
        {'Surface_ROI': 'Surface Shell - TrueBeam',
         'Top_offset': {'x': 0.15, 'y': 0., 'z': 0.4},
         'Tx_Machines': 'TrueBeam'}
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
HEURISTIC_OFFSET = 1500


def guess_couchtop_z(img_stack):
    """
    Guesses the z coordinate of the couch top based on specific dicom tags.
    Tags don't currently populate correctly, so work on reading them by hand.
    """
    try:

        img, = read_dataset(img_stack)

        CZ_raw = img[PRIV_01F7_1027].value

        couchZabs = unpack_from("f", CZ_raw)[0]
        sliceloc = img.SliceLocation.real
        ipp = img.ImagePositionPatient[2].real

        cdist = sliceloc - couchZabs
        abs_couch_pos = cdist + HEURISTIC_OFFSET
        ippscale = ipp / sliceloc

        couch_z = abs_couch_pos * ippscale

        return couch_z
    except Exception as e:
        logger.exception(e)
        return None


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
    # TODO: Prompt for machine if we can't figure it out
    return machine


def test_for_hn(icase, img_stack):
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
        logger.warning("Testing for H&N board by searching image is not "
                       f"implemented yet.  Treatment Site {icase.BodySite} "
                       "is insufficient for use in determination.")
    return False


def find_table_height(img_stack, resolution=None, search_start=None,
                      x_avg=None, z_avg=1., default=CT_Couch_TopY):
    """
    Find the table surface from image.
    """
    # Search start from CT_Top_NegativeX, let it find the middle for z, and
    # we are searching in y.
    search_start = search_start if search_start else {'x': CT_Top_NegativeX,
                                                      'y': None,
                                                      'z': None}
    x_avg = x_avg if x_avg else img_stack.PixelSize.x
    y_avg = resolution if resolution else None

    # Minimum value for a peak to be considered real
    threshold = -200

    try:
        edge = find_first_edge(img_stack,
                               search_start=search_start,
                               x_avg=x_avg,
                               y_avg=y_avg,
                               z_avg=z_avg,
                               line_direction='-y',
                               threshold=threshold,
                               rising_edge=False)

        return edge

    except TypeError:
        return default
    except (ValueError, IndexError, SystemError) as e:
        logger.exception(e)
        return default


class CouchTop(object):
    Name = ""

    ROI_Names = None
    Top_offset = None  # {'x': 0., 'y': 0., 'z': '0.'},
    Tx_Machines = None
    _tx_machines_set = None
    _board_z = None

    roi_geometries = None
    isHN = False
    template = None
    isValid = False
    _desc_re = re.compile(r'(?:Offset:\s(?P<Offset>\d+)'
                          r'|Tx Machines:\s(?P<TxMachines>.*)$'
                          r'|Surface:\s"(?P<Surface>[^"]+)")')

    _surfaceboundingbox = None

    inActiveSet = False

    def __init__(self, Name, Top_offset=None, Surface_ROI="", Tx_Machines="",
                 patient_db=get_current("PatientDB"), structure_set=None):
        self.Name = Name
        logger.debug(f"Building CouchTop with: {Name}, {Top_offset}, "
                     f"{Surface_ROI}, {Tx_Machines}")

        try:
            self.template = patient_db.LoadTemplatePatientModel(
                templateName=Name, lockMode='Read')

            rois = self.template.PatientModel.RegionsOfInterest
            self.ROI_Names = {roi.Name for roi in rois}

            self._build_from_description()

            self._Top_offset = Top_offset if Top_offset else self._Top_offset
            self.Surface_ROI = Surface_ROI if Surface_ROI else self.Surface_ROI
            self.isHN = True if "H&N" in "".join(self.ROI_Names) else False
            self.Tx_Machines = Tx_Machines if Tx_Machines else self.Tx_Machines

            self._tx_machines_set = self.machine_set(self.Tx_Machines)

            self.isValid = self.Surface_ROI in self.ROI_Names

            if structure_set:
                self.update()

        except SystemError:
            # No template in patient_db by this name.
            pass

    def _build_from_description(self):
        if self.template.Description:
            for m in self._desc_re.finditer(self.template.Description):
                if m.group('Surface'):
                    self.Surface_ROI = m.group('Surface')
                if m.group('Offset'):
                    try:
                        offset = literal_eval(m.group('Offset'))
                        if isinstance(offset, float):
                            self._Top_offset = point(y=offset)
                        elif isinstance(offset, tuple):
                            self._Top_offset = point(*offset)
                    except (ValueError, TypeError, SyntaxError,
                            MemoryError, RecursionError):
                        self._Top_offset = None
                    except Exception as e:
                        logger.exception(e)
                if m.group('TxMachines'):
                    self.Tx_Machines = m.group('TxMachines')

    @staticmethod
    def machine_set(inmachinename):
        namelow = inmachinename.lower()
        return set(namelow.replace('\n', ',').replace(' ', '').split(','))

    @property
    def Top_offset(self):
        try:
            surf_bb = self._surfaceboundingbox
            x_offset = (surf_bb[0].x + surf_bb[1].x) / 2.
            return point(x=-x_offset+self._Top_offset['x'],
                         y=self._Top_offset['y'],
                         z=self._Top_offset['z'])
        except Exception as e:
            logger.info(str(e), exc_info=True)
            return self._Top_offset

    def get_transform(self, structure_set, couch_y=CT_Couch_TopY, z=0.):

        # get from position of top, need ROIs to be present.
        surface_roi = structure_set.RoiGeometries[self.Surface_ROI]

        self._surfaceboundingbox = surface_roi.GetBoundingBox()
        current_y = self._surfaceboundingbox[0].y

        y = couch_y - current_y
        pt = point(x=0, y=y, z=z) + self.Top_offset
        transform = {'M11': 1, 'M12': 0, 'M13': 0, 'M14': pt.x,
                     'M21': 0, 'M22': 1, 'M23': 0, 'M24': pt.y,
                     'M31': 0, 'M32': 0, 'M33': 1, 'M34': pt.z,
                     'M41': 0, 'M42': 0, 'M43': 0, 'M44': 1}

        # Ensure that transform is a valid matrix of floats as RS will crash if
        # there are nonetypes or anything else in here.
        transform = {k: float(v) for k, v in transform.items()}
        logger.debug(f'{transform}')
        return transform

    def add_to_case(self, icase=None, structure_set=None,
                    couch_y=CT_Couch_TopY, match_z=True, forced_z=None,
                    simple_search=True):
        if icase is None:
            icase = get_current("Case")
        if structure_set is None:
            structure_set = icase.PatientModel.StructureSets[0]

        examination = structure_set.OnExamination
        source_exam_name = self.template.StructureSetExaminations[0].Name

        case_data = get_case_comment_data(icase)

        if 'board_z' in case_data:
            CouchTop._board_z = case_data['board_z']

        with CompositeAction("Add couch '{}' to plan.".format(self.Name)):
            csft = icase.PatientModel.CreateStructuresFromTemplate
            csft(SourceTemplate=self.template,
                 SourceExaminationName=source_exam_name,
                 SourceRoiNames=list(self.ROI_Names),
                 #  Rest are default options
                 SourcePoiNames=[],
                 AssociateStructuresByName=True,
                 TargetExamination=examination,
                 InitializationOption="AlignImageCenters")

            self.update(structure_set)

            self.move_rois(structure_set=structure_set,
                           couch_y=couch_y,
                           match_z=match_z,
                           forced_z=forced_z,
                           icase=icase,
                           simple_search=simple_search)

        if 'board_z' not in case_data and CouchTop._board_z:
            case_data['board_z'] = CouchTop._board_z
            set_case_comment_data(data=case_data,
                                    icase=icase,
                                    replace=True)

    def update(self, structure_set):
        rois = {roi.OfRoi.Name for roi in structure_set.RoiGeometries}
        self.roi_geometries = {roi_name: structure_set.RoiGeometries[roi_name]
                               for roi_name in self.ROI_Names
                               if roi_name in rois}

    @classmethod
    def get_board_z_from_image(cls, img_stack, couch_y, simple_search=True):
        """
        Searches for coordinate of top of board.
        Simple search looks only for the central hole.
        Complex search tries to identify the side holes as well and estimate
          based on the positions of the 4 side holes.  This method is preferred
          as CT scans often cut off the top of the board.
        """
        if cls._board_z and str(img_stack) in cls._board_z:
            return cls._board_z[str(img_stack)]

        z = img_stack.Corner.z + max(img_stack.SlicePositions)

        search_y = couch_y + HN_SEARCH_DELTA
        if simple_search:
            try:
                search_point = point(y=search_y)
                found_point = find_first_edge(img_stack,
                                            search_start=search_point,
                                            line_direction='-z',
                                            rising_edge=True)
                logger.debug(f"Found start of board at {found_point}.")
                if found_point:
                    # Naively assume that the first point is the start of the board
                    z = found_point.z
            except Exception as e:
                logger.warning(str(e), exc_info=True)
                return None
        else:
            try:
                # Ignore the central hole and look instead for the side holes.

                # To start, get a guess at the first hole, then find the center
                # of the H&N Board in the X direction.  We will then move the
                # search points based on any shift in this image.

                init_guess = point(x=HN_H2_X, y=search_y)
                guess_edges = find_edges(img_stack, search_start=init_guess,
                                         line_direction='-z', z_avg=0.05)
                guess_hole = holes_by_width(edges=guess_edges,
                                            width=HN_H_DIAM,
                                            tolerance=1.)[-1]

                width_search = point(y=search_y, z=guess_hole.center.z)
                width_edges = find_edges(img_stack, search_start=width_search,
                                         line_direction='x')
                x_offset = (width_edges[-1][1].x + width_edges[0][0].x)/2

                tp_search_start = point(x=HN_H2_X + x_offset, y=search_y)
                tn_search_start = point(x=-HN_H2_X + x_offset, y=search_y)

                bp_search_start = point(x=HN_H3_X + x_offset, y=search_y)
                bn_search_start = point(x=-HN_H3_X + x_offset, y=search_y)

                # Logic will now start with each rising edge in tp_search and
                # look for a falling edge that is the right distance away
                # (HN_H_DIAM +- some margin)  If that works, it will try to
                # find corresponding points that are within the sensible
                # distances for each other hole.
                tp_edges = find_edges(img_stack, search_start=tp_search_start,
                                      line_direction='-z', z_avg=0.05)
                tn_edges = find_edges(img_stack, search_start=tn_search_start,
                                      line_direction='-z', z_avg=0.05)
                bp_edges = find_edges(img_stack, search_start=bp_search_start,
                                      line_direction='-z', z_avg=0.05)
                bn_edges = find_edges(img_stack, search_start=bn_search_start,
                                      line_direction='-z', z_avg=0.05)

                tp_holes = holes_by_width(edges=tp_edges,
                                          width=HN_H_DIAM,
                                          tolerance=1.)
                tn_holes = holes_by_width(edges=tn_edges,
                                          width=HN_H_DIAM,
                                          tolerance=1.)
                bp_holes = holes_by_width(edges=bp_edges,
                                          width=HN_H_DIAM,
                                          tolerance=1.)
                bn_holes = holes_by_width(edges=bn_edges,
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

                if logger.level <= logging.DEBUG:
                    global __DEBUG__TB__
                    __DEBUG__TB__ = locals()

                # Check a few features to make sure that the holes are sensible
                if ((abs(bn_hole_z - bp_hole_z) > HN_H_DIAM / 2
                     or abs(tn_hole_z - tp_hole_z) > HN_H_DIAM / 2)):
                    # Holes aren't aligned with eachother, not the same holes
                    # or the board is way to rotated, fail out.
                    logger.warning(f"Holes not aligned: "
                                   f"{tn_hole_z}, {tp_hole_z}, "
                                   f"{bn_hole_z}, {bp_hole_z}")
                    return None

                if abs(abs(top_hole_z - bot_hole_z) - HN_H_SEP) > HN_H_DIAM:
                    # Holes aren't spaced right, no further checking yet
                    # TODO: Possibly look for additional hole pairs that do
                    # match.
                    logger.warning(f"Holes not spaced correctly:"
                                   f" {top_hole_z}, {bot_hole_z}")
                    return None

                # Finally, these look right so return the location of the top
                # of the board from these holes.  Include the distance from
                # hole center of the top hole to the edge of the board.
                logger.debug("Holes for distance: "
                             f"{tn_hole_z}, {tp_hole_z}, "
                             f"{bn_hole_z}, {bp_hole_z}")

                z = (((top_hole_z + bot_hole_z + HN_H_SEP) / 2)
                     + HN_H1_TO_H2_Z + HN_H1_TO_BOARD_Z)
            except IndexError:
                pass

        # MAGIC: Store the search result in the class so we don't have to do it
        # again.
        if not cls._board_z:
            cls._board_z = {str(img_stack): z}
        else:
            cls._board_z[str(img_stack)] = z

        return z

    def move_rois(self, structure_set, couch_y=CT_Couch_TopY,
                  match_z=True, forced_z=None, icase=None, simple_search=True):
        examination = structure_set.OnExamination
        img_stack = examination.Series[0].ImageStack

        roi_max_z = max([pt.z for roi in self.ROI_Names
                         for pt in self.roi_geometries[roi].GetBoundingBox()])

        z_top_corner = (img_stack.Corner.z + max(img_stack.SlicePositions))
        if match_z and not forced_z:
            if self.isHN:
                board_z = self.get_board_z_from_image(img_stack, couch_y,
                                                      simple_search)
                if board_z:
                    z_top_corner = board_z
            else:
                ct_z = guess_couchtop_z(img_stack)
                if ct_z is not None:
                    z_top_corner = ct_z
                else:
                    if icase is None:
                        icase = get_current("Case")

                    if icase.BodySite in SITE_SHIFT:
                        z_top_corner += SITE_SHIFT[icase.BodySite]

        z = forced_z if forced_z else z_top_corner - roi_max_z

        transform = self.get_transform(structure_set, couch_y, z)

        for roi in self.ROI_Names:
            structure_set.RoiGeometries[roi].OfRoi.TransformROI3D(
                Examination=examination,
                TransformationMatrix=transform)

    def remove_from_case(self):
        with CompositeAction("Remove {} couch from case.".format(self.Name)):
            if self.roi_geometries:
                for geom in self.roi_geometries.values():
                    geom.OfRoi.DeleteRoi()

    def machine_matches(self, inmachinename):
        if isinstance(inmachinename, CouchTop):
            inmachines = inmachinename._tx_machines_set
        elif isinstance(inmachinename, str):
            inmachines = self.machine_set(inmachinename)
        else:
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
            self.Tops = {k: CouchTop(k, **v) for k, v in tops.items()}
        elif use_known:
            self.Tops = {k: CouchTop(k, **v) for k, v in KNOWN_TOPS.items()}
        else:
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
        plan_roi_names = {roi.OfRoi.Name for roi
                          in structure_set.RoiGeometries}
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
