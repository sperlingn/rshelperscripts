import logging
from math import sqrt, sin, cos, pi
from typing import Sequence, List, Tuple
from .external import (rs_callable, rs_hasattr, rs_getattr,
                       IndirectInheritanceClass)
from .rsdicomread import read_dataset

_logger = logging.getLogger(__name__)

VALID_MODALITIES = ['CT']


def floatable_attr(obj, attrname):
    try:
        return float(getattr(obj, attrname)) is not None
    except (KeyError, TypeError, ValueError, AttributeError):
        return False


class point(dict):
    _COORDS = ['x', 'y', 'z']
    _precision = 2

    def __init__(self, x=None, y=None, z=None, precision=2):
        super(point, self).__init__(self)

        for coord in self._COORDS:
            self[coord] = 0

        self._precision = precision

        try:
            if isinstance(x, dict):
                self.update(x)
            elif all(floatable_attr(x, c) for c in self._COORDS):
                # Assume this is a point like and build from this:
                for coord in self._COORDS:
                    self[coord] = getattr(x, coord)
            elif (x is not None and y is None and z is None
                  and f'{x}'.replace('.', '').lstrip('-').isdecimal()):
                # Looks like x is a single number...
                for coord in self._COORDS:
                    self[coord] = float(f'{x}')
            elif len(x) == len(self._COORDS):
                for coord, val in zip(self._COORDS, x):
                    self[coord] = val
            else:
                raise TypeError
        except TypeError:
            self.update({'x': x if x else 0,
                         'y': y if y else 0,
                         'z': z if z else 0})

        self.__changed__()

    @classmethod
    def __contains__(cls, key):
        return key in cls._COORDS

    @classmethod
    def __ispointlike__(cls, obj):
        try:
            if isinstance(obj, cls):
                return True
            if (all(floatable_attr(obj, c) for c in cls._COORDS)
                or all(((c in obj and float(obj[c]) is not None)
                        for c in cls._COORDS))
                or (len(obj) == len(cls._COORDS)
                    and all(float(v) is not None for v in obj))):
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
        self.__changed__()

    @property
    def y(self):
        return self['y']

    @y.setter
    def y(self, value):
        self['y'] = value
        self.__changed__()

    @property
    def z(self):
        return self['z']

    @z.setter
    def z(self, value):
        self['z'] = value
        self.__changed__()

    @property
    def to_tup(self):
        return tuple(self[coord] for coord in self._COORDS)

    @property
    def magnitude(self):
        return sqrt(sum([v**2 for v in self.values()]))

    def normalize(self):
        return self.__idiv__(self.magnitude)

    @property
    def normalized(self):
        return self/self.magnitude

    def _round(self):
        if self._precision:
            for c in self._COORDS:
                if self[c] is not None:
                    self[c] = round(self[c], self._precision)

    def __changed__(self):
        self._round()

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
        self.__changed__()
        return self

    def __isub__(self, other):
        return self.__iadd__(-other)

    def __imul__(self, other):
        new = self * other
        for key in new:
            self[key] = new[key]
        self.__changed__()
        return self

    def __idiv__(self, other):
        return self.__imul__(1./other)

    def __itruediv__(self, other):
        return self.__idiv__(other)

    def __lt__(self, other):
        if self.__ispointlike__(other):
            other_p = point(other)
            return all((self[c] < other_p[c] for c in self))
        else:
            raise NotImplementedError

    def __abs__(self):
        return type(self)({k: abs(self[k]) for k in self})

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
        try:
            return f"({self.x:.2f}, {self.y:.2f}, {self.z:.2f})"
        except TypeError:
            return super().__str__()

    def __repr__(self):
        return "point({})".format(super(point, self).__repr__())


class Hole(object):
    diameter = 0.0
    center = None

    def __init__(self, center, diameter):
        self.center = point(center)
        self.diameter = float(diameter)

    def __lt__(self, other):
        return self.diameter < other.diameter

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


class OverridenAttribute:
    def __set_name__(self, owner, attrname):
        self._attrname = attrname

    def __get__(self, obj, objtype=None):
        raise AttributeError(f'{objtype.__name__!r}.{self._attrname!r}'
                             ' is overriden (removed).')


