from typing import List, Tuple, get_type_hints
from random import choice, randint, uniform
from copy import deepcopy
from logging import getLogger
from collections.abc import Sequence
_logger = getLogger(__name__)

try:
    from System import DateTime as _datetime

    class dt_pickle(DateTime):
        def __reduce_ex__(self, version):
            return (self.FromBinary, (self.ToBinary(),))

except ImportError:
    from datetime import datetime as _datetime

    class DateTime(_datetime):
        @property
        def Now(self):
            return self.now()

    dt_pickle = DateTime

    del _datetime


def build_mock_string(obj):
    for a, v in [(at, getattr(obj, at)) for at in dir(obj)
                 if not callable(getattr(obj, at))]:
        at = f'{type(v)}'.split("'")[1]
        outstr = f'{a} : '
        if 'connect' in at or 'NoneType' in at:
            outstr += f'Mock{a}'
        else:
            outstr += f'{at}'

        print(outstr)


def rand_from_hint(attr_type, attr_name=''):
    # Build an object from an attribute type.
    # Right now only handle List, Tuple, and proper types
    # TODO: When moving to Python 3.9+ we can use hinting to also
    #       create generics types with ranges and length hints
    if isinstance(attr_type, type):
        if attr_type == int:
            return randint(1, 20)
        elif attr_type == float:
            return uniform(-20, 20)
        elif attr_type == str:
            return f'{attr_name}_str'
        elif attr_type == DateTime:
            return DateTime.Now
        else:
            return attr_type()
    elif attr_type is None:
        # Special case for None
        return None
    else:
        TYPE_MAP = {'List': list,
                    'Tuple': tuple}
        attr_type_n = getattr(attr_type, '_name', None)
        argslist = getattr(attr_type, '__args__', None)
        if attr_type_n in TYPE_MAP and argslist:
            return TYPE_MAP[attr_type_n](rand_from_hint(attr)
                                         for attr in argslist)


def clamp(val, min_v, max_v=None):
    if max_v is None:
        max_v = min_v['max']
        min_v = min_v['min']
    return max(min(val, max_v), min_v)


def gap_pair_to_limit(pair_in, limits, GAP):
    pair = list(map(clamp, pair_in, limits))
    if pair[1] - pair[0] >= GAP:
        return pair

    center = sum(pair) / 2.
    if center + (GAP / 2.) > limits[0]['max']:
        return [limits[0]['max'],
                limits[0]['max'] + GAP]
    elif center - (GAP / 2.) < limits[1]['min']:
        return [limits[1]['min'] - GAP,
                limits[1]['min']]
    else:
        return [center - (GAP / 2.),
                center + (GAP / 2.)]


_MOCKERY_MAPPINGS = {}


def MakeMockery(root, attr, from_sequence=False):
    # Makes a mockery of an object, if it is a known type and mapping.

    # If we can't access the value, return None
    try:
        if from_sequence:
            val = root
        else:
            val = getattr(root, attr)
    except (AttributeError, ValueError):
        return None

    cls = val.__class__

    # First, find builtins that aren't mutable types can just be copied
    if cls.__module__ in ('builtins', '__builtins__', '__builtin__'):
        if not issubclass(cls, Sequence):
            # Not a sequence, is builtin, should be safe to just use.
            return val

        if isinstance(val, str):
            return val

        if cls in (list, tuple, set):
            return cls(MakeMockery(v, attr, True) for v in val)

        if cls in (dict):
            return {k: MakeMockery(v, k, True) for k, v in val.items()}

    # Other objects known to be okay to return a direct copy of
    if cls.__name__ in ('DateTime', 'Color'):
        return val

    if isinstance(val, MockObject):
        return deepcopy(val)

    if cls.__module__ in ('connect.connect_cpython'):
        if cls.__name__ in ('array_list',
                            'PyScriptObjectCollection'):
            return [MakeMockery(v, attr, True) for v in val]
        elif cls.__name__ in ('ExpandoDictionary'):
            return {k: MakeMockery(v, k, True) for k, v in val.items()}

    if cls.__name__ in ('numpy.ndarray'):
        return val.tolist()

    if attr in _MOCKERY_MAPPINGS:
        return _MOCKERY_MAPPINGS[attr](val)

    raise ValueError(f"Unable to translate attribute {attr} of class "
                     f"'{val.__class__}' and value '{val}' to a MockObject.")


