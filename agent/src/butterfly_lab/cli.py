"""Operator CLI. All numerical executions require a registered approved campaign."""

from __future__ import annotations

import argparse
import json
import os
import secrets
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .artifacts import plain
from .config import environment_hash, evaluator_hash, runtime_root
from .registry import Registry
from .schemas import CampaignSpec, DatasetManifest, ExperimentSpec


def read_json(path):
    return json.loads(Path(path).read_text())


def emit(value):
    print(json.dumps(plain(value), sort_keys=True, indent=2, default=str))


def provider_service(root, config_path):
    from .agents import AgentService
    from .providers import OpenAIConfig, OpenAIProvider, ReplayProvider

    cfg = read_json(config_path)
    if cfg.pop("kind", "openai") == "replay":
        provider = ReplayProvider(read_json(cfg["records"]))
    else:
        cfg["ledger_path"] = root / "provider-budget.json"
        provider = OpenAIProvider(OpenAIConfig(**cfg))
    return AgentService(provider, Registry(root), max_calls=cfg.get("max_calls", 20))


def lab_for(args, root):
    from .graph import Laboratory

    return Laboratory(
        root,
        provider_service(root, args.provider_config)
        if getattr(args, "provider_config", None)
        else None,
    )


def drain(root, campaign_id, timeout=120, provider_config=None):
    """Bounded operator-requested watcher; numerical supervision stays external."""
    from .graph import Laboratory

    worker = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "butterfly_lab.workers",
            "--root",
            str(root),
            "--concurrency",
            "2",
            "--idle-timeout",
            "-1",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    lab = Laboratory(root, provider_service(root, provider_config) if provider_config else None)
    started = time.monotonic()
    try:
        while True:
            for exp in lab.registry.list("experiments", campaign_id):
                if not lab.registry.get("findings", "finding-" + exp["id"]):
                    lab.resume(exp["id"])
            report = lab.campaign_report(campaign_id)
            if not report["pending_experiments"]:
                worker.terminate()
                output, error = worker.communicate(timeout=10)
                return {
                    "worker": {
                        "supervisor_pid": worker.pid,
                        "completed": True,
                        "wall_seconds": time.monotonic() - started,
                    },
                    "report": report,
                    "confirmation": lab.advance_confirmation(campaign_id),
                }
            if worker.poll() is not None:
                output, error = worker.communicate()
                raise RuntimeError(
                    "numerical supervisor exited before campaign completion: " + error[-2000:]
                )
            if time.monotonic() - started >= timeout:
                # Leave authorized jobs and their supervisor alive and reconcilable.
                return {
                    "status": "WORKER_CONTINUES",
                    "pid": worker.pid,
                    "report": report,
                    "next": "reconcile, then resume",
                }
            time.sleep(0.1)
    finally:
        lab.close()


def confirmation_service(root):
    from .confirmation import ConfirmationService

    reg = Registry(root)
    private = root / "authority"
    private.mkdir(mode=0o700, exist_ok=True)
    for name in ("signing.key", "authorization.key"):
        path = private / name
        if not path.exists():
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            with os.fdopen(fd, "w") as handle:
                handle.write(secrets.token_hex(32))
    secret = (private / "authorization.key").read_text()
    return ConfirmationService(
        reg, reg.artifacts, (private / "signing.key").read_bytes(), secret
    ), secret


def demo(root, kind="all"):
    from .fixtures import generate_spot_fixture, generate_option_fixture, default_ironfly_parameters
    from .graph import Laboratory
    from .agents import load_seeds

    config = Path(__file__).parent / "resources" / "seeds.json"
    if not config.exists():
        config = Path(__file__).resolve().parents[2] / "configs" / "seeds.json"
    kinds = ["spot", "fourleg"] if kind == "all" else [kind]
    reports = []
    for selected in kinds:
        id = "demo-" + selected
        data = (generate_spot_fixture if selected == "spot" else generate_option_fixture)(
            root / "fixtures" / (selected + (".csv" if selected == "spot" else ".parquet"))
        )
        data = DatasetManifest.model_validate(data)
        campaign = CampaignSpec(
            id=id,
            objective="Controlled reproducible research lifecycle and negative/data-limited evidence",
            approved=True,
            max_hypotheses=2,
        )
        seeds = load_seeds(config, id)
        if selected == "spot":
            h = seeds[0]
        else:
            h = seeds[10].model_copy(
                update={
                    "minimum_data": ["identified_contracts", "two_sided_quotes"],
                    "proposed_dsl": default_ironfly_parameters(),
                }
            )
        blocked = seeds[11].model_copy(
            update={"id": id + "-blocked", "minimum_data": ["multi_index_synchronized_history"]}
        )
        lab = Laboratory(root)
        try:
            lab.registry.put("campaigns", id, campaign)
            lab.registry.put("datasets", data.id, data)
            lab.run_campaign(
                id, data.id, [h.model_dump(mode="json"), blocked.model_dump(mode="json")]
            )
        finally:
            lab.close()
        reports.append(drain(root, id))
    return {"label": "SYNTHETIC fixtures, no historical economic evidence", "examples": reports}


