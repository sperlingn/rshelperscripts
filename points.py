import logging
from math import sqrt, sin, cos, pi
from typing import Sequence, List, Tuple

_logger = logging.getLogger(__name__)


class point(dict):
    _COORDS = ['x', 'y', 'z']

    def __init__(self, x=None, y=None, z=None):
        super(point, self).__init__(self)

        for coord in self._COORDS:
            self[coord] = 0

        if isinstance(x, dict):
            self.update(x)
        elif isinstance(x, tuple) and len(x) == len(self._COORDS):
            for coord, val in zip(self._COORDS, x):
                self[coord] = val
        elif all(hasattr(x, c) for c in self._COORDS):
            # Assume this is a point like and build from this:
            for coord in self._COORDS:
                self[coord] = getattr(x, coord)
        else:
            self.update({'x': x if x else 0,
                         'y': y if y else 0,
                         'z': z if z else 0})

    @classmethod
    def __contains__(cls, key):
        return key in cls._COORDS

    @classmethod
    def __ispointlike__(cls, obj):
        try:
            if isinstance(obj, cls):
                return True
            if any((hasattr(obj, c) or (c in obj)) for c in cls._COORDS):
                return True
        except TypeError:
            pass
        return False

    @classmethod
    def X(cls):
        return cls(1., 0., 0.)

    @classmethod
    def Y(cls):
        return cls(0., 1., 0.)

    @classmethod
    def Z(cls):
        return cls(0., 0., 1.)

    @property
    def x(self):
        return self['x']

    @x.setter
    def x(self, value):
        self['x'] = value

    @property
    def y(self):
        return self['y']

    @y.setter
    def y(self, value):
        self['y'] = value

    @property
    def z(self):
        return self['z']

    @z.setter
    def z(self, value):
        self['z'] = value

    @property
    def magnitude(self):
        return sqrt(sum([v**2 for v in self.values()]))

    def normalize(self):
        return self.__idiv__(self.magnitude)

    @property
    def normalized(self):
        return self/self.magnitude

    def __add__(self, other):
        if self.__ispointlike__(other):
            return type(self)({key: self[key] + (other[key] if key in other
                                                 else 0)
                               for key in self})
        elif isinstance(other, tuple) and len(other) == len(self):
            return type(self)({key: self[key] + other[i]
                               for i, key in enumerate(self)})
        else:
            return type(self)({key: self[key] + other for key in self})

    def __sub__(self, other):
        return self+(-other)

    def __neg__(self):
        return type(self)({key: -self[key] for key in self})

    def __pos__(self):
        return self

    def __mul__(self, other):
        if self.__ispointlike__(other):
            return type(self)({key: self[key] * (other[key] if key in other
                                                 else 0)
                               for key in self})
        elif isinstance(other, tuple) and len(other) == len(self):
            return type(self)({key: self[key] * other[i]
                               for i, key in enumerate(self)})
        else:
            return type(self)({key: self[key] * other for key in self})

    def __div__(self, other):
        return self.__mul__(1./other)

    def __truediv__(self, other):
        return self.__div__(other)

    def __radd__(self, other):
        return self+other

    def __rsub__(self, other):
        return -(self - other)

    def __rmul__(self, other):
        return self*other

    def __rdiv__(self, other):
        return ~self*other

    def __rtruediv__(self, other):
        return ~self*other

    def __invert__(self):
        try:
            return type(self)({key: 1./self[key] for key in self})
        except ZeroDivisionError:
            return type(self)({key: int(not self[key]) for key in self})

    def __iadd__(self, other):
        new = self + other
        for key in new:
            self[key] = new[key]
        return self

    def __isub__(self, other):
        return self.__iadd__(-other)

    def __imul__(self, other):
        new = self * other
        for key in new:
            self[key] = new[key]
        return self

    def __idiv__(self, other):
        return self.__imul__(1./other)

    def __itruediv__(self, other):
        return self.__idiv__(other)

    def copy(self):
        return self+0.

    def __floordiv__(self, other):
        return (self/other).__floor__()

    def __floor__(self):
        return type(self)({key: int(self[key]//1) for key in self})

    def to_from_rs(self):
        # self *= type(self)({'x': 1, 'y': -1, 'z': 1})
        self.y *= -1
        return self

    def __str__(self):
        return f"({self.x:.2f}, {self.y:.2f}, {self.z:.2f})"

    def __repr__(self):
        return "point({})".format(super(point, self).__repr__())


class Hole(object):
    diameter = 0.0
    center = None

    def __init__(self, center, diameter):
        self.center = point(center)
        self.diameter = float(diameter)

    def __lt__(self, other):
        return self.diameter.__lt__(other.diameter)

    def __repr__(self):
        return f"Hole({self.center}, {self.diameter})"

    def __str__(self):
        return f"{self.diameter} hole at {self.center}"

    @property
    def x(self):
        return self.center.x

    @property
    def y(self):
        return self.center.y

    @property
    def z(self):
        return self.center.z


def find_fwhm_edges(inarray, threshold='global_half_max', min_value=None):
    min_value = min_value if min_value is not None else min(inarray)
    last_max = min_value
    last_i = 0
    try:
        threshold = float(threshold)
    except ValueError:
        # Not a number, for now assume it is global half max
        threshold = (max(inarray)+min(inarray))/2.

    edge_v = threshold

    indices = []
    try:
        # Iterate through and find the next start of a peak.
        for i, v in enumerate(inarray):
            if last_i:
                if v > last_max:
                    last_max = v
                    edge_v = (last_max + min_value)/2.

                if v <= edge_v:
                    indices.append((last_i, i))
                    _logger.debug(f"Adding ({last_i}, {i}) to list.")
                    last_i = 0
                    """
                    indices.append(i + (indices[-2] if len(indices) > 2
                else 0))
                return find_fwhm_edges(inarray[i+1:], threshold,
            indices, min_value)
            """
            elif v > edge_v:
                last_i = i
    except (IndexError, SystemError) as e:
        _logger.info(str(e), exc_info=True)
        pass

    # Fall to here when we have an IndexError, and when we run out of points
    #  in the array.
    if last_i:
        indices.append((last_i, -1))
    return indices


def find_edges(img_stack, search_start=None, x_avg=None, y_avg=None,
               z_avg=None, line_direction='-y', threshold=-600):
    line_invert = '-' in line_direction
    ldir = line_direction[-1] if line_direction[-1] in ('x', 'y', 'z') else 'y'
    lvec = point({ldir: 1})

    z_res = img_stack.SlicePositions[1] - img_stack.SlicePositions[0]

    x_avg = x_avg if x_avg else img_stack.PixelSize.x
    y_avg = y_avg if y_avg else img_stack.PixelSize.y
    z_avg = z_avg if z_avg else z_res

    resolution = point(x_avg, y_avg, z_avg)

    img_res = point({'x': img_stack.PixelSize.x,
                     'y': img_stack.PixelSize.y,
                     'z': z_res})

    n_pixels = point({'x': img_stack.NrPixels.x,
                      'y': img_stack.NrPixels.y,
                      'z': len(img_stack.SlicePositions)})

    resolution = img_res.copy()

    if x_avg:
        resolution.x = x_avg
        if y_avg:
            resolution.y = y_avg
            if z_avg:
                resolution.z = z_avg

    size = n_pixels*img_res
    image_center = point(img_stack.Corner) + (size/2)

    voxelcount = (((size//resolution) - 1) * lvec) + 1

    # Build a point out of the search start, and any coordinate which is None
    # should be set to the image_center for that coordinate.
    search_pt = point({idx: (v if v is not None
                             else image_center[idx])
                       for idx, v in point(search_start).items()})
    search_pt.to_from_rs()

    # If search_start was not set, this will start the search from the image
    # center in all directions except the search direction where it will start
    # at the corner.  Otherwise, if search_start has any points defined (x y or
    # z) it will use those points (except it will also start from the corner
    # for the search direction).
    corner = (point(img_stack.Corner) * lvec) + (search_pt * ~lvec)

    corner.to_from_rs()

    _logger.debug(f"ires:\t{img_res}\n"
                  f"np:\t{n_pixels}\n"
                  f"size:\t{size}\n"
                  f"res:\t{resolution}\n"
                  f"vc:\t{voxelcount}")

    voxelsizes = resolution

    _logger.debug(f"{voxelcount} {voxelsizes} {corner}")

    try:
        line_pos = [corner[ldir] + pt * resolution[ldir]
                    for pt in range(voxelcount[ldir])]
        lines = img_stack.ResampleImageDataOnGrids(NrVoxelsVec=[voxelcount],
                                                   VoxelSizesVec=[voxelsizes],
                                                   CornerVec=[corner])
        line = list(lines[0])
        if line_invert:
            line_pos = line_pos[::-1]
            line = line[::-1]

        edge_pairs = find_fwhm_edges(line, threshold)

        _logger.debug(f"{edge_pairs = }")
        _logger.debug(f"{line_pos = }")
        _logger.debug(f"{lvec = }")

        if not edge_pairs:
            # If we never found a good edge, the couch edge must be outside of
            # the FOV.  Return None
            return None

        # Return a list of paired edges in raystation coordinates.
        edge_pairs_rs = [(((line_pos[pair[0]] * lvec)
                           + (corner * ~lvec)).to_from_rs(),
                          ((line_pos[pair[1]] * lvec)
                           + (corner * ~lvec)).to_from_rs())
                         for pair in edge_pairs]
        _logger.debug(f"{edge_pairs_rs = }")
        return edge_pairs_rs

        # Return a simlpe list of edges in raystation coordinates.
        return [((line_pos[x] * lvec)
                 + (corner * ~lvec)).to_from_rs() for x in edge_pairs]

    except (TypeError, ValueError, IndexError, SystemError) as e:
        _logger.exception(e)
        return None


def find_first_edge(img_stack, search_start=None,
                    x_avg=None, y_avg=None, z_avg=None,
                    line_direction=None, threshold=None, rising_edge=True):
    kwargs = {k: v for k, v in locals().items() if v is not None}
    del kwargs['img_stack']
    del kwargs['rising_edge']
    return find_edges(img_stack, **kwargs)[0][not rising_edge]


def holes_by_width(edges: Sequence[Tuple[point, point]],
                   width: float,
                   tolerance: float = 0.2,
                   rising_to_falling: bool = True
                   ) -> List[point]:
    """
    Returns a list of point, width pairs for each edge that is close to the
    width specified (to within the _tolerance_ value).
    """
    edge_pair_centers = []

    if not rising_to_falling:
        raise NotImplementedError("Falling to rising edge not implemented.")

    for i, pair_i in enumerate(edges):
        # Loop through all falling edge points after i
        for pair_next in edges[i:]:
            _logger.debug(f"On index {i} {pair_i!s} looking at {pair_next!s}")
            center = (pair_i[0] + pair_next[1])/2.
            _logger.debug(f"On index {i} {pair_i[0]!s} to "
                          f"{pair_next[1]!s} center {center!s}")
            dist = (pair_i[0] - pair_next[1]).magnitude
            _logger.debug(f"Point distance is {dist:.2f}")
            if abs(dist - width) <= tolerance:
                edge_pair_centers.append(Hole(center, dist))

    return sorted(edge_pair_centers)


class _M():
    _I = [[1, 0, 0],
          [0, 1, 0],
          [0, 0, 1]]
    matrix = None
    """Simple matrix class for 3x3"""
    def __init__(self, matrix=None):
        if matrix is None:
            matrix = self._I
        elif hasattr(matrix, 'matrix'):
            matrix = matrix.matrix
        elif len(matrix) != 3 or any([len(r) != 3 for r in matrix]):
            raise ValueError("Must be a 3x3 matrix.")

        self.matrix = [[v for v in r] for r in matrix]

    def __mul__(self, other):
        m = [[sum(left*right for left, right in zip(lrow, rcol))
              for rcol in zip(*other.matrix)]
             for lrow in self.matrix]
        return type(self)(m)

    def __imul__(self, other):
        self.matrix = (self*other).matrix
        return self

    def __repr__(self):
        return '{}({})'.format(self.__class__.__name__, repr(self.matrix))

    def __str__(self):
        return '[{}]'.format(',\n'.join(map(repr, self.matrix)))

    def __iter__(self):
        return self.matrix.__iter__()


class AffineMatrix():
    x = 0
    y = 0
    z = 0

    pitch = 0
    yaw = 0
    roll = 0

    order = 'pyr'
    _gantry_order = 'ryp'

    rot_mats = None
    _trans = None

    def __init__(self, x=0, y=0, z=0, pitch=0, yaw=0, roll=0,
                 invert_t=False, order='pyr'):
        self.x = x
        self.y = y
        self.z = z
        self.pitch = pitch
        self.yaw = yaw
        self.roll = roll
        self.invert_t = invert_t

        self.rot_mats = {}

        self.order = order
        self._validate_order()

    def _validate_order(self):
        if self.order.lower() == 'gantry':
            self.order = self._gantry_order
        elif (set([x for x in self.order]) != {'p', 'y', 'r'}
              or len(self.order) != 3):
            self.order = 'pyr'

    def _rebuild_matrices(self):
        alpha = self.roll
        beta = self.yaw
        gamma = self.pitch

        sa = sin(alpha*pi/180.)
        ca = cos(alpha*pi/180.)
        sb = sin(beta*pi/180.)
        cb = cos(beta*pi/180.)
        sg = sin(gamma*pi/180.)
        cg = cos(gamma*pi/180.)

        self.rot_mats['p'] = _M([[  1,   0,   0],   # noqa: E201
                                 [  0,  cg, -sg],   # noqa: E201
                                 [  0,  sg,  cg]])  # noqa: E201
        self.rot_mats['y'] = _M([[ cb,   0,  sb],   # noqa: E201
                                 [  0,   1,   0],   # noqa: E201
                                 [-sb,   0,  cb]])  # noqa: E201
        self.rot_mats['r'] = _M([[ ca, -sa,   0],   # noqa: E201
                                 [ sa,  ca,   0],   # noqa: E201
                                 [  0,   0,   1]])  # noqa: E201

        out_mat = _M()

        self._validate_order()

        for card in self.order[::-1]:
            out_mat *= self.rot_mats[card]

        self._rot_matrix = out_mat
        self._trans = [self.x, self.y, self.z]

    @property
    def matrix(self):
        self._rebuild_matrices()
        m = _M(self._rot_matrix)
        return (list(map(list.__add__, m, [[v] for v in self._trans]))
                + [[0, 0, 0, 1]])

    @property
    def rs_matrix(self):
        """
        Get matrix for Raystation given transform.  Angles in degrees.
        (default for Presented for pitch, then yaw, then roll).

        alpha = self.roll
        beta = self.yaw
        gamma = self.pitch

        sa = sin(alpha*pi/180.)
        ca = cos(alpha*pi/180.)
        sb = sin(beta*pi/180.)
        cb = cos(beta*pi/180.)
        sg = sin(gamma*pi/180.)
        cg = cos(gamma*pi/180.)
        x = self.x*(-1)**int(self.invert_t)
        y = self.y*(-1)**int(self.invert_t)
        z = self.z*(-1)**int(self.invert_t)

        m = {'M11': ca*cb, 'M12': ca*sb*sg-sa*cg,
        'M13': ca*sb*cg+sa*sg, 'M14': x,
        'M21': sa*cb, 'M22': sa*sb*sg+ca*cg, 'M23': sa*sb*cg-ca*sg, 'M24': y,
        'M31': -sb,   'M32': cb*sg,          'M33': cb*cg,          'M34': z,
        'M41': 0,     'M42': 0,              'M43': 0,              'M44': 1}
        """
        m = self.matrix
        odict = {'M{}{}'.format(ri+1, ci+1): value
                 for ri, row in enumerate(m)
                 for ci, value in enumerate(row)}

        return odict
