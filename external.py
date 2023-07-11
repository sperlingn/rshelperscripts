import logging as _logging

_logger = _logging.getLogger(__name__)


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

    def _await_user_input(msg):
        _logger.logging("Waited for user input: '{}'".format(msg))

finally:

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

            # Make sure that we don't reuse this object later (for now we can
            # only enter and exit once...with more logic this could be fixed.
            self._instance = None

            return rv

    def await_user_input(msg):
        # Wrapper to prevent await_user_input from spawning during a composite
        # action context manager.

        if CompositeAction._clsinstance is not None:
            # Log a warning (include traceback info to help trace cause)
            _logger.warning("Tried to call await_user_input during a composite"
                            " action.  This leads to a crash. Ignoring call.\m"
                            "Message was: '{}'".format(msg), exc_info=True)

        else:
            return _await_user_input(msg)

try:
    from pydicom import dcmread
except ImportError:
    # If we don't have pydicom in this env, can't do any of this. Just return a
    # dummy function that returns none.
    def dcmread(*args, **kwargs):
        return None

# __all__ = [dcmread, CompositeAction, get_current]