def parser():
    p = argparse.ArgumentParser(prog="butterfly-lab", description=__doc__)
    p.add_argument("--root", help="Private non-cloud runtime directory")
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("doctor")
    d = sub.add_parser("demo")
    d.add_argument("--kind", choices=["all", "spot", "fourleg"], default="all")
    sch = sub.add_parser("schemas")
    sch.add_argument("--output", required=True)
    for group, actions in {
        "data": ["inspect", "validate", "register"],
        "experiment": ["validate", "run", "status", "report"],
        "campaign": ["validate", "run", "status", "cancel", "report"],
        "worker": ["start", "status"],
        "confirmation": ["freeze", "authorize", "evaluate", "report"],
    }.items():
        g = sub.add_parser(group)
        a = g.add_subparsers(dest="action", required=True)
        for action in actions:
            q = a.add_parser(action)
            if group == "data" or action == "validate":
                q.add_argument("file")
            elif group in ("campaign", "experiment") and action == "run":
                q.add_argument("file")
                q.add_argument("--wait", action="store_true")
                q.add_argument("--provider-config")
                if group == "campaign":
                    q.add_argument("--dataset", required=True)
                    q.add_argument("--hypotheses")
            elif group == "worker" and action == "start":
                q.add_argument("--concurrency", type=int, default=1)
                q.add_argument("--max-jobs", type=int)
                q.add_argument("--detach", action="store_true")
                q.add_argument("--idle-timeout", type=float, default=2)
            elif group == "confirmation":
                q.add_argument("id")
                if action == "freeze":
                    q.add_argument("file")
                if action == "authorize":
                    q.add_argument("--principal", required=True)
                    q.add_argument("--expires-hours", type=int, default=1)
                if action == "evaluate":
                    q.add_argument("--token-file", required=True)
            elif group != "worker":
                q.add_argument("id")
    r = sub.add_parser("resume")
    r.add_argument("id", nargs="?")
    r.add_argument("--provider-config")
    sub.add_parser("reconcile")
    b = sub.add_parser("backup")
    b.add_argument("destination")
    b = sub.add_parser("restore")
    b.add_argument("source")
    b = sub.add_parser("benchmark")
    b.add_argument("kind", choices=["scientific", "compare", "load"])
    b.add_argument("--jobs", type=int, default=2000)
    b.add_argument("--hypotheses", type=int, default=250)
    return p


