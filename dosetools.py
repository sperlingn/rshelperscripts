import logging

from .external import CompositeAction as _CompositeAction
from .points import point, BoundingBox

_logger = logging.getLogger(__name__)

_ALL_ROI_TYPES = {'External',
                  'Ptv',
                  'Ctv',
                  'Gtv',
                  'TreatedVolume',
                  'IrradiatedVolume',
                  'Bolus',
                  'Avoidance',
                  'Organ',
                  'Marker',
                  'Registration',
                  'Isocenter',
                  'ContrastAgent',
                  'Cavity',
                  'BrachyChannel',
                  'BrachyAccessory',
                  'BrachySourceApplicator',
                  'BrachyChannelShield',
                  'Support',
                  'Fixation',
                  'DoseRegion',
                  'Control',
                  'FieldOfView',
                  'AcquisitionIsocenter',
                  'InitialLaserIsocenter',
                  'InitialMatchIsocenter'}

_DOSE_CALC_ROI_TYPES = {'External',
                        'Bolus',
                        'Support',
                        'Fixation'}


def invalidate_structureset_doses(icase, structure_set):
    """
    Hacky method to invalidate all dose grids computed against the listed
    structure set.  Sets each dose grid to be X*Y*1 voxels, then back to X*Y*Z.
    """
    exam_name = structure_set.OnExamination.Name

    with _CompositeAction(f'Invalidate all doses on "{exam_name}"'):

        for txplan in icase.TreatmentPlans:
            for bs in txplan.BeamSets:
                fd = bs.FractionDose
                if (fd.OnDensity
                        and fd.OnDensity.FromExamination.Name == exam_name):
                    grid = bs.GetDoseGrid()
                    corner = dict(**grid.Corner)
                    vs = dict(**grid.VoxelSize)
                    nrvox = dict(**grid.NrVoxels)
                    bs.UpdateDoseGrid(Corner=corner,
                                      VoxelSize=vs,
                                      NumberOfVoxels={'x': 1, 'y': 1, 'z': 1})
                    bs.UpdateDoseGrid(Corner=corner,
                                      VoxelSize=vs,
                                      NumberOfVoxels=nrvox)


def expand_dosegrids(icase, structure_set, expand_superior=False):
    """
    Expand dosegrids to include the full extent of any support structures in
    the L/R and A/P directions.  If expand_superior is set, also expand
    superiorly (for e.g. Brain Tx through the top of a H&N board)
    Default is false.
    """
    exam_name = structure_set.OnExamination.Name

    roi_bb = BoundingBox()

    # Define new bounds of the dose grid for this structure set based on any
    # ROIs with types defined by dose_types (e.g. bolus, support, external).
    for roi_g in structure_set.RoiGeometries:
        if roi_g.OfRoi.Type in _DOSE_CALC_ROI_TYPES:
            roi_bb += roi_g.GetBoundingBox()

    with _CompositeAction(f'Reshape all dose grids on "{exam_name}"'):
        for txplan in icase.TreatmentPlans:
            for bs in txplan.BeamSets:
                bs_exam_name = bs.GetStructureSet().OnExamination.Name
                if bs_exam_name != exam_name:
                    continue

                grid = bs.GetDoseGrid()

                corner = point(grid.Corner)
                vs = point(grid.VoxelSize)
                nrvox = point(grid.NrVoxels)

                grid_bb = BoundingBox([corner, corner+(vs*nrvox)])

                full_bb = grid_bb + roi_bb

                # Don't expand the dose grid in the Z inferiorly, any only
                # superiorly if asked.
                full_bb[0].z = grid_bb[0].z
                if not expand_superior:
                    full_bb[1].z = grid_bb[1].z

                new_corner = full_bb.lower
                new_nrvox = full_bb.size / vs

                bs.UpdateDoseGrid(Corner=new_corner,
                                  VoxelSize=vs,
                                  NumberOfVoxels=new_nrvox)
