# =========================================================================
# CUSTOM EXCEPTIONS
# =========================================================================

class FUBError(Exception):
    """Base exception for FUB-related errors"""
    pass

class FUBAPIError(FUBError):
    """API request failed"""
    pass

class RateLimitExceeded(FUBError):
    """Rate limit exceeded"""
    pass

class DataValidationError(Exception):
    """Data validation failed"""
    pass
