"""Enforced local subprocess boundary; never confuses permissions with prompts.

The trusted operator and operating-system administrator are outside the threat
model. Untrusted research/evaluation subprocesses have no inherited credentials,
network, general home-directory access, or evaluator write permission.
"""

from __future__ import annotations

import json
import math
import os
import platform
import resource
import signal
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class BoundaryUnavailable(RuntimeError):
    """The host cannot enforce the requested security boundary."""


class ResourceLimitExceeded(RuntimeError):
    """A protected process exceeded its measured resource limit."""


@dataclass(frozen=True)
class SandboxPolicy:
    read_paths: tuple[Path, ...] = ()
    write_paths: tuple[Path, ...] = ()
    denied_paths: tuple[Path, ...] = ()
    timeout_seconds: float = 60
    memory_mb: int = 1024

    def __post_init__(self) -> None:
        if self.timeout_seconds <= 0 or self.memory_mb <= 0:
            raise ValueError("Sandbox limits must be positive")
        for path in self.write_paths:
            resolved = Path(path).resolve()
            if resolved in (Path("/"), Path.home(), Path(sys.prefix).resolve()):
                raise ValueError("Refusing broad or runtime write access")
        for allowed in self.read_paths + self.write_paths:
            if Path(allowed).resolve() in (Path("/"), Path.home()):
                raise ValueError("Refusing broad home/root read access")


def _runtime_paths() -> tuple[Path, ...]:
    values = [Path(sys.prefix), Path(sys.base_prefix), Path(sys.executable).resolve()]
    binary = Path(sys.executable)
    if binary.is_symlink():
        target = Path(os.readlink(binary))
        target = target if target.is_absolute() else binary.parent / target
        # uv/venv interpreters may pass through a version-alias symlink. macOS
        # checks the lexical alias as well as its canonical target.
        for parent in target.parents:
            if parent.is_symlink():
                values.append(parent)
    if platform.system() == "Darwin":
        values.extend(Path(p) for p in ("/usr", "/System/Library", "/Library/Apple"))
    else:
        values.extend(Path(p) for p in ("/usr", "/lib", "/lib64", "/bin", "/etc/ld.so.cache"))
    return tuple(sorted({p.absolute() for p in values if p.exists()}, key=str))


def sandbox_command(command: list[str], policy: SandboxPolicy) -> list[str]:
    """Wrap an argv in an OS sandbox; no shell and no permissive fallback."""
    if not command:
        raise ValueError("Empty sandbox command")
    reads = tuple(
        dict.fromkeys(_runtime_paths() + tuple(Path(p).resolve() for p in policy.read_paths))
    )
    writes = tuple(Path(p).resolve() for p in policy.write_paths)
    denied = tuple(Path(p).resolve() for p in policy.denied_paths)
    if platform.system() == "Darwin" and shutil.which("sandbox-exec"):
        rules = [
            "(version 1)",
            "(deny default)",
            "(allow process-exec)",
            "(allow process-fork)",
            "(allow signal (target self))",
            "(allow sysctl-read)",
            '(allow file-read* (literal "/"))',
            '(allow file-read* file-write* (literal "/dev/null"))',
            '(allow file-read* (literal "/dev/urandom") (literal "/dev/random"))',
        ]
        for path in reads + writes:
            kind = "subpath" if path.is_dir() else "literal"
            rules.append(f"(allow file-read* ({kind} {json.dumps(str(path))}))")
        for path in writes:
            rules.append(f"(allow file-write* (subpath {json.dumps(str(path))}))")
        for path in denied:
            rules.append(f"(deny file-read* file-write* (subpath {json.dumps(str(path))}))")
        return ["/usr/bin/sandbox-exec", "-p", "".join(rules), *command]
    if platform.system() == "Linux" and shutil.which("bwrap"):
        argv = [
            "bwrap",
            "--unshare-all",
            "--die-with-parent",
            "--new-session",
            "--proc",
            "/proc",
            "--dev",
            "/dev",
            "--tmpfs",
            "/tmp",
        ]
        for path in reads:
            argv.extend(["--ro-bind", str(path), str(path)])
        for path in writes:
            argv.extend(["--bind", str(path), str(path)])
        for path in denied:
            if path.is_dir():
                argv.extend(["--tmpfs", str(path)])
            elif path.exists():
                argv.extend(["--ro-bind", "/dev/null", str(path)])
        return [*argv, "--", *command]
    raise BoundaryUnavailable(
        "Protected operations require working macOS sandbox-exec or Linux bwrap"
    )


