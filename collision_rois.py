# Interpreter: CPython 3.8 (64-bit)
# Name: Collision Detection
# Comment: Create Gantry colliders for collision detection and evaluation.
# Module: Structure definition, Plan setup


from .points import AffineMatrix
from .external import (CompositeAction, get_current, get_module_opt,
                       Show_OK, Show_OKCancel, Show_YesNo, MB_Icon, MB_Result)
from .case_comment_data import set_validation_comment
from .roi import ROI_Builder
from .mock_objects import MockBeam

import logging

# Unit for the STL files
_STL_OPTS = {'UnitInFile': 'Centimeter'}
# Default options for the ROIs to be created
_CREATE_OPTS = {'Color': 'White',
                # Bolus type prevents OOM issues for large ROIs.
                'Type':  'Bolus'}

_FN_BASE = '.\\CD\\{:0d}.stl'

_logger = logging.getLogger(__name__)

__FAB__ = 'FULL ARC BEAM'


def nominal_iso_name(isocenter, use_annotation=True):
    try:
        if use_annotation:
            return isocenter.Annotation.Name
    except (AttributeError, ValueError):
        pass

    return '{:.2f}, {:.2f}, {:.2f}'.format(*isocenter.Position.values())


def nominal_beam_name(beam):
    if beam.ArcStopGantryAngle is None:
        arc = 0
        gstart = beam.GantryAngle
        gtext = 'G{:.0f}'.format(gstart)
    else:
        a_start = beam.GantryAngle
        a_stop = beam.ArcStopGantryAngle

        arc = ((a_start + 180) % 360) - ((a_stop + 180) % 360)

        gstart, gstop = (a_start, a_stop) if arc < 0 else (a_stop, a_start)
        _logger.debug(f"Arc: {arc =} {gstart =} {gstop =}")
        gtext = 'G{:.0f}-{:.0f}'.format(a_start, a_stop)

    couch = 0
    for a in ['CouchRotationAngle', 'CouchAngle']:
        if hasattr(beam, a):
            couch = getattr(beam, a)
            break

    if couch != 0:
        gtext += ' T{:.0f}'.format(couch)

    return gtext


def beamset_rois(beam_set):
    cp = beam_set.PatientSetup.CollisionProperties
    patient_model = cp.ForPatientModel
    rois_by_type = {}
    for roi in patient_model.RegionsOfInterest:
        if roi.Type not in rois_by_type:
            rois_by_type[roi.Type] = set()
        rois_by_type[roi.Type].add(roi.Name)

    return rois_by_type


def margin_settings(margin):
    return {'Type': 'Expand',
            'Superior': margin, 'Inferior': margin,
            'Anterior': margin, 'Posterior': margin,
            'Right': margin, 'Left': margin}


def has_overlap(beam_set, rois_set, margin=0):
    overlaps = Overlaps(beam_set=beam_set)
    overlaps.check_rois(rois_set)
    overlaps.CleanUp()
    return overlaps


