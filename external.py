from enum import IntEnum
import logging as _logging
_logger = _logging.getLogger(__name__)


def helperoverride(function):
    function.__overridden__ = True
    return function


try:
    from System.Windows import MessageBox as _MessageBox
except ImportError:

    # TODO: Work to include a QT or other based dialog? Right now we can assume
    # that the Windows MessageBox will work for RS.  This is only for debugging
    # functions.
    @helperoverride
    class _MessageBox:
        def Show(*args, **kwargs):
            _logger.info("MessageBox: args={}, kwargs={}", args, kwargs)
            return True


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


class MB_Options(IntEnum):
    DefaultDesktopOnly = 131072
    None_ = 0
    RightAlign = 524288
    RtlReading = 1048576
    ServiceNotification = 2097152


def Show_OK(message, caption, ontop=False, icon=MB_Icon.None_,
            defaultResult=MB_Result.None_):
    button = MB_Button.OK
    opt = MB_Options.DefaultDesktopOnly if ontop else MB_Options.None_
    return _MessageBox.Show(message, caption, button, icon, defaultResult, opt)


def Show_OKCancel(message, caption, ontop=False, icon=MB_Icon.None_,
                  defaultResult=MB_Result.None_):
    button = MB_Button.OKCancel
    opt = MB_Options.DefaultDesktopOnly if ontop else MB_Options.None_
    return _MessageBox.Show(message, caption, button, icon, defaultResult, opt)


def Show_YesNo(message, caption, ontop=False, icon=MB_Icon.None_,
               defaultResult=MB_Result.None_):
    button = MB_Button.YesNo
    opt = MB_Options.DefaultDesktopOnly if ontop else MB_Options.None_
    return _MessageBox.Show(message, caption, button, icon, defaultResult, opt)


def Show_YesNoCancel(message, caption, ontop=False, icon=MB_Icon.None_,
                     defaultResult=MB_Result.None_):
    button = MB_Button.YesNoCancel
    opt = MB_Options.DefaultDesktopOnly if ontop else MB_Options.None_
    return _MessageBox.Show(message, caption, button, icon, defaultResult, opt)


def _await_user_input_mb(message):
    _logger.debug("Waited for user input: '{}'".format(message))
    return _MessageBox.Show("{}".format(message), "Awaiting Input",
                            # Always on top = 131072
                            1, 0, 0, 131072)


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
                         await_user_input as _await_user_input)

except ImportError:
    # Replacement functions when not running in RS

    def get_current(name):
        # TODO: Might want to return a sample object that has reasonable
        # facimiles of the real objects for debugging.
        return None

    class _CompositeActionOrig(_CompositeActionDummy):
        pass

    _await_user_input = _await_user_input_mb

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
    from pydicom import dcmread
except ImportError:
    # If we don't have pydicom in this env, can't do any of this. Just return a
    # dummy function that returns none.
    @helperoverride
    def dcmread(*args, **kwargs):
        return None

# __all__ = [dcmread, CompositeAction, get_current]
