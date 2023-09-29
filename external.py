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
    from pydicom import dcmread
except ImportError:
    # If we don't have pydicom in this env, can't do any of this. Just return a
    # dummy function that returns none.
    @helperoverride
    def dcmread(*args, **kwargs):
        return None


def rs_hasattr(obj, attrname):
    try:
        return hasattr(obj, attrname)
    except (KeyError, ValueError, IndexError, TypeError):
        return False


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

# __all__ = [dcmread, CompositeAction, get_current]