class BoundingBox(list):
    __delitem__ = OverridenAttribute()
    __imul__ = OverridenAttribute()
    pop = OverridenAttribute()
    remove = OverridenAttribute()
    clear = OverridenAttribute()
    # __contains__ = OverridenAttribute()  # Might be okay to leave this...

    # TODO: Continue work on list inheritence
    def __init__(self, bbin=None):
        _min = None     # point() minimum
        _max = None     # point() maximum
        if bbin:
            if point.__ispointlike__(bbin):
                try:
                    _min = point(bbin)
                    _max = _min
                except (ValueError, TypeError):
                    pass
            elif self.__ispointlistlike__(bbin):
                # Might be a list of points.
                _min, _max = self.__minmax_pt_list__(bbin)
            elif self.__ispointlistlistlike__(bbin):
                _min, _max = self.__minmax_pt_list__(*bbin)

        super().__init__((_min, _max))

    @property
    def _min(self):
        return self[0]

    @_min.setter
    def _min(self, value):
        self[0] = point(value)

    @property
    def _max(self):
        return self[1]

    @_max.setter
    def _max(self, value):
        self[1] = point(value)

    @staticmethod
    def sort(*args, **kwargs):
        pass

    @classmethod
    def __ispointlistlistlike__(cls, obj):
        try:
            return all((cls.__ispointlistlike__(i) for i in obj))
        except (TypeError, ValueError, IndexError):
            return False

    @classmethod
    def __ispointlistlike__(cls, obj):
        if isinstance(obj, cls) or rs_callable(obj, 'GetBoundingBox'):
            return True
        try:
            return all((point.__ispointlike__(p) for p in obj))
        except (TypeError, ValueError, IndexError):
            return False

    @classmethod
    def __minmax_pt_list__(cls, *args):
        point_list = []
        for i, pt_or_list in enumerate(args):
            if cls.__ispointlistlistlike__(pt_or_list):
                point_list += [cls.__minmax_pt_list__(*pt_or_list)]
            elif cls.__ispointlistlike__(pt_or_list):
                if rs_callable(pt_or_list, 'GetBoundingBox'):
                    try:
                        pt_or_list = pt_or_list.GetBoundingBox()
                    except Exception:
                        continue
                point_list += [*map(point, pt_or_list)]
            elif point.__ispointlike__(pt_or_list):
                point_list += [point(pt_or_list)]
            else:
                raise TypeError(f"Argument {i} was not a point or"
                                f" a list of points ({pt_or_list})")

        if not point_list:
            raise ValueError("No valid points passed")

        min_p, max_p = map(point, zip(*map(lambda p: (min(p), max(p)),
                                           zip(*map(lambda p: point(p).to_tup,
                                                    point_list)))))
        return min_p, max_p

    def __add__(self, other):
        return type(self)([*self.__minmax_pt_list__(self, other)])

    def __iadd__(self, other):
        self._min, self._max = self.__minmax_pt_list__(self, other)
        return self

    def append(self, item):
        self += item

    def copy(self):
        return type(self)(self)

    @property
    def lower(self):
        return point(self[0])

    @property
    def upper(self):
        return point(self[1])

    @property
    def size(self):
        return self._max - self._min

    @property
    def center(self):
        return (self._max + self._min) / 2

    def limit(self, other, dim):
        other_bb = BoundingBox(other)
        dim_dir = 0
        if dim[0] in '+-':
            dim_dir = {'+': 1, '-': -1}[dim[0]]
            dim = dim[1]
        if dim_dir <= 0:
            self._min[dim] = other_bb._min[dim]
        if dim_dir >= 0:
            self._max[dim] = other_bb._max[dim]

    def limitz(self, other, infonly=False):
        dim = '-z' if infonly else 'z'
        self.limit(other, dim)

    def dosegrid_params(self, resolution=0.2, margin=0.2):
        margin = point(margin)
        resolution = point(resolution)
        new_corner = self.lower - margin
        new_nrvox = (self.size + 2*margin) / resolution
        return {'Corner': new_corner,
                'VoxelSize': resolution,
                'NumberOfVoxels': new_nrvox}

    def box_geometry_params(self, margin=0.2):
        margin = point(margin)

        size = self.size + 2*margin
        center = self.center - margin

        return {'Size': size,
                'Center': center,
                'Representation': "TriangleMesh",
                'VoxelSize': None}