class Overlaps(dict):
    _isValid = False
    _invalidation_cb_fn = None
    _iter_cb_fn = None
    beam_set = None
    test_roi_g = None
    margin_roi = None
    coll_create_opts = {'Color': 'Red',
                        'Type': 'Bolus'}

    _gantries = None
    _builder = None
    beams = None  # Beams to check against (set if passed beamset)
    beam_map = None  # Dict mapping beams to the rois used for collision

    # Dict of dicts of bools.
    #  i.e. Overlaps[Collider][Gantry] = bool(Collided)
    # e.g. Overlaps['External']['T10 G181-179'] = True
    # Adds a helper function to check any and all for all of them
    # also function to return those that fail as a tuple
    # Could be done with numpy or pandas much more simply, but that would
    # require an extra import/venv.
    def __init__(self, *args,
                 invalidation_cb_fn=None, iter_cb_fn=None, gantry_cb_fn=None,
                 beam_set=None, full_arc_check=False,
                 **kwargs):

        self._invalidation_cb_fn = invalidation_cb_fn
        self._iter_cb_fn = iter_cb_fn
        self._gantry_cb_fn = gantry_cb_fn
        self._gantries = {}
        self.beam_map = {}

        super().__init__(*args, **kwargs)

        if beam_set:
            self.beam_set = beam_set
            self.beams = [b for b in beam_set.Beams]
            if full_arc_check:
                # Add a beam for a full arc check at 0 couch as well.
                fab = MockBeam(ArcRotationDirection='Clockwise',
                               GantryAngle=181,
                               ArcStopGantryAngle=179,
                               Name=__FAB__,
                               # Use the first beams' isocenter... #TODO don't.
                               Isocenter=self.beams[0].Isocenter,
                               CouchRotationAngle=0.0)
                self.beams.append(fab)

            self._builder = ROI_Builder(beam_set=beam_set,
                                        default_opts=self.coll_create_opts)

            self.test_roi = self._builder.CreateROI('collision')
            self.margin_roi = self._builder.CreateROI('margin')

            self._add_gantries()

    def _log_callback_fn(self, *args):
        loc = locals()
        _logger.debug(f"Callback self, {loc=}")

    def gantry_cb(self, progress, message=''):
        if callable(self._gantry_cb_fn):
            return self._gantry_cb_fn(progress, message)
        else:
            return self._log_callback_fn(progress, message)

    def calc_iter_cb(self, progress, message=''):
        if callable(self._iter_cb_fn):
            return self._iter_cb_fn(progress, message)
        else:
            return self._log_callback_fn(progress, message)

    def invalidation_cb(self, isvalid):
        if callable(self._invalidation_cb_fn):
            return self._invalidation_cb_fn(isvalid)

    @property
    def isValid(self):
        return self._isValid

    @isValid.setter
    def isValid(self, value):
        if self._isValid != bool(value):
            self._isValid = bool(value)

            if not self._isValid:
                logging.debug("Calling invalidation callback function")
                self.invalidation_cb(value)
                self.clear()

    @property
    def isFalse(self):
        # Right now this will try to exclude the beam used for full arc
        # evaluation if it was added.
        gantry_colliders = {gantry for beamname, gantry
                            in self.beam_map.items() if beamname != __FAB__}
        return not any([any([collides for gantry_roi, collides
                             in collider.items()
                             if gantry_roi in gantry_colliders])
                        for collider in self.values()])

    @property
    def hasCollision(self):
        return not self.isFalse

    @property
    def beamrois_set(self):
        return set(self._gantries.keys())

    @property
    def failing_pairs(self):
        return [(collider_roi, beam_roi) for collider_roi in self
                for beam_roi in self[collider_roi]
                if self[collider_roi][beam_roi]]

    @property
    def by_beams(self):
        out = {}
        for collider_roi in self:
            for beam_roi in self[collider_roi]:
                if beam_roi not in out:
                    out[beam_roi] = {}
                out[beam_roi][collider_roi] = self[collider_roi][beam_roi]
        return out

    @property
    def colliders_by_gantry(self):
        by_beams = self.by_beams
        return {beam_roi: [collider_roi for collider_roi in by_beams[beam_roi]
                           if by_beams[beam_roi][collider_roi]]
                for beam_roi in by_beams}

    @property
    def failing_by_beam(self):
        beamsdict = {}
        for collider_roi, beam_roi in self.failing_pairs:
            if beam_roi in beamsdict:
                beamsdict[beam_roi] += [collider_roi]
            else:
                beamsdict[beam_roi] = [collider_roi]
        logging.debug(f"{beamsdict=}")
        return beamsdict

    @property
    def failing_by_collider(self):
        colliderdict = {}
        for collider_roi, beam_roi in self.failing_pairs:
            if collider_roi in colliderdict:
                colliderdict[collider_roi] += [beam_roi]
            else:
                colliderdict[collider_roi] = [beam_roi]
        return colliderdict

    def _add_gantries(self):
        for i, beam in enumerate(self.beams):
            a_start = beam.GantryAngle
            if beam.ArcStopGantryAngle is None:
                arc = 0
                _logger.debug(f"Static: {a_start =}")
            else:
                a_stop = beam.ArcStopGantryAngle
                arc = ((a_start + 180) % 360) - ((a_stop + 180) % 360)

            gstart = a_start if arc <= 0 else a_stop
            _logger.debug(f"Arc: {arc =} {gstart =}")

            couch = 0
            for a in ['CouchRotationAngle', 'CouchAngle']:
                if hasattr(beam, a):
                    couch = getattr(beam, a)
                    break

            # Correct for rotation angles when not in HFS
            cp = self.beam_set.PatientSetup.CollisionProperties
            exam = cp.ForExaminationStructureSet.OnExamination
            exam_pp = exam.PatientPosition
            bs_pp = ''.join(filter(str.isupper, self.beam_set.PatientPosition))

            if exam_pp[0] == "F":
                couch += 180
            if exam_pp[2] == "P":
                gstart += 180

            if exam_pp[0] != bs_pp[0]:
                couch += 180
            if exam_pp[2] != bs_pp[2]:
                gstart += 180

            _logger.debug(f"{exam_pp=} {bs_pp=} {couch=} {gstart=}")

            gtext = nominal_beam_name(beam)
            fn_base = get_module_opt('fn_base', _FN_BASE)
            fn = fn_base.format(int(round(abs(arc), 0)))

            iso = beam.Isocenter.Position
            isoname = nominal_iso_name(beam.Isocenter)
            gantry_name = f'{isoname}: {gtext}'

            mat = AffineMatrix(**iso, roll=gstart, yaw=couch, order='gantry')

            tm = mat.rs_matrix

            if gantry_name in self._gantries:
                roi = self._gantries[gantry_name]
            else:
                roi = self._builder.GetOrCreateROI(gantry_name, _CREATE_OPTS)
                self._gantries[gantry_name] = roi

                roi.DeleteGeometry()

                try:
                    roi.importSTL(fn, tm, **_STL_OPTS)
                except SystemError:
                    _logger.exception(f"Failed to add gantry {gantry_name}")

            self.gantry_cb(i/len(self.beams), beam.Name)

            self.beam_map[beam.Name] = gantry_name

    def check_rois(self, rois_set, margin=0):
        # Build structure of all patient geometries to check against
        #   TODO: Maybe this should iterate instead and report back what
        #   beam/contout pairs overlap?

        roi = self.test_roi

        if not rois_set:
            raise ValueError("No valid structures found for comparison.")

        total = len(rois_set) * len(self.beamrois_set)
        i = 1
        # Turns out overlap calculation for single roi to single roi is fast...
        for collider_roi in rois_set:
            # Because we have a margin, and it is much faster to expand each
            # structure once and then compare the expansion, we will do that.
            if margin > 0:
                self.margin_roi.marginate(collider_roi, margin)
                loop_roi = self.margin_roi.Name
            else:
                loop_roi = collider_roi

            overa = self[collider_roi] if collider_roi in self else {}

            for beam_roi in self.beamrois_set:
                if beam_roi in overa:
                    continue
                overa[beam_roi] = roi.check_overlap(loop_roi, beam_roi)
                self.calc_iter_cb(i/total, f'{collider_roi}: {beam_roi}')
                i += 1

            self[collider_roi] = overa

        self.isValid = True

        return self

    def __str__(self):
        return '\n'.join(f'{beamname}: '+', '.join(roi)
                         for beamname, roi in self.failing_by_beam.items())

    def CleanUp(self, keepbeams=False):
        if not keepbeams:
            for roi in self._gantries.values():
                roi.DeleteRoi()

        if self.margin_roi:
            self.margin_roi.DeleteRoi()
            self.margin_roi = None

        if self.test_roi:
            self.test_roi.DeleteRoi()
            self.test_roi = None


