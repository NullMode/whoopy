__version__ = "0.3.0"

import logging
from typing import Any

# Import v1 for backward compatibility
try:
    from . import handlers as _handlers_v1  # noqa: F401
    from . import models as _models_v1  # noqa: F401
    from .client_v1 import API_VERSION as API_VERSION_V1
    from .client_v1 import WhoopClient as WhoopClientV1
    from .models.models_v1 import SPORT_IDS as SPORT_IDS_V1

    v1_available = True
except Exception as ex:
    logging.error(f"Error importing whoopy v1: {ex}")
    v1_available = False
    WhoopClientV1 = None  # type: ignore[misc,assignment]
    API_VERSION_V1 = "1"
    SPORT_IDS_V1 = {}

# Import v2 as the new default
WhoopClient: Any
WhoopClientV2: Any | None = None
WhoopClientV2Sync: Any | None = None
API_VERSION: str
SPORT_IDS: dict[int, str]

try:
    from .client_v2 import WhoopClientV2
    from .models.models_v2 import SPORT_IDS
    from .sync_wrapper import WhoopClientV2Sync

    # Make v2 sync wrapper the default
    WhoopClient = WhoopClientV2Sync
    API_VERSION = "2"
    v2_available = True

except Exception as ex:
    logging.error(f"Error importing whoopy v2: {ex}")
    v2_available = False
    # Fall back to v1 if v2 fails and v1 is available
    if v1_available:
        WhoopClient = WhoopClientV1
        API_VERSION = API_VERSION_V1
        SPORT_IDS = SPORT_IDS_V1
    else:
        # Neither v1 nor v2 available
        raise ImportError("Unable to import any version of WhoopClient") from ex

# Export all available clients
__all__ = [
    "API_VERSION",  # API version (v2 by default)
    "SPORT_IDS",  # Sport ID mapping (v2 by default)
    "WhoopClient",  # Default (v2 sync)
    "WhoopClientV1",  # Legacy v1
    "WhoopClientV2",  # Async v2
    "WhoopClientV2Sync",  # Explicit sync v2
    "__version__",
]

try:
    # import other versions
    from . import client_v1 as _client_v1  # noqa: F401
    from . import client_vu7 as _client_vu7  # noqa: F401
except Exception as ex:
    logging.error(f"Not all dependencies installed: {ex}")
