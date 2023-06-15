try:
    from connect import get_current, CompositeAction  # , set_progress

except ImportError:
    # Replacement functions when not running in RS
    class CompositeAction():
        def __enter__(self, *args, **kwargs):
            pass

        def __exit__(self, *args, **kwargs):
            pass

    def get_current(name):
        # TODO: Might want to return a sample object that has reasonable
        # facimiles of the real objects for debugging.
        return None

try:
    from pydicom import dcmread
except ImportError:
    # If we don't have pydicom in this env, can't do any of this. Just return a
    # dummy function that returns none.
    def dcmread(*args, **kwargs):
        return None

__all__ = [dcmread, CompositeAction, get_current]
