"""Typed errors for SureBet monitor."""


class SurebetMonitorError(Exception):
    """Base error."""


class AuthFailed(SurebetMonitorError):
    pass


class CaptchaDetected(SurebetMonitorError):
    pass


class AntiBotDetected(SurebetMonitorError):
    pass


class SiteUnavailable(SurebetMonitorError):
    pass


class TimeoutError_(SurebetMonitorError):
    """Named to avoid shadowing builtin TimeoutError in imports."""


class FilterNotFound(SurebetMonitorError):
    pass


class ResultsTimeout(SurebetMonitorError):
    pass


class ParserOrLayoutChanged(SurebetMonitorError):
    pass


class ParserHealthWarning(SurebetMonitorError):
    pass
