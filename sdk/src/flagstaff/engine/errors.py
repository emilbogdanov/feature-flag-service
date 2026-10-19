# Raised while a flag is being built, never while it is evaluated: a ruleset the engine can't
# make sense of is rejected as a whole instead of being half-evaluated in production.
class InvalidFlagError(ValueError):
    pass


class InvalidContextError(ValueError):
    pass
