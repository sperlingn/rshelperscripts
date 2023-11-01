from enum import IntEnum
import sys
from copy import deepcopy
import logging as _logging
from uuid import uuid4
from dataclasses import dataclass
_logger = _logging.getLogger(__name__)


__opts = {'DUP_MAX_RECURSE': 10}

_NAMELIST = ['Name', 'DicomPlanLabel']


def helperoverride(function):
    function.__overridden__ = True
    return function


try:
    from System.Windows import MessageBox as _MessageBox
    from System.Windows.Controls import Button, TextBlock, DockPanel, Label
    from System import ArgumentOutOfRangeException, InvalidOperationException
    from System.IO import InvalidDataException
except ImportError:

    # TODO: Work to include a QT or other based dialog? Right now we can assume
    # that the Windows MessageBox will work for RS.  This is only for debugging
    # functions.
    @helperoverride
    class _MessageBox:
        def Show(*args, **kwargs):
            _logger.info("MessageBox: args={}, kwargs={}", args, kwargs)
            return True

    @helperoverride
    class ArgumentOutOfRangeException(IndexError):
        pass

    @helperoverride
    class InvalidOperationException(Exception):
        pass

    @helperoverride
    class InvalidDataException(ValueError):
        pass

    @helperoverride
    class Button:
        def __init__(self, *args, **kwargs):
            raise NotImplementedError("Only supported for CLR launch.")


class _CompositeActionDummy():
    _name = ""

    def __init__(self, *args, **kwargs):
        if 'name' in kwargs:
            self._name = kwargs['name']
        elif len(args) > 0:
            self._name = args[0]

    def __enter__(self):
        _logger.info("Entered {} Undo state.".format(self._name))
        return self

    def __exit__(self, e_type, e, e_traceback):
        if e_type is not None:
            _logger.exception('{!s}'.format(e))

        _logger.info("Exited  {} Undo state.".format(self._name))


class MB_Button(IntEnum):
    OK = 0
    OKCancel = 1
    YesNo = 4
    YesNoCancel = 3


class MB_Icon(IntEnum):
    Asterisk = 64
    Error = 16
    Exclamation = 48
    Hand = 16
    Information = 64
    None_ = 0
    Question = 32
    Stop = 16
    Warning_ = 48


class MB_Result(IntEnum):
    Cancel = 2
    No = 7
    None_ = 0
    OK = 1
    Yes = 6

    def __bool__(self):
        # Only return True for OK and Yes results.  Otherwise consider it a
        # No/False/Cancel result for bool check.
        return self in (MB_Result.OK, MB_Result.Yes)


class MB_Options(IntEnum):
    DefaultDesktopOnly = 131072
    None_ = 0
    RightAlign = 524288
    RtlReading = 1048576
    ServiceNotification = 2097152


def _Show_MB(*args, ontop=False):
    opt = MB_Options.DefaultDesktopOnly if ontop else MB_Options.None_
    res = _MessageBox.Show(*args, opt)
    try:
        return MB_Result(res)
    except ValueError:
        # New return type, just return it and log so we can add it later.
        _logger.warning(f'Unexpected message box result: {res}')
        return res


def Show_OK(message, caption, ontop=False, icon=MB_Icon.None_,
            defaultResult=MB_Result.None_):
    button = MB_Button.OK
    return _Show_MB(message, caption, button, icon, defaultResult, ontop=ontop)


def Show_Warning(message, caption, ontop=True):
    return Show_OK(message, caption, ontop, icon=MB_Icon.Warning_)


def Show_OKCancel(message, caption, ontop=False, icon=MB_Icon.None_,
                  defaultResult=MB_Result.None_):
    button = MB_Button.OKCancel
    return _Show_MB(message, caption, button, icon, defaultResult, ontop=ontop)


def Show_YesNo(message, caption, ontop=False, icon=MB_Icon.None_,
               defaultResult=MB_Result.None_):
    button = MB_Button.YesNo
    return _Show_MB(message, caption, button, icon, defaultResult, ontop=ontop)


def Show_YesNoCancel(message, caption, ontop=False, icon=MB_Icon.None_,
                     defaultResult=MB_Result.None_):
    button = MB_Button.YesNoCancel
    return _Show_MB(message, caption, button, icon, defaultResult, ontop=ontop)


