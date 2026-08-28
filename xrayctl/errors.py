"""xrayctl exceptions."""

OK = 0
USAGE_ERROR = 2
NOT_FOUND = 3
NETWORK_ERROR = 4
PARSE_ERROR = 5
CORE_ERROR = 6
UNSUPPORTED = 7


class XrayctlError(Exception):
    exit_code = 1


class UsageError(XrayctlError):
    exit_code = USAGE_ERROR


class NotFoundError(XrayctlError):
    exit_code = NOT_FOUND


class NetworkError(XrayctlError):
    exit_code = NETWORK_ERROR


class ParseError(XrayctlError):
    exit_code = PARSE_ERROR


class CoreError(XrayctlError):
    exit_code = CORE_ERROR


class UnsupportedError(XrayctlError):
    exit_code = UNSUPPORTED