def check_collision(plan, beam_set, silent=False, retain=False,
                    retain_on_fail=True, full_arc_check=False):
    # TODO: Add full arc check logic
    try:
        with CompositeAction("Add Collision ROIs"):

            overlaps = Overlaps(beam_set=beam_set,
                                full_arc_check=full_arc_check)

            if not silent:
                check = Show_YesNo("Perform automatic collision check?",
                                   "Automatic Yes or No",
                                   defaultResult=MB_Result.Yes,
                                   icon=MB_Icon.Question)
            else:
                check = MB_Result.Yes

            if check == MB_Result.Yes:
                all_rois = beamset_rois(beam_set)
                rois_set = all_rois['External']
                if 'Support' in all_rois:
                    rois_set |= all_rois['Support']
                overlaps.check_rois(rois_set)
                _logger.debug(f"{overlaps = }")
                if overlaps.hasCollision and not silent:
                    retain = retain_on_fail
                    Show_OK("Found potential collision.\n"
                            f"Overlaps identified:\n{overlaps!s}",
                            "Overlap found.",
                            icon=MB_Icon.Exclamation)

            if not silent:
                msg = ("Review for potential collision.\n"
                       "Press OK to keep structures, Cancel to remove.\n"
                       "\n"
                       "CAUTION: To avoid memory issues, do NOT open\n"
                       "         the ROI details on Gantry ROIs.")

                res = Show_OKCancel(msg, 'Review for collisions')
                if res == 1:
                    _logger.info("Retaining ROIs.")
                else:
                    raise Warning("Removing ROIs")
            elif not retain:
                raise Warning("Removing ROIs")

    except Warning as e:
        _logger.info(f"Stopped with warning. {e!s}", exc_info=True)

    status = {'status': overlaps.hasCollision,
              'UpdateComment': True,
              'overlaps': overlaps}

    return status


if __name__ == '__main__':
    log_fmt = ('%(asctime)s: %(name)s.%(funcName)s:%(lineno)d'
               ' - %(levelname)s: %(message)s')

    logging.basicConfig(format=log_fmt, level=logging.INFO, force=True)

    try:
        beam_set = get_current('BeamSet')
        plan = get_current('Plan')
    except SystemError:
        _logger.exception("Couldn't load beamset. Trying first.")
        beam_set = get_current('Plan').BeamSets[0]

    status = check_collision(plan, beam_set)

    if status['UpdateComment']:
        status = status['status']
        _logger.info(f"Updating validation status for plan to {status}.")
        set_validation_comment(plan, beam_set, "Collision", not(status))