def _await_user_input_mb(message):
    _logger.debug(f'Waited for user input: "{message}"')
    return Show_OK(f'{message}', "Awaiting Input", ontop=True)


try:
    from connect import RayWindow
except ImportError:
    try:
        import wpf
        from System.Windows import Window

        class RayWindow(Window):
            def LoadComponent(self, XAML):
                return wpf.LoadComponent(self, XAML)
    except ImportError:
        class RayWindow():
            def LoadComponent(self, XAML):
                raise NotImplementedError("Neither RS nor wpf in environment")


try:
    from connect import (get_current, CompositeAction as _CompositeActionOrig,
                         await_user_input as _await_user_input, set_progress)

    IN_RAYSTATION = True

except ImportError:
    # Replacement functions when not running in RS
    IN_RAYSTATION = False

    def get_current(name):
        # TODO: Might want to return a sample object that has reasonable
        # facimiles of the real objects for debugging.
        return None

    class _CompositeActionOrig(_CompositeActionDummy):
        pass

    _await_user_input = _await_user_input_mb

    def set_progress(message, percent):
        _logger.info(f"Progress: {message} ({percent:.0%})")

finally:

    @helperoverride
    class CompositeAction:
        _clsinstance = None
        _instance = None
        _blocked = False
        my_args = None
        _dummyclass = _CompositeActionDummy
        _realclass = _CompositeActionOrig

        def __init__(self, *args, **kwargs):
            self.my_args = (args, kwargs)
            self.instance

        @property
        def instance(self):
            cls = type(self)
            if not self._instance:
                (args, kwargs) = self.my_args
                if cls._blocked:
                    self._instance = cls._dummyclass(*args, **kwargs)
                elif cls._clsinstance and cls._clsinstance != self:
                    self._instance = cls._dummyclass(*args, **kwargs)
                else:
                    self._instance = cls._realclass(*args, **kwargs)
                    cls._clsinstance = self

            return self._instance

        @classmethod
        def block(cls):
            cls._blocked = True

        @classmethod
        def unblock(cls):
            cls._blocked = False

        @classmethod
        @property
        def isactive(cls):
            return cls._clsinstance is not None

        @classmethod
        def get_active_singleton(cls):
            return cls._clsinstance

        def __enter__(self):
            self.instance.__enter__()
            return None

        def __exit__(self, e_type, e, e_traceback):
            cls = type(self)
            if e_type is not None:
                _logger.exception(str(e))

            if self == cls._clsinstance and not cls._blocked:
                # We were the first launch of CompositeAction, we can now clear
                # the class instance and let a new one start next time.
                cls._clsinstance = None

            # Use the private instance so we don't create a new one
            # accidentally (will throw an Error if _instance is None because we
            # have exited twice without entering
            self._instance.__exit__(e_type, e, e_traceback)

            # Make sure that we don't reuse this instance later, if we run
            # __enter__ again, it will generate a new self._instance following
            # the logic in instance(self)
            self._instance = None

            return None

    class SuspendCompositeAction:
        _clsinstance = None
        _CompositeActionClass = CompositeAction
        active_action_args = None
        message = "Suspending composite action"

        def __init__(self, reason=None):
            if not type(self)._clsinstance:
                # First time being used.
                type(self)._clsinstance = self

            if reason:
                self.message = f"{self.message}: ({reason})"

        def __enter__(self):
            cls = type(self)
            ca_class = cls._CompositeActionClass
            ca_class.block()
            if ca_class.isactive:
                # Currently in a CompositeAction, suspend it.
                _logger.info(f"{self.message}")
                self.active_ca_wrapper = ca_class.get_active_singleton()
                # Exit the composite action without an error.
                self.active_ca_wrapper.__exit__(None, None, None)

            return None

        def __exit__(self, e_type, e, e_traceback):
            cls = type(self)
            if e_type is not None:
                _logger.exception(f"Reached exit of {self.__class__.__name__}"
                                  " with an error, bubble up.")
                raise e

            if self == cls._clsinstance:
                # We were the first launch of SuspendCompositeAction, we can
                # now clear the class instance and let a new one start.
                cls._clsinstance = None

                # Unblock CompositeAction from being created.
                ca_class = cls._CompositeActionClass
                ca_class.unblock()

                if self.active_ca_wrapper:
                    # There was a running CompositeAction when we halted, start
                    # it again with the same arguments
                    self.active_ca_wrapper.instance.__enter__()
                    self.active_ca_wrapper = None

            return None

    @helperoverride
    def await_user_input(msg):
        # Wrapper to prevent await_user_input from spawning during a composite
        # action context manager.

        if CompositeAction._clsinstance is not None:
            # Log a warning (include traceback info to help trace cause)
            _logger.warning("Tried to call await_user_input during a composite"
                            " action.  This leads to a crash. Ignoring call.\n"
                            "Message was: '{}'".format(msg), exc_info=True)
            _await_user_input_mb(msg)
        else:
            _await_user_input(msg)

