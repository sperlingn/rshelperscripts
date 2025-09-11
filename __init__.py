from logging import getLogger as _getLogger, basicConfig as _basicConfig

log_fmt = ('%(asctime)s: %(name)s.%(funcName)s:%(lineno)d'
           ' - %(levelname)s: %(message)s')
_basicConfig(format=log_fmt)

from .case_comment_data import *  # noqa: W401, W611
from .couchtop import *           # noqa: W401, W611
from .points import *             # noqa: W401, W611
from .rsdicomread import *        # noqa: W401, W611
from .dosetools import *          # noqa: W401, W611
from .external import *           # noqa: W611
from .roi import *                # noqa: W401, W611
from .clinicalgoals import *      # noqa: W401, W611
from .validations import *        # noqa: W401, W611
from .plans import *              # noqa: W401, W611
from .optimization import (RunOptimizations, BulkOptimizer)    # noqa: W611
from .dose_eval_dialog import show_indices_dialog # noqa: W611

if RS_VERSION.major >= 14:        # noqa: W401
    # Prebuild machines for RS version 14 and up to avoid crashing when using
    # composite action
    populate_machines()           # noqa: W401

del logging                       # noqa: E602

_logger = _getLogger(__name__)

# Replicates builtin functionality, but put in place as it might be good to
# limit later what gets included in the __all__.
__all__ = [k for k in globals().keys() if k[0] != '_']