class MetaSlotsFromHints(type):
    def __new__(metacls, name, bases, dct):
        hints = dct.get('__annotations__', {}).keys()
        slots = set(dct.get('__slots__', ()))
        slots |= hints

        # Exclude any class variables from slots.
        slots -= dct.keys()

        # Allow dict if we haven't defined any hints.
        if not hints:
            slots.add('__dict__')
        dct['__slots__'] = tuple(slots)
        return super().__new__(metacls, name, bases, dct)


class MockObject(object, metaclass=MetaSlotsFromHints):
    # Mock object class which can be subclassed
    # If there are no type hints set, then the getattr function will
    # create the attribute requested and assign it a new MockObject.
    # Otherwise, the getattr function will perform normally.
    _COPY_ONLY: set = None
    _COPY_EXCLUDE: set = None

    def __init__(self, *args, **kwargs):
        hints = get_type_hints(self.__class__)
        if hints is None:
            hints = {k: None for k in kwargs}

        known_keys = {key for key in hints if key[0] != '_'}

        if len(args) == 1:
            # Don't retain build fake values if we were passed an argument,
            #  instead assume that we copy it and end.
            return self.CopyFrom(args[0])
        elif len(args) > 1:
            raise ValueError("Can only accept up to 1 non-keyword argument.")

        # Don't set any defaults for anything passed as a kwarg
        for attr in known_keys - kwargs.keys():
            attr_type = hints[attr]
            val = rand_from_hint(attr_type, attr)
            setattr(self, attr, val)

        # Set values from keys passed in kwargs.
        if kwargs:
            excess_keys = kwargs.keys() - known_keys if known_keys else None
            if excess_keys:
                raise ValueError(f"'{self.__class__.__name__}' does not "
                                 "support the following passed attributes: "
                                 f"'{excess_keys}'")

            for attr, val in ((k, kwargs[k]) for k
                             in known_keys & kwargs.keys()):
                setattr(self, attr, val)


    def __str__(self, depth=1):
        lines = []
        my_items = {attr: getattr(self, attr) for attr in self.__slots__
                    if attr[0] != '_'}
        my_items.update(getattr(self, '__dict__', {}))

        for var, val in my_items.items():
            line = '\t'*depth + f'{var} = '
            if isinstance(val, MockObject):
                line += val.__str__(depth+1)
            elif ((isinstance(val, list) or isinstance(val, tuple))
                  and all(map(lambda v: isinstance(v, MockObject), val))):
                bra = '[' if isinstance(val, list) else '('
                ket = ']' if isinstance(val, list) else ')'
                sublines = [x.__str__(depth+1) for x in val]
                if len(sublines) == 1:
                    line += bra + sublines[0].lstrip() + ket
                else:
                    line += '\n' + ''.join(sublines)
            else:
                line += f'{val!r}'

            lines.append(line)

        str_n = '\n'.join(lines).lstrip()
        if '\n' in str_n:
            str_n = '\n' + '\t'*depth + str_n
        return f'{self.__class__.__name__}({str_n})'

    def __repr__(self):
        return str(self)

    def __enforce_rules__(self):
        # Function to force object to conform to rules.
        # Run at the end of init.
        pass

    def CopyFrom(self, other):
        hints = get_type_hints(self.__class__)
        known_keys = {key for key in hints if key[0] != '_'}
        try:
            keys = set(dir(other))

            for attr, val in ((k, MakeMockery(other, k))
                             for k in known_keys & keys):
                setattr(self, attr, val)
        except (ValueError, AttributeError, TypeError) as e:
            _logger.debug(f"Couldn't clone: {e}", exc_info=True)

    def CopyTo(self, other):
        # Copies values in self to other if keys exist in both.
        # If self has _COPY_ONLY set, this will only copy those attributes,
        # otherwise, it will copy all type hinted parameters EXCEPT those
        # list in _COPY_EXCLUDE.
        hints = get_type_hints(self)
        attrs = set(self._COPY_ONLY if self._COPY_ONLY else hints.keys())
        attrs -= set(self._COPY_EXCLUDE)

        for attr, val in [(attr, getattr(self, attr)) for attr in attrs
                          if attr[0] != '_'
                          and hasattr(other, attr) 
                          and not callable(getattr(other, attr))]:
            try:
                setattr(other, attr, val)
            except (TypeError, ValueError):
                _logger.debug(f"Couldn't set value of attribute '{attr}' to "
                              f"'{val}' on '{other}'", exc_info=True)

    def __reduce_ex__(self, version):
        # Hack to allow us to use deepcopy which uses protocol version 4
        out = super().__reduce_ex__(version)
        if version == 4:
            # Currently deepcopy uses version 4, we need to translate some
            #  objects which do not support pickling such as DateTime
            c_fn, bases, dictandslots, *rest = out
            for indict in dictandslots:
                if indict is not None:
                    for val in indict.values():
                        if isinstance(val, DateTime):
                            val.__class__ = dt_pickle

            out = (c_fn, bases, dictandslots, *rest)
        return out



