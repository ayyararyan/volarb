"""External numerical supervisor and fixed, sandboxed evaluator entrypoint.

The supervisor is independent of graph lifetimes. It owns leases; each numerical
attempt is a separate OS process. Only the installed evaluator allowlist runs.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import math
import os
import platform
import resource
import signal
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path
from datetime import datetime, timezone
from typing import Any

from .artifacts import canonical_bytes, fsync_directory, plain
from .registry import Registry, RegistryError, StaleFence, verify_source_binding

EVALUATORS = frozenset({"exp001", "iron_butterfly", "controlled"})


def _atomic_json(path: Path, value: Any) -> None:
    tmp = path.with_name("." + path.name + "-" + uuid.uuid4().hex)
    with tmp.open("xb") as stream:
        stream.write(canonical_bytes(value))
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(tmp, path)
    fsync_directory(path.parent)


def execute_registered_job(input_path: str, output_path: str) -> None:
    """Internal child entry: rechecks immutable fingerprints before numerical work."""
    job = json.loads(Path(input_path).read_text())
    limits = job["resources"]
    cpu = max(1, math.ceil(limits["cpu_seconds"]))
    resource.setrlimit(resource.RLIMIT_CPU, (cpu, cpu))
    resource.setrlimit(resource.RLIMIT_NOFILE, (256, 256))
    # Each file cannot exhaust its allocation; supervisor also caps aggregate bytes.
    file_limit = int(limits["storage_bytes"])
    resource.setrlimit(resource.RLIMIT_FSIZE, (file_limit, file_limit))
    # The child retains its wall-time bound even if its supervisor is killed.
    signal.setitimer(signal.ITIMER_REAL, float(limits["wall_seconds"]))
    if platform.system() == "Linux":
        ram = int(limits["memory_mb"]) * 1024 * 1024
        resource.setrlimit(resource.RLIMIT_AS, (ram, ram))
    else:

        def rss_watchdog() -> None:
            while True:
                used = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / (1024 * 1024)
                if used > limits["memory_mb"]:
                    os._exit(137)
                time.sleep(0.2)

        threading.Thread(target=rss_watchdog, daemon=True).start()
    from .config import environment_hash, evaluator_hash
    from .schemas import DatasetManifest, ExperimentSpec

    experiment = ExperimentSpec.model_validate(job["experiment"]).model_dump(mode="json")
    dataset = DatasetManifest.model_validate(job["dataset"]).model_dump(mode="json")
    if experiment["evaluator"] not in EVALUATORS:
        raise RegistryError("Evaluator is not allowlisted")
    if environment_hash() != job["environment_hash"] or evaluator_hash() != job["evaluator_hash"]:
        raise RegistryError("Environment/evaluator changed after run registration")
    if dataset.get("partition") == "confirmation":
        raise RegistryError("Ordinary numerical worker cannot access protected confirmation")
    verify_source_binding(dataset)
    from .evaluators import evaluate

    started = time.monotonic()
    result = evaluate(experiment, dataset, Path(output_path))
    verify_source_binding(dataset)
    if not isinstance(result, dict):
        raise RegistryError("Numerical evaluator must return an object")
    usage = resource.getrusage(resource.RUSAGE_SELF)
    peak = usage.ru_maxrss / (1024 * 1024 if platform.system() == "Darwin" else 1024)
    _atomic_json(
        Path(output_path) / "worker-result.json",
        {
            "result": result,
            "cpu_seconds": usage.ru_utime + usage.ru_stime,
            "evaluation_wall_seconds": time.monotonic() - started,
            "peak_rss_mb": peak,
        },
    )


def _source_paths(dataset: dict[str, Any], artifact_root: Path) -> tuple[Path, ...]:
    """Source access is explicit, never derived by granting the home directory."""
    paths: list[Path] = []
    if dataset.get("source_path"):
        paths.append(Path(dataset["source_path"]).expanduser().resolve())
    for ref in dataset.get("source_refs", []):
        if str(ref.get("uri", "")).startswith("sha256:"):
            sha = ref["sha256"]
            paths.append(artifact_root / sha[:2] / sha)
    return tuple(paths)


def _rss_mb(pid: int) -> float:
    try:
        if Path(f"/proc/{pid}/status").exists():
            for line in Path(f"/proc/{pid}/status").read_text().splitlines():
                if line.startswith("VmRSS:"):
                    return float(line.split()[1]) / 1024
        result = subprocess.run(
            ["/bin/ps", "-p", str(pid), "-o", "rss="],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
        return float(result.stdout.strip() or 0) / 1024
    except (OSError, ValueError, subprocess.SubprocessError):
        return 0.0


def _stop(process: subprocess.Popen[Any]) -> None:
    if process.poll() is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
        process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        process.wait(timeout=3)
    except ProcessLookupError:
        process.wait(timeout=3)


def _source_receipt() -> tuple[str | None, str | None, str]:
    base = Path(__file__).resolve().parent
    h = hashlib.sha256()
    for path in sorted(base.glob("*.py")):
        h.update(path.name.encode())
        h.update(path.read_bytes())
    try:
        process = subprocess.run(
            ["git", "-C", str(base), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
        commit = process.stdout.strip() if process.returncode == 0 else None
    except (OSError, subprocess.SubprocessError):
        commit = None
    return (
        commit,
        None if commit else "Installed source is not in an accessible Git checkout",
        h.hexdigest(),
    )


class WorkerSupervisor:
    def __init__(
        self,
        root: Path | str,
        *,
        concurrency: int = 1,
        worker_id: str | None = None,
        poll_interval: float = 0.2,
    ):
        if not 1 <= concurrency <= 2 or poll_interval <= 0:
            raise ValueError("Initial local numerical pool must contain one or two workers")
        self.registry = Registry(root)
        self.root = self.registry.root
        self.concurrency = concurrency
        self.worker_id = worker_id or "worker-" + uuid.uuid4().hex
        self.poll_interval = poll_interval
        self.stop_event = threading.Event()

    def run_once(self, slot: int = 0) -> bool:
        from .config import environment_hash, evaluator_hash
        from .security import SandboxPolicy, sandbox_command

        env_hash, engine_hash = environment_hash(), evaluator_hash()
        job = self.registry.claim(
            self.worker_id + f"-{slot}", os.getpid(), max_concurrency=self.concurrency
        )
        if job is None:
            return False
        run, attempt, fence = job["run_id"], job["attempt_id"], job["fence"]
        scratch = self.root / "jobs" / run / attempt
        scratch.mkdir(parents=True, mode=0o700)
        process: subprocess.Popen[Any] | None = None
        try:
            if job["environment_hash"] != env_hash or job["evaluator_hash"] != engine_hash:
                raise RegistryError(
                    "Incompatible environment/evaluator; refusing changed scientific logic"
                )
            if job["experiment"]["evaluator"] not in EVALUATORS:
                raise RegistryError("Evaluator not allowlisted")
            if job["dataset"].get("partition") == "confirmation":
                raise RegistryError("Protected confirmation is not an ordinary queue capability")
            self.registry.check_ordinary_dataset(job["dataset"])
            verify_source_binding(job["dataset"])
            input_path = scratch / "input.json"
            output = scratch / "output"
            output.mkdir(mode=0o700)
            _atomic_json(input_path, job)
            module_root = Path(__file__).resolve().parent.parent
            bootstrap = (
                "import sys;sys.dont_write_bytecode=True;sys.path.insert(0,"
                + repr(str(module_root))
                + ");"
                "from butterfly_lab.workers import execute_registered_job;"
                "execute_registered_job(sys.argv[1],sys.argv[2])"
            )
            limits = job["resources"]
            policy = SandboxPolicy(
                read_paths=(
                    module_root,
                    input_path,
                    *_source_paths(job["dataset"], self.registry.artifacts.root),
                ),
                write_paths=(output,),
                timeout_seconds=limits["wall_seconds"],
                memory_mb=int(limits["memory_mb"]),
            )
            command = sandbox_command(
                [sys.executable, "-I", "-c", bootstrap, str(input_path), str(output)], policy
            )
            clean_env = {
                "PATH": "/usr/bin:/bin",
                "PYTHONDONTWRITEBYTECODE": "1",
                "OPENBLAS_NUM_THREADS": "1",
                "OMP_NUM_THREADS": "1",
                "MKL_NUM_THREADS": "1",
                "TMPDIR": str(output),
            }
            started = time.monotonic()
            started_at = datetime.now(timezone.utc)
            with (
                (scratch / "stdout.log").open("wb") as stdout,
                (scratch / "stderr.log").open("wb") as stderr,
            ):
                self.registry.prepare_job(run, attempt, fence, scratch)
                process = subprocess.Popen(
                    command,
                    stdin=subprocess.DEVNULL,
                    stdout=stdout,
                    stderr=stderr,
                    env=clean_env,
                    cwd=output,
                    start_new_session=True,
                )
                self.registry.start_job(run, attempt, fence, process.pid, scratch)
                next_heartbeat, peak_rss = 0.0, 0.0
                while process.poll() is None:
                    elapsed = time.monotonic() - started
                    if elapsed > limits["wall_seconds"]:
                        raise TimeoutError("Numerical wall-time allocation exhausted")
                    if time.monotonic() >= next_heartbeat:
                        if not self.registry.heartbeat(run, attempt, fence):
                            _stop(process)
                            self.registry.fail(
                                run,
                                attempt,
                                fence,
                                {
                                    "kind": "CANCELLED",
                                    "message": "Cancellation acknowledged; evaluator stopped",
                                },
                                cancelled=True,
                            )
                            return True
                        peak_rss = max(peak_rss, _rss_mb(process.pid))
                        if peak_rss > limits["memory_mb"]:
                            raise MemoryError("Numerical RSS allocation exhausted")
                        size = sum(p.stat().st_size for p in scratch.rglob("*") if p.is_file())
                        if size > limits["storage_bytes"]:
                            raise OSError("Numerical storage allocation exhausted")
                        next_heartbeat = time.monotonic() + 1
                    time.sleep(self.poll_interval)
            if process.returncode != 0:
                # Error text is a local artifact; never include data paths/credentials in public logs.
                error_ref = self.registry.artifacts.put_bytes(
                    (scratch / "stderr.log").read_bytes()[-100_000:], "text/plain"
                )
                self.registry.fail(
                    run,
                    attempt,
                    fence,
                    {
                        "kind": "EVALUATOR_PROCESS_FAILED",
                        "returncode": process.returncode,
                        "stderr_ref": plain(error_ref),
                    },
                )
                return True
            receipt = json.loads((output / "worker-result.json").read_text())
            result = receipt["result"]
            artifacts: dict[str, Any] = {}
            total_bytes = 0
            for path in sorted(output.rglob("*")):
                if path.is_symlink():
                    raise RegistryError("Evaluator output symlinks are forbidden")
                if path.is_file() and path.name != "worker-result.json":
                    total_bytes += path.stat().st_size
                    if total_bytes > limits["storage_bytes"]:
                        raise OSError("Numerical artifact storage allocation exhausted")
                    media = (
                        "application/vnd.apache.parquet"
                        if path.suffix == ".parquet"
                        else "application/json"
                        if path.suffix == ".json"
                        else "text/csv"
                        if path.suffix == ".csv"
                        else "application/octet-stream"
                    )
                    artifacts[str(path.relative_to(output))] = plain(
                        self.registry.artifacts.put_file(path, media)
                    )
            declared_artifacts = result.get("artifacts", {})
            bound_artifacts = {}
            for name, relative in declared_artifacts.items():
                if not isinstance(relative, str) or relative not in artifacts:
                    raise RegistryError("Evaluator declared an absent/nonlocal artifact")
                bound_artifacts[name] = artifacts[relative]
            for name, ref in artifacts.items():
                if ref not in bound_artifacts.values():
                    bound_artifacts[name] = ref
            from .schemas import RunManifest, Quantity

            commit, unknown_reason, tree_hash = _source_receipt()
            config_ref = self.registry.artifacts.put_json(
                {
                    "experiment": job["experiment"],
                    "dataset": job["dataset"],
                    "environment_hash": env_hash,
                    "evaluator_hash": engine_hash,
                }
            )
            manifest = RunManifest(
                run_id=run,
                experiment_id=job["experiment_id"],
                attempt_id=attempt,
                code_commit=commit,
                code_commit_unknown_reason=unknown_reason,
                source_tree_hash=tree_hash,
                environment_hash=env_hash,
                config_ref=config_ref,
                seed=job["experiment"]["seed"],
                worker_identity=self.worker_id + f"-{slot}",
                fencing_token=fence,
                started_at=started_at,
                finished_at=datetime.now(timezone.utc),
                status="COMPLETED",
                artifact_refs=list(bound_artifacts.values()),
                resource_usage={
                    "cpu": Quantity(value=receipt["cpu_seconds"], unit="seconds"),
                    "wall": Quantity(value=time.monotonic() - started, unit="seconds"),
                    "peak_rss": Quantity(value=max(peak_rss, receipt["peak_rss_mb"]), unit="MiB"),
                    "artifacts": Quantity(value=total_bytes, unit="bytes"),
                },
            )
            manifest_ref = self.registry.artifacts.put_json(manifest)
            result.update(
                run_id=run,
                artifacts=bound_artifacts,
                execution={
                    "attempt_id": attempt,
                    "fencing_token": fence,
                    "environment_hash": env_hash,
                    "evaluator_hash": engine_hash,
                    "wall_seconds": time.monotonic() - started,
                    "cpu_seconds": receipt["cpu_seconds"],
                    "peak_rss_mb": max(peak_rss, receipt["peak_rss_mb"]),
                    "artifact_bytes": total_bytes,
                    "sandbox": platform.system(),
                    "provenance": job["dataset"]["provenance"],
                },
            )
            result["run_manifest_ref"] = plain(manifest_ref)
            result_ref = self.registry.artifacts.put_json(result)
            _atomic_json(
                scratch / "published.json",
                {
                    "run_id": run,
                    "attempt_id": attempt,
                    "fence": fence,
                    "result_ref": plain(result_ref),
                },
            )
            # A crash at this line is recovered from published.json after OS death is verified.
            self.registry.complete(
                run, attempt, fence, result_ref, actual_cpu_seconds=receipt["cpu_seconds"]
            )
            return True
        except BaseException as error:
            if process is not None:
                _stop(process)
            try:
                self.registry.fail(
                    run, attempt, fence, {"kind": type(error).__name__, "message": str(error)}
                )
            except StaleFence:
                pass
            if isinstance(error, (KeyboardInterrupt, SystemExit)):
                raise
            return True

    def run(self, *, max_jobs: int | None = None, idle_timeout: float = 2.0) -> dict[str, Any]:
        """Service loop. None max_jobs permits continuous operation until idle_timeout.

        Use idle_timeout < 0 for a persistent service. Threads only supervise;
        numerical computations always execute in sandboxed external processes.
        """
        if max_jobs is not None and max_jobs < 0:
            raise ValueError("max_jobs must be nonnegative")
        started, completed, issued = time.monotonic(), 0, 0
        lock = threading.Lock()

        def loop(slot: int) -> int:
            nonlocal issued
            local, idle_since = 0, time.monotonic()
            while not self.stop_event.is_set():
                with lock:
                    if max_jobs is not None and issued >= max_jobs:
                        break
                    issued += 1
                worked = self.run_once(slot)
                if worked:
                    local += 1
                    idle_since = time.monotonic()
                else:
                    with lock:
                        issued -= 1
                    if idle_timeout >= 0 and time.monotonic() - idle_since >= idle_timeout:
                        break
                    time.sleep(self.poll_interval)
            return local

        with concurrent.futures.ThreadPoolExecutor(max_workers=self.concurrency) as pool:
            futures = [pool.submit(loop, slot) for slot in range(self.concurrency)]
            completed = sum(f.result() for f in futures)
        return {
            "attempts_processed": completed,
            "wall_seconds": time.monotonic() - started,
            "numerical_concurrency": self.concurrency,
            **self.registry.status(),
        }


def start_worker(
    root: Path | str, *, concurrency: int = 1, max_jobs: int | None = None, idle_timeout: float = 2
) -> dict[str, Any]:
    return WorkerSupervisor(root, concurrency=concurrency).run(
        max_jobs=max_jobs, idle_timeout=idle_timeout
    )


def spawn_worker(root: Path | str, *, concurrency: int = 1) -> dict[str, Any]:
    """Detach the supervisor from the caller/graph and return an inspectable PID."""
    registry = Registry(root)
    log = registry.root / "worker-service.log"
    with log.open("ab") as stream:
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "butterfly_lab.workers",
                "--root",
                str(registry.root),
                "--concurrency",
                str(concurrency),
                "--idle-timeout",
                "-1",
            ],
            stdin=subprocess.DEVNULL,
            stdout=stream,
            stderr=stream,
            start_new_session=True,
        )
    registry.add_event(
        "SUPERVISOR_STARTED", str(process.pid), {"pid": process.pid, "concurrency": concurrency}
    )
    return {"pid": process.pid, "log": str(log), "concurrency": concurrency}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True)
    parser.add_argument("--concurrency", type=int, default=1)
    parser.add_argument("--max-jobs", type=int)
    parser.add_argument("--idle-timeout", type=float, default=2)
    args = parser.parse_args()
    print(
        json.dumps(
            start_worker(
                args.root,
                concurrency=args.concurrency,
                max_jobs=args.max_jobs,
                idle_timeout=args.idle_timeout,
            )
        )
    )


if __name__ == "__main__":
    main()
