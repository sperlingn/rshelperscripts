from typing import List
from random import choice, randint

from System import DateTime


class MockObject(object):
    def __getattr__(self, attr):
        setattr(self, attr, MockObject())
        return getattr(self, attr)


class MockPatient(MockObject):
    Comments: str = ''
    DateOfBirth: DateTime
    Gender: str = ''
    Name: str = ''
    PatientID: str = ''
    Cases: list

    def __init__(self, name=None, id=None, dob=None, gender=None, cases=None):
        self.Gender = gender if gender else choice(['Male', 'Female'])
        self.PatientID = id if id else f'99{randint(0,1e6):6d}'
        self.DateOfBirth = dob if dob else DateTime(randint(1920, 2010),
                                                    randint(1, 12),
                                                    randint(1, 28))
        self.Name = name if name else choice(['DOE^JOHN',
                                              'DOE^JANE',
                                              'BAGGINS^BILBO',
                                              'BAGGINS^FRODO',
                                              'GAMGEE^SAMWISE',
                                              'EVENSTAR^ARWEN',
                                              'FINWE^GALADRIEL'])
        self.Cases = cases if cases else []


class MockStructure(MockObject):
    Name: str  # Wait for Py 3.10 for typing

    def __init__(self, name='ROI_1', roitype='Unknown'):
        self.Name = name
        self.OrganData.OrganType = roitype


class MockPrescriptionDoseReference(MockObject):
    DoseValue: float  # Wait for Py 3.10 for typing
    OnStructure: MockStructure  # Wait for Py 3.10 for typing

    def __init__(self, roi=None, dosevalue=1000):
        self.OnStructure = MockStructure() if roi is None else roi
        self.DoseValue = dosevalue


class MockCase(MockObject):
    TreatmentPlans: list
    BodySite: str = ''
    Comments: str = ''
    CaseName: str = ''
    PerPatientUniqueId: str = ''

    def __init__(self, plans=None):
        self.TreatmentPlans = plans if plans else []

    @property
    def Name(self): raise AttributeError


class MockPlan(MockObject):
    BeamSets: list
    DicomPlanLabel: str

    def __init__(self, name="Plan1"):
        self.BeamSets = []
        self.DicomPlanLabel = f'{name}'

    @property
    def Name(self): raise AttributeError


class MockPrescription(MockObject):
    PrimaryPrescriptionDoseReference: MockPrescriptionDoseReference
    PrescriptionDoseReferences: List[MockPrescriptionDoseReference]

    def __init__(self, pdrlist=None):
        try:
            self.PrescriptionDoseReferences = pdrlist
            self.PrimaryPrescriptionDoseReference = pdrlist[0]
        except TypeError:
            mpdr = MockPrescriptionDoseReference()
            self.PrimaryPrescriptionDoseReference = mpdr
            self.PrescriptionDoseReferences = [mpdr]


class MockFractionDose(MockObject):
    DoseValues = None


class MockPatientModel(MockObject):
    def __init__(self, roilist=None):
        self.RegionsOfInterest = roilist


class MockBeamSet(MockObject):
    Prescription: MockPrescription
    FractionDose: MockFractionDose
    Name: str

    def __init__(self, name='BeamSet1', pdrlist=None,
                 pm: MockPatientModel = None):
        self.Name = name
        self.Prescription = MockPrescription(pdrlist)
        if pm:
            self.PatientSetup.CollisionProperties.ForPatientModel = pm