try:
    from pydicom import dcmread, uid
except ImportError:
    # If we don't have pydicom in this env, can't do any of this. Just return a
    # dummy function that returns a usuable but empty dataset like object.
    class _DUMMY_DCM:
        Modality = 'CT'

        def __getattr__(self, attr):
            # Suppress AttributeErrors in favor of empty returns.  Only usefuly
            # because this is a dummy class for debugging or when running
            # without dcmread.
            return None

    @helperoverride
    def dcmread(*args, **kwargs):
        DUMMY_DCM = _DUMMY_DCM()
        return DUMMY_DCM

    @helperoverride
    class uid:

        @staticmethod
        def generate_uid(prefix=None, entropy_sources=[]):
            # Very short and not entirely compliant UID generator

            uid = uuid4().int
            if prefix:
                prefix = f'{prefix}'[0:32]
                prefix[31] = '0'
                return f'{prefix}.{uid}'[0:62]

            return f'2.25.{uid}'[0:62]


def rs_hasattr(obj, attrname):
    try:
        if '.' in attrname:
            # Composite attribute, nest.
            firstattr, rest = attrname.split('.', 1)
            return rs_hasattr(rs_getattr(obj, firstattr), rest)
        return hasattr(obj, attrname)
    except (KeyError, ValueError, IndexError, TypeError):
        return False


def rs_getattr(obj, attrname):
    if attrname in ['', '.', 'self']:
        # If we are passed an empty attrname, a bare dot, or self, return obj
        return obj

    if rs_hasattr(obj, attrname) and '.' in attrname:
        # Composite attribute, nest.
        firstattr, rest = attrname.split('.', 1)
        return rs_getattr(getattr(obj, firstattr), rest)
    return getattr(obj, attrname)


def rs_callable(obj, attrname):
    try:
        return callable(getattr(obj, attrname))
    except (AttributeError, ValueError, KeyError, IndexError):
        return False


def get_module_opt(opt_name, default=None):
    mod_opts = sys.modules[__name__].__opts

    return mod_opts[opt_name] if opt_name in mod_opts else default


def set_module_opt(opt_name, value):
    mod_opts = sys.modules[__name__].__opts
    mod_opts[opt_name] = value


def set_module_opts(**kwargs):
    for opt, val in kwargs.items():
        set_module_opt(opt, val)


