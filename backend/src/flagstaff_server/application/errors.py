class ApplicationError(Exception):
    pass


# The flag changed since the caller read it. Raised when the caller's version is already behind,
# and by the repository when another change commits first.
class StaleFlagError(ApplicationError):
    def __init__(self, key: str, *, expected: int, actual: int | None = None) -> None:
        found = f", it is at {actual}" if actual is not None else ""
        super().__init__(f"flag {key!r} is no longer at version {expected}{found}")
        self.key = key
        self.expected = expected
        self.actual = actual
