import subprocess
import sys
import platform
from pathlib import Path

import pytest

from butterfly_lab.security import (
    BoundaryUnavailable,
    ResourceLimitExceeded,
    SandboxPolicy,
    run_sandboxed,
    sandbox_command,
    verify_boundary,
)


def require_boundary():
    try:
        return verify_boundary()
    except BoundaryUnavailable as exc:
        pytest.skip("Host cannot run protected operation; application fails closed: " + str(exc))


def test_actual_confirmation_read_evaluator_write_network_and_secret_denied():
    report = require_boundary()
    assert all(report["checks"].values())


def test_no_boundary_fails_closed(monkeypatch):
    monkeypatch.setattr("butterfly_lab.security.shutil.which", lambda name: None)
    with pytest.raises(BoundaryUnavailable):
        sandbox_command([sys.executable, "-c", "print(1)"], SandboxPolicy())


def test_allowed_output_is_writable_protected_input_is_not(tmp_path):
    require_boundary()
    source = tmp_path / "source.txt"
    source.write_text("fixture")
    output = tmp_path / "out"
    output.mkdir()
    script = "from pathlib import Path; import sys; Path(sys.argv[2]).write_text(Path(sys.argv[1]).read_text())"
    result = run_sandboxed(
        [sys.executable, "-c", script, str(source), str(output / "artifact")],
        SandboxPolicy(read_paths=(source,), write_paths=(output,)),
    )
    assert result.returncode == 0, result.stderr
    assert (output / "artifact").read_text() == "fixture"
    with pytest.raises(ValueError, match="environment"):
        run_sandboxed(
            [sys.executable, "-c", "pass"], SandboxPolicy(), env={"OPENAI_API_KEY": "fixture"}
        )


def test_broad_writes_and_timeout():
    with pytest.raises(ValueError):
        SandboxPolicy(write_paths=(Path.home(),))
    require_boundary()
    with pytest.raises(subprocess.TimeoutExpired):
        run_sandboxed(
            [sys.executable, "-c", "import time; time.sleep(5)"], SandboxPolicy(timeout_seconds=0.1)
        )


def test_macos_confirmation_process_measured_memory_limit():
    if platform.system() != "Darwin":
        pytest.skip("Linux uses enforced RLIMIT_AS rather than macOS RSS watchdog")
    require_boundary()
    with pytest.raises(ResourceLimitExceeded):
        run_sandboxed(
            [sys.executable, "-c", "import time; data=bytearray(30*1024*1024); time.sleep(2)"],
            SandboxPolicy(memory_mb=16, timeout_seconds=5),
        )
