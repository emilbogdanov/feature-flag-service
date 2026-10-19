import math


def is_number(value: object) -> bool:
    if isinstance(value, bool):
        return False
    # An int is always finite, and math.isfinite raises on ints too large to become a float.
    return isinstance(value, int) or (isinstance(value, float) and math.isfinite(value))
