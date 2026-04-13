class TVLError(Exception):
    """Base exception for TVL SDK."""


class SchemaError(TVLError):
    pass


class ParseError(TVLError):
    pass


class UnsatError(TVLError):
    pass

