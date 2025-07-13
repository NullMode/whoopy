__version__ = "0.3.0"

import logging

# Import v1 for backward compatibility
try:
    from . import models
    from . import handlers
    from .models.models_v1 import SPORT_IDS as SPORT_IDS_V1
    from .client_v1 import WhoopClient as WhoopClientV1
    from .client_v1 import API_VERSION as API_VERSION_V1
except Exception as ex:
    logging.error(f"Error importing whoopy v1: {ex}")

# Import v2 as the new default
try:
    from .client_v2 import WhoopClientV2
    from .sync_wrapper import WhoopClientV2Sync
    from .models.models_v2 import SPORT_IDS
    
    # Make v2 sync wrapper the default
    WhoopClient = WhoopClientV2Sync
    API_VERSION = "2"
    
except Exception as ex:
    logging.error(f"Error importing whoopy v2: {ex}")
    # Fall back to v1 if v2 fails
    WhoopClient = WhoopClientV1
    API_VERSION = API_VERSION_V1
    SPORT_IDS = SPORT_IDS_V1

# Export all available clients
__all__ = [
    "WhoopClient",      # Default (v2 sync)
    "WhoopClientV2",    # Async v2
    "WhoopClientV2Sync", # Explicit sync v2
    "WhoopClientV1",    # Legacy v1
    "SPORT_IDS",        # Sport ID mapping (v2 by default)
    "API_VERSION",      # API version (v2 by default)
    "__version__",
]

try:
    # import other versions
    from . import client_vu7
    from . import client_v1
except Exception as ex:
    logging.error(f"Not all dependencies installed: {ex}")