def run_sandboxed(
    command: list[str],
    policy: SandboxPolicy,
    *,
    input_text: str | None = None,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Execute with a scrubbed environment, wall/CPU limits and Linux address limit.

    macOS does not reliably support RLIMIT_AS for Python scientific runtimes;
    the numerical supervisor additionally enforces measured RSS there.
    """
    clean_env = {
        "PATH": "/usr/bin:/bin",
        "PYTHONDONTWRITEBYTECODE": "1",
        "OPENBLAS_NUM_THREADS": "1",
        "OMP_NUM_THREADS": "1",
        "MKL_NUM_THREADS": "1",
    }
    allowed_env = {"PYTHONPATH", "OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"}
    for key, value in (env or {}).items():
        if key not in allowed_env:
            raise ValueError(f"Sandbox environment key not allowed: {key}")
        clean_env[key] = value

    def limits() -> None:
        cpu = max(1, math.ceil(policy.timeout_seconds))
        resource.setrlimit(resource.RLIMIT_CPU, (cpu, cpu + 1))
        if platform.system() == "Linux":
            limit = policy.memory_mb * 1024 * 1024
            resource.setrlimit(resource.RLIMIT_AS, (limit, limit))

    try:
        process = subprocess.Popen(
            sandbox_command(command, policy),
            text=True,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=clean_env,
            cwd="/",
            preexec_fn=limits,
            start_new_session=True,
        )
        started = time.monotonic()
        initial_input = input_text
        while True:
            try:
                stdout, stderr = process.communicate(input=initial_input, timeout=0.1)
                return subprocess.CompletedProcess(command, process.returncode, stdout, stderr)
            except subprocess.TimeoutExpired:
                initial_input = None
                limit_error: Exception | None = None
                if time.monotonic() - started >= policy.timeout_seconds:
                    limit_error = subprocess.TimeoutExpired(command, policy.timeout_seconds)
                if platform.system() == "Darwin":
                    measured = subprocess.run(
                        ["/bin/ps", "-o", "rss=", "-p", str(process.pid)],
                        text=True,
                        capture_output=True,
                        timeout=2,
                        check=False,
                    )
                    if (
                        measured.stdout.strip()
                        and int(measured.stdout.strip()) > policy.memory_mb * 1024
                    ):
                        limit_error = ResourceLimitExceeded(
                            "Protected process exceeded measured RSS limit"
                        )
                if limit_error is not None:
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    process.communicate()
                    raise limit_error
    except OSError as exc:
        raise BoundaryUnavailable(f"Sandbox launch failed: {type(exc).__name__}") from exc


def verify_boundary() -> dict[str, Any]:
    """Actually attempt forbidden reads, protected writes, network and secret access."""
    with tempfile.TemporaryDirectory(prefix="butterfly-boundary-") as temp:
        root = Path(temp).resolve()
        allowed = root / "allowed"
        allowed.mkdir()
        forbidden = root / "confirmation.txt"
        forbidden.write_text("fixture-only-secret", encoding="utf-8")
        evaluator = allowed / "protected.py"
        evaluator.write_text("protected", encoding="utf-8")
        script = """import json, os, socket, sys
results = {}
for name, path, mode in [('confirmation_read', sys.argv[1], 'r'), ('evaluator_write', sys.argv[2], 'w')]:
    try:
        with open(path, mode) as stream:
            if mode == 'r': stream.read()
            else: stream.write('mutated')
        results[name] = False
    except PermissionError: results[name] = True
    except FileNotFoundError: results[name] = True
try:
    sock = socket.socket(); sock.settimeout(0.3); sock.connect(('127.0.0.1', 9))
    results['network'] = False
except PermissionError: results['network'] = True
except OSError as e: results['network'] = e.errno in (1, 13, 101)
results['credentials'] = not any(k in os.environ for k in ['OPENAI_API_KEY', 'DHAN_ACCESS_TOKEN', 'AWS_SECRET_ACCESS_KEY'])
print(json.dumps(results))
"""
        process = run_sandboxed(
            [sys.executable, "-c", script, str(forbidden), str(evaluator)],
            SandboxPolicy(read_paths=(allowed,), timeout_seconds=10),
        )
        if process.returncode != 0:
            raise BoundaryUnavailable(
                "Sandbox denial probe could not execute: " + process.stderr[-500:]
            )
        results = json.loads(process.stdout)
        if not all(results.values()) or evaluator.read_text(encoding="utf-8") != "protected":
            raise BoundaryUnavailable("Sandbox did not enforce every required boundary")
        return {
            "available": True,
            "backend": platform.system(),
            "checks": results,
            "threat_model": "untrusted child processes, not host operator/root",
        }
