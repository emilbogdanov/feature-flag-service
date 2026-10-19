import ast
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

import flagstaff.engine

ENGINE_MODULES = sorted(Path(flagstaff.engine.__file__).parent.glob("*.py"))


def imported_modules(path: Path) -> Iterator[str]:
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            yield from (alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            yield node.module


# The server and the SDK both evaluate flags with this package, so it must not pull in
# anything from either side: no HTTP client, no ORM, not even the rest of the SDK.
@pytest.mark.parametrize("path", ENGINE_MODULES, ids=lambda path: path.name)
def test_engine_depends_only_on_the_standard_library(path: Path) -> None:
    foreign = [
        module
        for module in imported_modules(path)
        if module.partition(".")[0] not in sys.stdlib_module_names
        and module != "flagstaff.engine"
        and not module.startswith("flagstaff.engine.")
    ]

    assert foreign == []