class ListItemPanel(DockPanel):
    _button = None
    _label = None

    def __init__(self, obj_name_in, button_click, index,
                 is_current=False, is_default=False, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self._button = Button()
        _logger.debug(f"{obj_name_in=}")
        if is_current:
            self._button.Tag = 'current'
        if is_default:
            self._button.IsDefault = True

        # Use a TextBlock to get around _ being an accelerator in buttons.
        obj_text = TextBlock()
        obj_text.Text = f"{obj_name_in}"
        self._button.Content = obj_text

        self._button.Click += button_click

        self._label = Label()
        self._label.Content = f"_{index}"
        self._label.Target = self._button

        self.Children.Add(self._label)
        self.Children.Add(self._button)


class ListSelectorDialog(RayWindow):
    _XAML = """
<Window xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
        xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml"
        xmlns:d="http://schemas.microsoft.com/expression/blend/2008"
        xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006"
        xmlns:System="clr-namespace:System;assembly=mscorlib"
        Title="Select List"
        SizeToContent="WidthAndHeight"
        Foreground="#FF832F2F"
        Topmost="True"
        WindowStartupLocation="CenterOwner"
        ResizeMode="NoResize"
        WindowStyle="ThreeDBorderWindow" MinWidth="192"
        FontSize="24">

    <Window.Resources>
        <Style TargetType="{x:Type StackPanel}">
            <Setter Property="Margin" Value="0"/>
        </Style>
        <Style TargetType="{x:Type Label}">
            <Setter Property="VerticalAlignment" Value="Center"/>
        </Style>
        <Style TargetType="{x:Type Button}">
            <Setter Property="Margin" Value="5"/>
            <Setter Property="Padding" Value="5"/>
            <Style.Triggers>
                <Trigger Property="Tag" Value="current">
                    <Setter Property="BorderThickness" Value="3" />
                    <Setter Property="BorderBrush">
                        <Setter.Value>
                            <RadialGradientBrush RadiusX="1" RadiusY="1">
                                <GradientStop Color="#FF04B6D3" Offset="0.34"/>
                                <GradientStop Color="White" Offset="1"/>
                            </RadialGradientBrush>
                        </Setter.Value>
                    </Setter>
                </Trigger>
            </Style.Triggers>
        </Style>
    </Window.Resources>
    <Window.TaskbarItemInfo>
        <TaskbarItemInfo ProgressState="Normal" ProgressValue="50"/>
    </Window.TaskbarItemInfo>

    <StackPanel Background="#FFE6E6E6" MinHeight="20" Margin="0">
        <Label x:Name="PickerLabel" Content="Select one:"/>
        <StackPanel x:Name="ListPanel">
        </StackPanel>
    </StackPanel>
</Window>
    """
    ListPanel = None  # StackPanel
    _results = None  # dict for results
    _list_in = None  # list of list_in

    def __init__(self, list_in, results):
        self.LoadComponent(self._XAML)

        if 'description' in results:
            self.PickerLabel.Content = results['description']

        self.ListPanel.Children.Clear()

        self._list_in = {obj_name(obj): obj for obj in list_in}

        self._results = results

        _logger.debug(f"{results=}")
        for i, obj_name_in in enumerate(self._list_in):
            is_current = self.obj_matches('current', obj_name_in)
            is_default = self.obj_matches('default', obj_name_in)
            obj_listitem = ListItemPanel(obj_name_in, self.List_Click,
                                         i+1, is_current, is_default)

            self.ListPanel.Children.Add(obj_listitem)
            continue

            obj_button = Button()
            _logger.debug(f"{obj_name_in=}")
            if self.obj_matches('current', obj_name_in):
                obj_button.Tag = 'current'
            if self.obj_matches('default', obj_name_in):
                obj_button.IsDefault = True

            # Use a TextBlock to get around _ being an accelerator in buttons.
            obj_text = TextBlock()
            obj_text.Text = f"{obj_name_in}"
            obj_button.Content = obj_text

            obj_button.Click += self.List_Click
            self.ListPanel.Children.Add(obj_button)

    def obj_matches(self, feature, obj_name_in):
        if feature not in self._results:
            return False

        if self._results[feature] in [obj_name_in, self._list_in[obj_name_in]]:
            _logger.debug(f"Found {feature} {obj_name_in=}")
            return True
        elif isinstance(self._results[feature], str):
            # This was a simple check, not present, so false.
            return False

        try:
            for matcher in self._results[feature]:
                if matcher in [obj_name_in, self._list_in[obj_name_in]]:
                    return True
        except (IndexError, ValueError, TypeError):
            return False

        return False

    def List_Click(self, caller, event):
        try:
            text_child = caller.Content.Text
            self._results['Selected'] = self._list_in[text_child]
            self.DialogResult = True
        finally:
            self.Close()


def obj_name(obj, name_identifier_object='.', strict=False):
    if isinstance(obj, str):
        return obj

    try:
        obj = rs_getattr(obj, name_identifier_object)
    except AttributeError:
        _logger.warning(f"{obj} has no attribute {name_identifier_object}")

    try:
        return rs_getattr(obj, [attr for attr in _NAMELIST if
                                rs_hasattr(obj, attr)][0])
    except IndexError:
        if strict:
            raise ValueError("No matching identifier")

        return str(obj)


def has_obj_name(obj, name_identifier_object='.'):
    try:
        obj = rs_getattr(obj, name_identifier_object)
    except AttributeError:
        _logger.warning(f"{obj} has no attribute {name_identifier_object}")

    return any(lambda attr: rs_hasattr(obj, attr), _NAMELIST)


def guess_name_id(obj_collection, first_guess=None):
    guess_list = []

    if first_guess:
        guess_list.append(first_guess)

    first_obj = next(iter(obj_collection))
    guess_list += [attr for attr in dir(first_obj) if attr[0:3] == 'For']

    for guess in guess_list:
        try:
            names = [obj_name(obj, guess, strict=True)
                     for obj in obj_collection]
            # Test for uniqueness
            if len(names) == len(set(names)):
                return guess
        except ValueError:
            continue

    raise ValueError("Unable to guess unique name id.")


def pick_list(obj_list, description="Select One", current=None, default=None):
    results = {'current': current,
               'default': default,
               'description': description}

    # Don't bother with a dialog if there is only one choice.
    if len(obj_list) == 1:
        return next(iter(obj_list))

    dlg = ListSelectorDialog(obj_list, results)
    try:
        res = dlg.ShowDialog()

        if not res:
            raise Warning("Closed with cancel")

    except Warning:
        _logger.warning("Dialog failed to run correctly.", exc_info=True)

    if 'Selected' in results:
        return results['Selected']
    else:
        return None


def pick_exam(exams=None, include_current=True, default=None,
              message="Select Exam:"):
    try:
        current = obj_name(get_current("Examination"))
    except InvalidDataException:
        _logger.debug("No current examination selected.")
        current = None

    exams = exams if exams else [exam for exam in
                                 get_current("Case").Examinations
                                 if include_current
                                 or obj_name(exam) != obj_name(current)]
    return pick_list(exams, message, current=current, default=default)


def pick_plan(plans=None, include_current=True, default=None,
              message="Select Plan:"):
    try:
        current = obj_name(get_current("Plan"))
    except InvalidDataException:
        _logger.debug("No current plan selected.")
        current = None

    plans = plans if plans else [plan for plan in
                                 get_current("Case").TreatmentPlans
                                 if include_current
                                 or obj_name(plan) != obj_name(current)]
    return pick_list(plans, message, current=current, default=default)


def pick_machine(current=None, default=None, match_on=None,
                 exclude_current=False, message="Select machine:"):
    def_filter_dict = {'IsLinac': True,
                       'HasMlc': True,
                       'Name': None,
                       'IsDynamicArcCapable': True,
                       'IsDynamicMlcCapable': True,
                       'IsStaticArcCapable': True,
                       'CommissionedBy': None,
                       'IsIonMachine': False,
                       'IsCyberKnifeLinac': False,
                       'HasRangeShifters': False,
                       'IsElectronCapable': None
                       }

    _logger.debug(f"{locals()}")
    if current is not None:
        current = {current} if isinstance(current, str) else set(current)
    else:
        current = {}

    if not match_on:
        match_on = [k for k in def_filter_dict
                    if def_filter_dict[k] is not None]

    machine_db = get_current("MachineDB")
    mach_query = machine_db.QueryCommissionedMachineInfo

    currentmachinfo = []
    for mach in current:
        currentmachinfo += mach_query(Filter={'Name': mach})

    currentmachinfo = (currentmachinfo + [def_filter_dict])[0]

    filter_dict = {k: currentmachinfo[k] for k in match_on}

    machines_info_list = mach_query(Filter=filter_dict)

    machines = [MachineQueryResult(**m) for m in machines_info_list]

    if exclude_current:
        for machine in machines:
            if machine.Name in current:
                machines.remove(machine)

    return pick_list(machines, message,
                     current=current, default=default)


@dataclass
class MachineQueryResult:
    Name: str
    NameAliases: str
    IsDeprecated: bool
    IsCommissioned: bool
    CommissionTime: object
    IsTemplate: bool
    IsDynamicArcCapable: bool
    IsDynamicMlcCapable: bool
    IsStaticArcCapable: bool
    CommissionedBy: str
    HasMlc: bool
    IsLinac: bool
    IsIonMachine: bool
    IsCyberKnifeLinac: bool
    HasRangeShifters: bool
    IsElectronCapable: bool
    SupportsOcularGaze: bool
    PatientSupportType: str
    IsRbeIncluded: bool = False

    @property
    def Alias(self):
        return self.NameAliases


class Machine:
    _machine = None
    _energies = None

    def __init__(self, machine):
        self._machine = machine
        if self._machine.PhotonBeamQualities is None:
            raise NotImplementedError("Only support for photons machines.")

    @property
    def photon_energies(self):
        if not self._energies:
            # Sort by increasing nominal energy, this will let us pull the
            # nearest value not above the current energy
            energies = sorted(self._machine.PhotonBeamQualities,
                              key=lambda e: e.NominalEnergy)
            self._energies = {(f'{int(e.NominalEnergy)}'
                               if e.FluenceMode is None else
                               f'{int(e.NominalEnergy)} {e.FluenceMode}'): e
                              for e in energies}
        return self._energies

    def closest_energy(self, energy):
        energies = self.photon_energies
        if energy in energies:
            return energy

        nominal_energy = int(energy.rstrip(" FFF"))
        isfff = 'FFF' in energy

        if isfff:
            if f'{nominal_energy}' in energies:
                return f'{nominal_energy}'
        else:
            fff_energy = f'{energy} FFF'
            if fff_energy in energies:
                return fff_energy

        try:
            return [e for e in energies if isfff == ('FFF' in e)][0]
        except IndexError:
            return next(iter(energies))


def get_machine(machine_name):
    mach_db = get_current("MachineDB")
    return Machine(mach_db.GetTreatmentMachine(machineName=machine_name))


def pick_site(sites=None, current=None, default=None):
    if sites is None:
        site_settings = get_current("ClinicDB").GetSiteSettings()
        site_defs = site_settings.DefaultSettings.BodySiteDefinitions
        sites = [obj_name(site) for site in site_defs]

    return pick_list(sites, "Select site:", current=current, default=default)


def dup_object_param_values(obj_in, obj_out,
                            includes=None, excludes=[], sub_objs=[], _depth=0):
    if obj_in is None:
        raise TypeError("Got passed a nonetype object to copy from.")

    if _depth > __opts['DUP_MAX_RECURSE']:
        raise RecursionError(f"{__name__} too deep ({_depth} layers),"
                             " this may be a self referential object.")

    sub_obj_depth = max([s.count('.') for s in sub_objs] + [0])
    if sub_obj_depth > __opts['DUP_MAX_RECURSE']:
        raise ValueError(f"Subobjects too deep ({sub_obj_depth} > "
                         f"{__opts['DUP_MAX_RECURSE']}): {sub_objs=}")

    # TODO: Consider exclududing any objects which are PyScriptObjects unless
    # explicitly included.

    # Get the list of sub_objects we might be acting on.
    sub_o_set = {sub_o for sub_o in sub_objs
                 if (rs_hasattr(obj_out, sub_o)
                     and rs_getattr(obj_out, sub_o) is not None)}

    # Objects to act on directly, copying everything in them.
    sub_o_root_set = {sub_o for sub_o in sub_o_set if '.' not in sub_o}

    # Objects who have a deep component to be acted on later in the recursed
    # dup_obj_param_values call.
    sub_o_deep_set = {sub_o for sub_o in sub_o_set if '.' in sub_o}
    sub_o_deep_root_set = {sub_o.split('.', 1)[0] for sub_o in sub_o_deep_set}

    # All roots, including shallow, shallow+deep, and deep only
    sub_o_all_root_set = sub_o_root_set | sub_o_deep_root_set

    # Mapping of sub_objs to pass to later dup_obj_param_values calls.
    sub_o_deep_set_map = {o_root: {sub_sub_o.split('.', 1)[1] for sub_sub_o
                                   in sub_o_deep_set
                                   if sub_sub_o.split('.', 1)[0] == o_root}
                          for o_root in sub_o_all_root_set}

    # Objects with deep sets but no root set to copy (Handle differently from
    # the normal objects
    sub_o_deep_only_root_set = sub_o_deep_root_set - sub_o_root_set

    # If passed a sub object with its own sub objects, assume that we cannot
    # use it in the list of params to be copied alone.
    top_excludes = sub_o_root_set | sub_o_deep_root_set | set(excludes)

    if includes is None:
        top_includes = set(dir(obj_out))
    else:
        top_includes = {inc for inc in includes if '.' not in inc}

    # Any objects in top that are callble should be excluded
    top_callables = {p for p in top_includes if rs_callable(obj_out, p)}

    # Any objects in top that are Script Collections or ScriptObjects should be
    # excluded.
    top_scriptitems = {p for p in top_includes
                       if 'Script' in (type(rs_getattr(obj_out, p))).__name__}

    valid_top_params = (top_includes - top_callables) - top_scriptitems

    params = valid_top_params - top_excludes
    for param in params:
        value = rs_getattr(obj_in, param)
        try:
            setattr(obj_out, param, value)
            _logger.debug(f'{"":->{_depth}s}{"":>>{_depth>0:d}s}'
                          f'Set {param}={value} on {obj_out}')
        except InvalidOperationException:
            _logger.debug(f'{"":->{_depth}s}{"":>>{_depth>0:d}s}'
                          f'Failed to set {param}={value} on {obj_out}')

    # Loop through objects to be copied
    for sub_obj in sub_o_root_set:
        sub_in = rs_getattr(obj_in, sub_obj)
        sub_out = rs_getattr(obj_out, sub_obj)

        # Explicitly requested objects to copy.
        sub_sub_objs = sub_o_deep_set_map[sub_obj]  # This may be an empty set

        # Exclude anything already excluded in the dot notation
        sub_excludes = {exc.split('.', 1)[1] for exc in excludes
                        if '.' in exc and sub_obj == exc.split('.', 1)[0]}

        sub_includes = None
        if includes:
            sub_includes = {inc.split('.', 1)[1] for inc in includes
                            if '.' in inc and inc.split('.', 1)[0] == sub_obj}

        if not sub_includes and sub_obj not in sub_o_deep_only_root_set:
            sub_includes = None

        # Add excludes for all objects in root that are not in the sub_sub_objs
        # list if this is a member of the sub_o_deep_only_root_set.
        dup_object_param_values(sub_in,
                                sub_out,
                                includes=sub_includes,
                                excludes=sub_excludes,
                                sub_objs=sub_sub_objs,
                                _depth=_depth+1)
    return None


class CallLaterList():
    _fn_list = {}  # Class level list

    def _def_fn(self, *args, **kwargs):
        raise NotImplementedError("Must be initialised first.")

    def __getattr__(self, fn):
        if fn not in self._fn_list:
            self._fn_list[fn] = CallLater()
        return self._fn_list[fn]

    def __call__(self, fn):
        fnname = fn.__name__
        myfn = self.__getattr__(fnname)
        myfn.set_fn(fn)
        return myfn


class CallLater():
    _myfn = None

    def __call__(self, *args, **kwargs):
        return self._myfn(*args, **kwargs)

    def set_fn(self, fn):
        self._myfn = fn


def get_unique_name(obj, container, char_limit=64):
    if isinstance(container, set):
        limiting_set = container
    elif rs_hasattr(container, 'Keys'):
        limiting_set = set(container.Keys)
    else:
        try:
            limiting_set = set(map(obj_name, container))
        except (ValueError, AttributeError):
            limiting_set = set(container)

    o_name = obj_name(obj)
    oo_name = o_name
    n = 1
    while o_name in limiting_set:
        o_name = f'{oo_name[0:(char_limit - 5 - n//10)]} ({n})'
        n += 1

    return o_name


class ObjectDict(dict):
    _name_id = None

    def __init__(self, obj_collection=None, name_identifier='.'):
        super().__init__()

        self._name_id = guess_name_id(obj_collection, name_identifier)

        if obj_collection is not None:
            self.update(obj_collection)

    def update(self, collection):
        if type(collection).__name__ == 'PyScriptObjectCollection':
            return super().update({obj_name(obj, self._name_id): obj
                                   for obj in collection})
        else:
            return super().update(collection)

    def __and__(self, other):
        return self.keys() & other.keys()


def params_from_mapping(obj, param_map, default_map=None):
    if default_map:
        params = deepcopy(default_map)
    else:
        params = {}

    map_p = {key: (param_map[key](obj) if callable(param_map[key])
                   else (rs_getattr(obj, key) if rs_hasattr(obj, key) else
                         rs_getattr(obj, param_map[key])))
             for key in param_map
             if key and (callable(param_map[key])
                         or rs_hasattr(obj, param_map[key])
                         or rs_hasattr(obj, key))}

    params.update(map_p)
    return params


# __all__ = [dcmread, CompositeAction, get_current]