class MockOrganData(MockObject):
    OrganType: str
    RbeCellTypeName: str
    ResponseFunctionTissueName: str


class MockStructure(MockObject):
    Name: str
    OrganData: MockOrganData

    def __init__(self, name='ROI_1', roitype='Unknown'):
        super().__init__(Name=name,
                         OrganData=MockOrganData(OrganType=roitype))


class MockPrescriptionDoseReference(MockObject):
    DoseValue: float
    OnStructure: MockStructure

    def __init__(self, roi=None, dosevalue=1000):
        super().__init__(DoseValue=dosevalue,
                         OnStructure=(MockStructure() if roi is None else roi))


class MockPrescription(MockObject):
    PrimaryPrescriptionDoseReference: MockPrescriptionDoseReference
    PrescriptionDoseReferences: List[MockPrescriptionDoseReference]

    def __init__(self, pdrlist=None):
        try:
            self.PrescriptionDoseReferences = pdrlist
            self.PrimaryPrescriptionDoseReference = pdrlist[0]
        except (TypeError, IndexError):
            mpdr = MockPrescriptionDoseReference()
            self.PrimaryPrescriptionDoseReference = mpdr
            self.PrescriptionDoseReferences = [mpdr]


class MockFractionDose(MockObject):
    DoseValues: List[float]


class MockPatientModel(MockObject):
    RegionsOfInterest: List[MockStructure]


class MockCollisionProperties(MockObject):
    ForPatientModel: MockPatientModel


class MockPatientSetup(MockObject):
    CollisionProperties: MockCollisionProperties


class MockBeamSet(MockObject):
    Prescription: MockPrescription
    FractionDose: MockFractionDose
    PatientSetup: MockPatientSetup
    Name: str

    def __init__(self, *args, name='BeamSet1', pdrlist=None,
                 pm: MockPatientModel = None, **kwargs):

        super().__init__(Name=name,
                         Prescription=MockPrescription(pdrlist))
        if pm:
            self.PatientSetup.CollisionProperties.ForPatientModel = pm


class MockFluence(MockObject):
    pass


class MockBlocks(MockObject):
    pass


class MockBoli(MockObject):
    pass


class MockCompensator(MockObject):
    pass


class MockOrm(MockObject):
    pass


