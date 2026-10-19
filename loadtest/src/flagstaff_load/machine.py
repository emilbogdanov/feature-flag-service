from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

_UNKNOWN = "unknown"


# What the numbers were measured on. The load generator shares the machine with the stack, so
# both compete for the same cores.
@dataclass(frozen=True, slots=True)
class Machine:
    os: str
    cpu: str
    logical_cores: int
    python: str
    docker: str


def describe_machine() -> Machine:
    return Machine(
        os=platform.platform(terse=True),
        cpu=_cpu_name(),
        logical_cores=os.cpu_count() or 0,
        python=platform.python_version(),
        docker=_docker(),
    )


def _cpu_name() -> str:
    # if/else rather than an early return, so the type check passes on every platform.
    if sys.platform == "win32":
        import winreg  # noqa: PLC0415

        key_path = r"HARDWARE\DESCRIPTION\System\CentralProcessor\0"
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path) as key:
            name, _ = winreg.QueryValueEx(key, "ProcessorNameString")
        found = str(name).strip()
    else:
        found = _cpu_name_from_proc()
    return found or platform.processor() or _UNKNOWN


def _cpu_name_from_proc() -> str:
    cpuinfo = Path("/proc/cpuinfo")
    if not cpuinfo.exists():
        return ""
    for line in cpuinfo.read_text(encoding="utf-8").splitlines():
        if line.startswith("model name"):
            return line.partition(":")[2].strip()
    return ""


# Docker Desktop gives its containers a share of the machine, which is what the stack ran on.
def _docker() -> str:
    docker = shutil.which("docker")
    if docker is None:
        return _UNKNOWN
    try:
        finished = subprocess.run(  # noqa: S603  # fixed arguments; only docker's path varies
            [docker, "info", "--format", "{{.ServerVersion}}|{{.NCPU}}|{{.MemTotal}}"],
            capture_output=True,
            text=True,
            check=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return _UNKNOWN
    version, cpus, memory = finished.stdout.strip().split("|")
    return f"{version}, with {cpus} CPUs and {int(memory) / 2**30:.1f} GiB for containers"