class CT_Image_Stack(IndirectInheritanceClass):
    _size = None
    _bounding_box = None
    _npixels = None
    _res = None
    _img_stack = None
    DICOM = None

    def __init__(self, img_stack):
        self._img_stack = img_stack
        if abs(point(img_stack.SliceDirection)) != point.Z():
            raise NotImplementedError("Can only handle Z direction scans.")

        z_res = ((img_stack.SlicePositions[1] - img_stack.SlicePositions[0])
                 * img_stack.SliceDirection.z)

        self._res = point({'x': img_stack.PixelSize.x,
                           'y': img_stack.PixelSize.y,
                           'z': z_res})

        self._npixels = point({'x': img_stack.NrPixels.x,
                               'y': img_stack.NrPixels.y,
                               'z': len(img_stack.SlicePositions)})

        self._size = self._npixels * self._res

        self._bounding_box = BoundingBox(img_stack)

        self.DICOM, = read_dataset(self._img_stack)

    @property
    def size(self):
        return abs(self._size)

    @property
    def n_pixels(self):
        return self._npixels.copy()

    def GetBoundingBox(self):
        return self.boundingbox

    @property
    def boundingbox(self):
        return self._bounding_box.copy()

    @property
    def res(self):
        return self._res.copy()

    @property
    def maxz(self):
        return self._bounding_box[1].z

    @property
    def minz(self):
        return self._bounding_box[0].z

    @property
    def image_center(self):
        return self._bounding_box.center

    @property
    def corner(self):
        return self._bounding_box.lower

    @staticmethod
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

        # Fall to here when we have an IndexError, and when we run out of
        # points in the array.
        if last_i:
            indices.append((last_i, -1))
        return indices

    def find_edges(self, search_start=None, x_avg=None, y_avg=None,
                   z_avg=None, direction='-y', threshold=-600):
        line_invert = '-' in direction
        ldir = direction[-1]
        lvec = point({ldir: 1})

        resolution = self.res
        if x_avg is not None:
            resolution.x = x_avg

        if y_avg is not None:
            resolution.y = y_avg

        if z_avg is not None:
            resolution.z = z_avg

        voxelcount = (((self.size//resolution) - 1) * lvec) + 1

        # Build a point out of the search start, and any coordinate which is
        # None should be set to the image_center for that coordinate.
        image_center = self.image_center
        search_pt = point({idx: (v if v is not None
                                 else image_center[idx])
                           for idx, v in point(search_start).items()})

        # If search_start was not set, this will start the search from the
        # image center in all directions except the search direction where it
        # will start at the corner.  Otherwise, if search_start has any points
        # defined (x y or z) it will use those points (except it will also
        # start from the corner for the search direction).

        corner = (self.corner * lvec) + (search_pt * ~lvec)

        _logger.debug(f"\n\t{corner=}\n\t{self.corner=}\n\t{lvec=}")

        _logger.debug("Searching:\n\t"
                      f"ires:\t{self._res}\n\t"
                      f"np:\t{self._npixels}\n\t"
                      f"size:\t{self._size}\n\t"
                      f"res:\t{resolution}\n\t"
                      f"vc:\t{voxelcount}\n\t"
                      f"corner:\t{corner}\n\t"
                      f"search_pt:\t{search_pt}")

        voxelsizes = resolution

        _logger.debug(f"{voxelcount=} {voxelsizes=} {corner=}")

        try:
            line_pos = [corner[ldir] + pt * resolution[ldir]
                        for pt in range(voxelcount[ldir])]

            ridog_kwargs = {"NrVoxelsVec": [voxelcount],
                            "VoxelSizesVec": [voxelsizes],
                            "CornerVec": [corner]}
            lines = self._img_stack.ResampleImageDataOnGrids(**ridog_kwargs)
            line = list(lines[0])
            if line_invert:
                line_pos = line_pos[::-1]
                line = line[::-1]

            edge_pairs = self.find_fwhm_edges(line, threshold)

            _logger.info("Found line:\n\t"
                         f"{edge_pairs = }\n\t"
                         f"{lvec = }")
            _logger.debug("Additional...\n\t"
                          f"{line_pos = }\n\t"
                          f"{line = }")

            if not edge_pairs:
                # If we never found a good edge, the couch edge must be outside
                # of the FOV.  Return Empty list
                return []

            # Return a list of paired edges in raystation coordinates.
            edge_pairs_rs = [(((line_pos[pair[0]] * lvec)
                               + (corner * ~lvec)),
                              ((line_pos[pair[1]] * lvec)
                               + (corner * ~lvec)))
                             for pair in edge_pairs]
            _logger.debug(f"{edge_pairs_rs = }")
            _loc_ = locals()
            _logger.log(level=logging.DEBUG-1, msg=f"\n{_loc_=}",
                        stack_info=True)
            return edge_pairs_rs

            # Return a simlpe list of edges in raystation coordinates.
            return [((line_pos[x] * lvec)
                    + (corner * ~lvec)) for x in edge_pairs]

        except (TypeError, ValueError, IndexError, SystemError) as e:
            _logger.exception(e)
            return []

    def find_first_edge(self, search_start=None,
                        x_avg=None, y_avg=None, z_avg=None,
                        direction=None, threshold=None, rising_edge=True):

        kwargs = {k: v for k, v in locals().items() if v is not None}
        del kwargs['rising_edge']
        del kwargs['self']
        _logger.debug(f"{kwargs=}")
        return self.find_edges(**kwargs)[0][not rising_edge]

    @staticmethod
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
            raise NotImplementedError("Falling to rising not implemented.")

        for i, pair_i in enumerate(edges):
            # Loop through all falling edge points after i
            for pair_next in edges[i:]:
                _logger.debug(f"On index {i} {pair_i!s} "
                              f"looking at {pair_next!s}")
                center = (pair_i[0] + pair_next[1])/2.
                _logger.debug(f"On index {i} {pair_i[0]!s} to "
                              f"{pair_next[1]!s} center {center!s}")
                dist = (pair_i[0] - pair_next[1]).magnitude
                _logger.debug(f"Point distance is {dist:.2f}")
                if abs(dist - width) <= tolerance:
                    edge_pair_centers.append(Hole(center, dist))

        return sorted(edge_pair_centers)


class Image_Series():
    _series = None
    img_stack = None
    UID = ''
    DICOM = None
    structure_sets = None

    def __init__(self, series, structure_sets=None):
        self._series = series

        self.UID = series.ImportedDicomUID

        self.img_stack = CT_Image_Stack(series.ImageStack)

        self.DICOM = self.img_stack.DICOM

        if structure_sets is not None:
            try:
                self.structure_sets = [s for s in structure_sets]
            except TypeError:
                self.structure_sets = [structure_sets]
        else:
            self.structure_sets = []

        if self.DICOM.Modality not in VALID_MODALITIES:
            raise NotImplementedError("Unknown/unhandled modality "
                                      f"{self.DICOM.Modality} in "
                                      f"series {self._series} ({self.UID=})")

    def __getattr__(self, attr):
        if rs_hasattr(self._series, attr):
            return rs_getattr(self._series, attr)
        elif hasattr(self.img_stack, attr):
            return getattr(self.img_stack, attr)

        raise AttributeError


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

        if point.__ispointlike__(x):
            pt = point(x)
            for coord in pt._COORDS:
                setattr(self, coord, pt[coord])
        else:
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

        m = {
        'M11':ca*cb,  'M12': ca*sb*sg-sa*cg, 'M13': ca*sb*cg+sa*sg, 'M14': x,
        'M21': sa*cb, 'M22': sa*sb*sg+ca*cg, 'M23': sa*sb*cg-ca*sg, 'M24': y,
        'M31': -sb,   'M32': cb*sg,          'M33': cb*cg,          'M34': z,
        'M41': 0,     'M42': 0,              'M43': 0,              'M44': 1}
        """
        m = self.matrix
        odict = {'M{}{}'.format(ri+1, ci+1): float(value)
                 for ri, row in enumerate(m)
                 for ci, value in enumerate(row)}

        return odict

    def __repr__(self):
        return '{}({})'.format(self.__class__.__name__, repr(self.matrix))

    def __str__(self):
        return '\n'.join('\t'.join(f'{c:.2f}' for c in r) for r in self.matrix)