class PointDict(dict):
    def __init__(self, *args, **kwargs):
        super().__init__()
        for i, a in enumerate(['x', 'y', 'z']):
            if a in kwargs:
                self[a] = kwargs[a]
            elif i < len(args):
                self[a] = args[i]
            else:
                self[a] = args[0] if len(args) == 1 else 0.


class MockAnnotation(MockObject):
    DisplayColor: str
    Name: str


class MockIsocenter(MockObject):
    Position: PointDict
    Annotation: MockAnnotation


class MockLayer(MockObject):
    LeafCenterPositions: List[float]
    LeafWidths: List[float]

    def __init__(self, lcps=None, lw=None, is_varian=True, is_HD=False):

        if is_varian:
            N_MLC = 60
            N_SMALL = 40
        else:
            N_MLC = 40
            N_SMALL = 0

        if is_HD:
            W_FULL = 0.5
            W_HALF = 0.25
            N_MLC = 60
            N_SMALL = 32
        else:
            W_FULL = 1.0
            W_HALF = 0.5

        if lcps and lw and len(lw) == len(lcps):
            self.LeafCenterPositions = list(lcps)
            self.LeafWidths = list(lw)
            N_MLC = len(self.LeafCenterPositions)
        else:
            self.LeafWidths = [W_FULL] * ((N_MLC - N_SMALL)//2)
            self.LeafWidths += [W_HALF] * (N_SMALL)
            self.LeafWidths += [W_FULL] * ((N_MLC - N_SMALL)//2)

            min_mlc = -(W_FULL * (N_MLC - N_SMALL) + W_HALF * N_SMALL)/2

            self.LeafCenterPositions = [min_mlc + i * W_FULL + W_FULL/2 for i
                                        in range(0, (N_MLC - N_SMALL)//2)]

            min_mlc = self.LeafCenterPositions[-1] + W_FULL/2

            if N_SMALL > 0:
                self.LeafCenterPositions += [min_mlc + i * W_HALF + W_HALF/2
                                             for i in range(0, N_SMALL)]
                min_mlc = self.LeafCenterPositions[-1] + W_HALF/2

            self.LeafCenterPositions += [min_mlc + i * W_FULL + W_FULL/2 for i
                                         in range(0, (N_MLC - N_SMALL)//2)]


class MockMachineReference(MockObject):
    MachineName: str
    CommissioningTime: DateTime
    Energy: int


class MockSegment(MockObject):
    CollimatorAngle: float
    DoseRate: float
    Fluence: MockFluence
    JawPositions: Tuple[(float,)*4]
    LeafPositions: Tuple[(Tuple[(float,)*60],)*2]
    RelativeWeight: float
    SegmentNumber: int

    def __enforce_rules__(self):
        # Clean leaf and jaw positions to feasible
        MLC_GAP = 0.5
        JAW_GAP = 0.1
        JAW_LIMITS = [{'min': -20, 'max': 2},
                      {'min': -2, 'max': 20},
                      {'min': -20, 'max': 10},
                      {'min': -10, 'max': 20}]

        MLC_LIMITS = {'min': -20,
                      'max': 20,
                      'ext': 15.5}

        jaws = [j for i, jp in enumerate(zip(*(iter(self.JawPositions),) * 2))
                for j in gap_pair_to_limit(jp,
                                           JAW_LIMITS[i*2:(i+1)*2],
                                           JAW_GAP)]

        BANK_LIMITS = [{'min': clamp(min(self.LeafPositions[0]), MLC_LIMITS),
                        'max': clamp(min(self.LeafPositions[0])
                                     + MLC_LIMITS['ext'], MLC_LIMITS)},
                       {'min': clamp(max(self.LeafPositions[1])
                                     - MLC_LIMITS['ext'], MLC_LIMITS),
                        'max': clamp(max(self.LeafPositions[1]), MLC_LIMITS)}]

        lp_pairs = map(lambda *pair: gap_pair_to_limit(pair,
                                                       BANK_LIMITS,
                                                       MLC_GAP),
                       *self.LeafPositions)

        self.JawPositions = jaws
        self.LeafPositions = [list(p) for p in zip(*lp_pairs)]


class MockBeam(MockObject):
    ArcRotationDirection: str
    ArcStopGantryAngle: float
    BeamMU: float
    BeamQualityId: str
    BlockTray: str
    Blocks: List[MockBlocks]
    Boli: List[MockBoli]
    Compensator: MockCompensator
    Cone: str
    CouchPitchAngle: float
    CouchRollAngle: float
    CouchRotationAngle: float
    CreatedDuringOptimization: bool
    DeliveryTechnique: str
    Description: str
    FilteredOrm: MockOrm
    Fluence: MockFluence
    GantryAngle: float
    InitialCollimatorAngle: float
    InitialJawPositions: Tuple[(float,)*4]
    IntendedJawPositionsForTomoBeam: Tuple[(float,)*2]
    Isocenter: MockIsocenter
    UpperLayer: MockLayer
    LowerLayer: MockLayer
    MachineReference: MockMachineReference
    Name: str
    Number: int
    Orm: MockOrm
    PatientPosition: str
    PlanGenerationTechnique: str
    Segments: List[MockSegment]
    Wedge: str

    def __enforce_rules__(self):
        # Ensure unique parameters for required items.
        try:
            for i, segment in self.Segments:
                segment.SegmentNumber = i
        except TypeError:
            pass

        self.BeamMU = max(0, self.BeamMU)


class MockPlan(MockObject):
    BeamSets: List[MockBeamSet]
    DicomPlanLabel: str

    def __init__(self, *args, name="Plan1", **kwargs):
        super().__init__(*args, DicomPlanLabel=f'{name}', **kwargs)

    def __enforce_rules__(self):
        # Make beamset names unique, build beamset getter
        # TODO:
        pass


class MockCase(MockObject):
    TreatmentPlans: List[MockPlan]
    BodySite: str
    Comments: str
    CaseName: str
    PerPatientUniqueId: str

    def __init__(self, *args, plans=None, **kwargs):
        if plans is not None:
            super().__init__(*args, TreatmentPlans=plans, **kwargs)
        else:
            super().__init__(*args, **kwargs)

    def __enforce_rules__(self):
        # Make sure plan names are unique
        # TODO:
        pass


class MockPatient(MockObject):
    Comments: str
    DateOfBirth: DateTime
    Gender: str
    Name: str
    PatientID: str
    Cases: List[MockCase]

    def __init__(self, *args,
                 name=None, id=None, dob=None, gender=None, cases=None,
                 **kwargs):
        n_args = {'Gender': gender if gender else choice(['Male', 'Female']),
                  'PatientID': id if id else f'99{randint(0,1e6):6d}',
                  'DateOfBirth': dob if dob else DateTime(randint(1920, 2010),
                                                          randint(1, 12),
                                                          randint(1, 28)),
                  'Name': name if name else choice(['DOE^JOHN',
                                                    'DOE^JANE',
                                                    'BAGGINS^BILBO',
                                                    'BAGGINS^FRODO',
                                                    'GAMGEE^SAMWISE',
                                                    'EVENSTAR^ARWEN',
                                                    'FINWE^GALADRIEL'])}
        kwargs.update(n_args)
        if cases is not None:
            kwargs['Cases'] = cases
        super().__init__(*args, **kwargs)

_MOCKERY_MAPPINGS.update({
    'OnStructure': MockStructure,
    'Patient': MockPatient,
    'Cases': MockCase,
    'BeamSets': MockBeamSet,
    'Segments': MockSegment,
    'UpperLayer': MockLayer,
    'Isocenter': MockIsocenter,
    'Fluence': MockFluence,
    'Annotation': MockAnnotation
    })