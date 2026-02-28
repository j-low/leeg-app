from slowapi import Limiter
from slowapi.util import get_remote_address

# Global limiter instance - import this in routes that need rate-limit decorators.
# Default: 200 requests/minute per IP (overridden per-endpoint for sensitive routes).
limiter = Limiter(key_func=get_remote_address, default_limits=["200/minute"])
