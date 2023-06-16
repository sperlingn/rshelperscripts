import logging

from .external import CompositeAction as _CompositeAction

_logger = logging.getLogger(__name__)


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
                    bs.UpdateDoseGrid(Corner=grid.Corner,
                                      VoxelSize=grid.VoxelSize,
                                      NumberOfVoxels={'x': 1, 'y': 1, 'z': 1})
                    bs.UpdateDoseGrid(Corner=grid.Corner,
                                      VoxelSize=grid.VoxelSize,
                                      NumberOfVoxels=grid.NrVoxels)