def dispatch(args):
    if args.command == "restore":
        from .backup import restore

        target = (
            Path(
                args.root
                or os.environ.get("BUTTERFLY_LAB_HOME", Path.home() / ".local/share/butterfly-lab")
            )
            .expanduser()
            .resolve()
        )
        return restore(Path(args.source), target)
    root = runtime_root(args.root)
    if args.command == "doctor":
        from .security import verify_boundary

        return {
            "python": sys.version.split()[0],
            "environment_hash": environment_hash(),
            "evaluator_hash": evaluator_hash(),
            "runtime": str(root),
            "sandbox": verify_boundary(),
            "broker_execution": False,
            "provider_smoke": "not run; explicit provider credentials and budget required",
        }
    if args.command == "schemas":
        from .schemas import CONTRACTS

        dest = Path(args.output)
        dest.mkdir(parents=True, exist_ok=True)
        for model in CONTRACTS:
            (dest / (model.__name__ + ".json")).write_text(
                json.dumps(model.model_json_schema(), indent=2, sort_keys=True) + "\n"
            )
        return {"schemas": len(CONTRACTS)}
    if args.command == "demo":
        return demo(root, args.kind)
    registry = Registry(root)
    if args.command == "data":
        from .data import qualify_dataset

        data = DatasetManifest.model_validate(read_json(args.file))
        if data.partition == "confirmation":
            if args.action != "register":
                raise PermissionError(
                    "Protected confirmation cannot be inspected by ordinary data commands"
                )
            registry.put("datasets", data.id, data)
            return {"dataset": data.id, "status": "PROTECTED_MANIFEST_REGISTERED_WITHOUT_READING"}
        registry.check_ordinary_dataset(data.model_dump(mode="json"))
        report = qualify_dataset(data.model_dump(mode="json"))
        if args.action == "register":
            # Keep unavailable sources registered honestly; admission rechecks capability.
            data = data.model_copy(
                update={
                    "capabilities": report.get("capabilities", []),
                    "qualification_ref": registry.artifacts.put_json(report),
                }
            )
            registry.put("datasets", data.id, data)
        return {"dataset": data.id, "qualification": report}
    if args.command == "worker":
        from .workers import start_worker, spawn_worker

        if args.action == "status":
            return registry.status()
        if args.detach:
            return spawn_worker(root, concurrency=args.concurrency)
        return start_worker(
            root,
            concurrency=args.concurrency,
            max_jobs=args.max_jobs,
            idle_timeout=args.idle_timeout,
        )
    if args.command == "reconcile":
        return registry.reconcile()
    if args.command in ("backup", "restore"):
        from .backup import backup, restore

        return (
            backup(root, Path(args.destination))
            if args.command == "backup"
            else restore(Path(args.source), root)
        )
    if args.command == "confirmation":
        service, secret = confirmation_service(root)
        if args.action == "freeze":
            return service.freeze(args.id, **read_json(args.file))
        if args.action == "authorize":
            receipt = service.authorize(
                args.id,
                args.principal,
                (datetime.now(timezone.utc) + timedelta(hours=args.expires_hours)).isoformat(),
                secret,
            )
            path = root / "authority" / (args.id + ".release.json")
            path.write_text(json.dumps(receipt))
            path.chmod(0o600)
            return {"authorization_file": str(path), "batch_id": args.id}
        if args.action == "evaluate":
            return {
                "bundle": service.evaluate(args.id, read_json(args.token_file)["signature"]),
                "findings": service.publish_findings(args.id),
            }
        return service.report(args.id)
    if args.command == "benchmark":
        from .benchmarks import scientific_benchmark, comparison_benchmark, load_benchmark

        if args.kind == "scientific":
            return scientific_benchmark(root)
        if args.kind == "compare":
            return comparison_benchmark(root)
        return load_benchmark(root, jobs=args.jobs, hypotheses=args.hypotheses)
    if args.command == "resume":
        lab = lab_for(args, root)
        try:
            if args.id and registry.get("campaigns", args.id):
                return lab.advance_confirmation(args.id)
            ids = [args.id] if args.id else [e["id"] for e in registry.list("experiments")]
            return [{"experiment_id": id, **lab.resume(id)} for id in ids]
        finally:
            lab.close()
    kind = args.command
    model = CampaignSpec if kind == "campaign" else ExperimentSpec
    if args.action == "validate":
        return model.model_validate(read_json(args.file)).model_dump(mode="json")
    if args.action == "cancel":
        return registry.cancel_campaign(args.id)
    if args.action == "status":
        return (
            registry.status(args.id)
            if kind == "campaign"
            else {
                "experiment": registry.get("experiments", args.id),
                "runs": [r for r in registry.runs() if r["experiment_id"] == args.id],
            }
        )
    lab = lab_for(args, root)
    try:
        if args.action == "report":
            return (
                lab.campaign_report(args.id)
                if kind == "campaign"
                else registry.get("findings", "finding-" + args.id)
            )
        value = read_json(args.file)
        if kind == "experiment":
            value.update(environment_hash=environment_hash(), implementation_hash=evaluator_hash())
        obj = model.model_validate(value)
        registry.put(kind, obj.id, obj)
        if kind == "campaign":
            data = DatasetManifest.model_validate(read_json(args.dataset))
            registry.put("datasets", data.id, data)
            hypotheses = read_json(args.hypotheses) if args.hypotheses else None
            result = lab.run_campaign(obj.id, data.id, hypotheses)
            campaign_id = obj.id
        else:
            if not registry.get("hypotheses", obj.hypothesis_id):
                raise ValueError("register hypothesis through campaign first")
            registry.put(
                "trial",
                obj.trial_id,
                {
                    "id": obj.trial_id,
                    "campaign_id": obj.campaign_id,
                    "hypothesis_id": obj.hypothesis_id,
                    "relation": obj.relation.value,
                    "parent_experiment_id": obj.parent_experiment_id,
                    "informed_by_result_ids": obj.informed_by_result_ids,
                },
            )
            result = lab.run_experiment(obj.id)
            campaign_id = obj.campaign_id
        return (
            drain(root, campaign_id, provider_config=args.provider_config) if args.wait else result
        )
    finally:
        lab.close()


def main():
    args = parser().parse_args()
    try:
        emit(dispatch(args))
    except (ValueError, KeyError, PermissionError, RuntimeError, OSError) as error:
        emit({"error": type(error).__name__, "detail": str(error)})
        raise SystemExit(2) from error


if __name__ == "__main__":
    main()
