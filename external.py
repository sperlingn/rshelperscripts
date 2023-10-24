from enum import IntEnum
import sys
import logging as _logging
_logger = _logging.getLogger(__name__)


__opts = {}


def helperoverride(function):
    function.__overridden__ = True
    return function


try:
    from System.Windows import MessageBox as _MessageBox
    from System.Windows.Controls import Button
    from System import ArgumentOutOfRangeException
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

        def __init__(self, *args, **kwargs):
            if type(self)._clsinstance:
                self._instance = _CompositeActionDummy(*args, **kwargs)
            else:
                self._instance = _CompositeActionOrig(*args, **kwargs)
                type(self)._clsinstance = self._instance

        def __enter__(self):
            return self._instance.__enter__()

        def __exit__(self, e_type, e, e_traceback):
            if e_type is not None:
                _logger.exception(str(e))

            if self._instance == type(self)._clsinstance:
                # We were the first launch of CompositeAction, we can now clear
                # the class instance and let a new one start next time.
                type(self)._clsinstance = None

            rv = type(self._instance).__exit__(self._instance,
                                               e_type, e, e_traceback)

            # FIXME:
            # Make sure that we don't reuse this object later (for now we can
            # only enter and exit once...with more logic this could be fixed.
            self._instance = None

            return rv

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
    # dummy function that returns none.
    @helperoverride
    def dcmread(*args, **kwargs):
        return None

    @helperoverride
    class uid:
        def generate_uid(self, prefix=None, entropy_sources=[]):
            raise NotImplementedError(self.__name__)


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


class PlanSelectorDialog(RayWindow):
    _XAML = """
<Window xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
        xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml"
        xmlns:d="http://schemas.microsoft.com/expression/blend/2008"
        xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006"
        xmlns:System="clr-namespace:System;assembly=mscorlib"
        Title="Select Plan"
        SizeToContent="WidthAndHeight"
        Foreground="#FF832F2F"
        Topmost="True"
        WindowStartupLocation="CenterOwner"
        ResizeMode="NoResize"
        WindowStyle="ThreeDBorderWindow" MinWidth="192"
        FontSize="24">

    <Window.Resources>
        <Style TargetType="{x:Type StackPanel}">
            <Setter Property="Margin" Value="5"/>
        </Style>
        <Style TargetType="{x:Type Button}">
            <Setter Property="Margin" Value="5"/>
            <Setter Property="Padding" Value="5"/>
        </Style>
    </Window.Resources>
    <Window.TaskbarItemInfo>
        <TaskbarItemInfo ProgressState="Normal" ProgressValue="50"/>
    </Window.TaskbarItemInfo>

    <StackPanel Background="#FFE6E6E6" MinHeight="20" Margin="0">
        <Label Content="Select a plan:"/>
        <StackPanel x:Name="PlanPanel">
            <Button x:Name="ButtonList" Content="PlanName" />
        </StackPanel>
    </StackPanel>
</Window>
    """
    PlanPanel = None  # StackPanel
    _results = None  # dict for results
    _plans = None  # list of plans

    def __init__(self, plans, results):
        self.LoadComponent(self._XAML)

        self.PlanPanel.Children.Clear()

        self._plans = {plan.Name: plan for plan in plans}

        for plan in plans:
            plan_button = Button()
            plan_button.Content = f"{plan.Name}"
            plan_button.Click += self.Plan_Click
            self.PlanPanel.Children.Add(plan_button)

        self._results = results

    def Plan_Click(self, caller, event):
        self._results['Plan'] = self._plans[caller.Content]
        self.DialogResult = True
        self.Close()


def pick_plan(plans):
    results = {}
    dlg = PlanSelectorDialog(plans, results)
    try:
        res = dlg.ShowDialog()

        if not res:
            raise Warning("Closed with cancel")

    except Warning:
        _logger.warning("Dialog failed to run correctly.", exc_info=True)

    if 'Plan' in results:
        return results['Plan']
    else:
        return None

# __all__ = [dcmread, CompositeAction, get_current]
