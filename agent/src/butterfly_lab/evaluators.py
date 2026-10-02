"""Protected numerical evaluators: predictive EXP-001 and four-leg economics.

Entry point is called only by the registered external worker. No network, broker
or live-accounting dependency is reachable from these calculations.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .accounting import Account, Contract, dated_spec, fee_for_fill
from .baselines import policy_decision, select_b0
from .data import DataQualificationError, load_dataset, metadata, qualify_dataset
from .statistics import paired_inference, robustness


EXP001_DEFINITION = {
    "version": "1",
    "origin": "10:05:00",
    "horizon_minutes": 30,
    "return_count": 30,
    "lag_seconds": 60,
    "rv_floor": 1e-16,
    "excursion_floor": 1e-8,
    "ridge": 0.001,
    "scale_floor": 1e-12,
    "transformation": "exp(log-excursion ridge prediction), no smearing; MAE absolute log-relative excursion * 10000",
    "refitting": "expanding monthly; outcomes available before first origin of month",
}


def _write(frame: pd.DataFrame, directory: Path, name: str) -> str:
    path = directory / f"{name}.parquet"
    frame.to_parquet(path, index=False)
    return path.name


def _infer(
    b: list[float], c: list[float], experiment: dict[str, Any], metric: str
) -> dict[str, Any]:
    plan = experiment.get("inference", {})
    result = paired_inference(
        b,
        c,
        metric=metric,
        block_length=int(plan.get("block_length", 5)),
        repetitions=int(plan.get("bootstrap_samples", 999)),
        seed=int(experiment.get("seed", 17)),
        practical_effect=float(plan.get("practical_effect", 0.01)),
        relative=metric == "loss",
        alpha=float(plan.get("alpha", 0.05)),
    )
    if len(b) < int(plan.get("minimum_sessions", 30)):
        result.update(outcome="INCONCLUSIVE", precision="insufficient")
    return result


def exp001_features(
    frame: pd.DataFrame, dataset: dict[str, Any]
) -> tuple[pd.DataFrame, pd.DataFrame]:
    if not dataset.get("timestamp_convention_verified", False):
        raise DataQualificationError("EXP001 requires verified bar-label convention")
    if int(dataset.get("availability_lag_seconds", 0)) != 60:
        raise DataQualificationError(
            "EXP001-v1 requires frozen conservative 60-second availability lag"
        )
    if int(metadata(dataset).get("bar_seconds", 60)) != 60:
        raise DataQualificationError("EXP001 requires one-minute bars")
    if "close" not in frame or (frame.close <= 0).any():
        raise DataQualificationError("positive spot closes required")
    dates = sorted(set(frame.session) | set(dataset.get("session_dates", [])))
    ledger, features = [], []
    groups = {
        key: group.set_index("bar_end", drop=False) for key, group in frame.groupby("session")
    }
    for date in dates:
        origin = pd.Timestamp(f"{date} 10:05:00", tz="Asia/Kolkata").tz_convert("UTC")
        rec: dict[str, Any] = {
            "session": date,
            "origin": origin,
            "status": "ELIGIBLE",
            "reason": "",
        }
        group = groups.get(date)
        past = pd.date_range(
            origin - pd.Timedelta(minutes=31), origin - pd.Timedelta(minutes=1), freq="min"
        )
        future = pd.date_range(
            origin + pd.Timedelta(minutes=1), origin + pd.Timedelta(minutes=30), freq="min"
        )
        if group is None or not set(past).issubset(group.index):
            rec.update(status="MISSING_FEATURE", reason="31 complete past closes required")
        elif not set(future).issubset(group.index):
            rec.update(
                status="MISSING_TARGET", reason="all 30 target closes required; no forward filling"
            )
        else:
            before, after = group.loc[past], group.loc[future]
            if (
                not before.session_class.eq("regular").all()
                or not after.session_class.eq("regular").all()
            ):
                rec.update(
                    status="SESSION_UNQUALIFIED", reason="registered session classification failed"
                )
            elif (before.available_at > origin).any():
                rec.update(status="LATE_FEATURE", reason="feature unavailable at origin")
            else:
                closes = before.close.to_numpy(dtype=float)
                returns = np.diff(np.log(closes))
                rv = float(returns @ returns)
                drift = float(abs(returns.sum()) / math.sqrt(rv)) if rv > 0 else 0.0
                excursion = float(
                    np.max(np.abs(np.log(after.close.to_numpy(dtype=float) / closes[-1])))
                )
                features.append(
                    {
                        "session": date,
                        "origin": origin,
                        "reference": closes[-1],
                        "rv": rv,
                        "log_rv": math.log(max(rv, 1e-16)),
                        "drift": drift,
                        "excursion": excursion,
                        "log_excursion": math.log(max(excursion, 1e-8)),
                        "feature_available_at": before.available_at.max(),
                        "label_available_at": after.available_at.max(),
                        "degenerate_rv": rv == 0,
                        "degenerate_excursion": excursion == 0,
                    }
                )
        ledger.append(rec)
    return pd.DataFrame(features), pd.DataFrame(ledger)


def _ridge_predict(train: pd.DataFrame, predict: pd.DataFrame, columns: list[str]) -> np.ndarray:
    x, xp = train[columns].to_numpy(float), predict[columns].to_numpy(float)
    means, scales = x.mean(axis=0), x.std(axis=0)
    scales = np.maximum(scales, 1e-12)
    design = np.column_stack([np.ones(len(x)), (x - means) / scales])
    target = train.log_excursion.to_numpy(float)
    penalty = np.diag([0.0] + [0.001] * len(columns))
    coeff = np.linalg.solve(design.T @ design + penalty, design.T @ target)
    log_prediction = np.column_stack([np.ones(len(xp)), (xp - means) / scales]) @ coeff
    # Bounds are fixed numeric safety, not data-selected economic clipping.
    return np.exp(np.clip(log_prediction, math.log(1e-8), 20.0))


def exp001_predictions(features: pd.DataFrame, experiment: dict[str, Any]) -> pd.DataFrame:
    split = experiment.get("split", {})
    end = split.get("train_end", "2023-12-31")
    evaluation_end = split.get("evaluation_end", "2026-08-31")
    minimum = int(split.get("minimum_training_sessions", 30))
    eligible = features[(features.session > end) & (features.session <= evaluation_end)].copy()
    eligible["month"] = (
        eligible.session.str[:7]
        if split.get("refit", "expanding_monthly") == "expanding_monthly"
        else "frozen"
    )
    output = []
    for _, group in eligible.groupby("month", sort=True):
        cutoff = group.origin.min()
        if split.get("refit", "expanding_monthly") == "frozen":
            train = features[features.session <= end]
        else:
            train = features[features.origin < cutoff]
        train = train[train.label_available_at < cutoff]
        if len(train) < minimum:
            for row in group.to_dict("records"):
                output.append({**row, "status": "INSUFFICIENT_TRAINING", "train_n": len(train)})
            continue
        b = _ridge_predict(train, group, ["log_rv"])
        c = _ridge_predict(train, group, ["log_rv", "drift"])
        scale = float(
            np.median(train.excursion.to_numpy() / np.sqrt(np.maximum(train.rv.to_numpy(), 1e-16)))
        )
        for idx, row in enumerate(group.to_dict("records")):
            output.append(
                {
                    **row,
                    "status": "EVALUATED",
                    "train_n": len(train),
                    "train_end": train.session.max(),
                    "training_label_cutoff": train.label_available_at.max(),
                    "fit_at": cutoff,
                    "baseline_prediction": float(b[idx]),
                    "candidate_prediction": float(c[idx]),
                    "control_prediction": float(scale * math.sqrt(max(row["rv"], 1e-16))),
                    "baseline_loss": abs(row["excursion"] - float(b[idx])) * 10000,
                    "candidate_loss": abs(row["excursion"] - float(c[idx])) * 10000,
                    "control_loss": abs(row["excursion"] - scale * math.sqrt(max(row["rv"], 1e-16)))
                    * 10000,
                }
            )
    return pd.DataFrame(output)


def _exp001(
    experiment: dict[str, Any], dataset: dict[str, Any], frame: pd.DataFrame, directory: Path
) -> dict[str, Any]:
    features, ledger = exp001_features(frame, dataset)
    artifacts = {"opportunities": _write(ledger, directory, "opportunities")}
    if features.empty:
        return {
            "outcome": "DATA_LIMITED",
            "limitations": ["No complete feature/target session"],
            "metrics": {},
            "artifacts": artifacts,
        }
    predictions = exp001_predictions(features, experiment)
    artifacts.update(
        features=_write(features, directory, "features"),
        predictions=_write(predictions, directory, "predictions"),
        exclusions=_write(ledger[ledger.status.ne("ELIGIBLE")], directory, "exclusions"),
    )
    if predictions.empty or not predictions.status.eq("EVALUATED").any():
        return {
            "outcome": "DATA_LIMITED",
            "metrics": {},
            "limitations": ["Insufficient training/evaluation coverage under frozen split"],
            "artifacts": artifacts,
        }
    scored = predictions[predictions.status.eq("EVALUATED")]
    validation_end = experiment.get("split", {}).get("validation_end", "2024-12-31")
    final = scored[scored.session > validation_end]
    if final.empty:
        return {
            "outcome": "DATA_LIMITED",
            "metrics": {},
            "limitations": ["No frozen later-period assessment observations"],
            "artifacts": artifacts,
        }
    inference = _infer(
        final.baseline_loss.tolist(), final.candidate_loss.tolist(), experiment, "loss"
    )
    artifacts["session_outcomes"] = _write(final, directory, "session_outcomes")
    plan = experiment.get("inference", {})
    robust = robustness(
        final.baseline_loss.tolist(),
        final.candidate_loss.tolist(),
        {
            "block_lengths": plan.get("robustness_block_lengths", [1, 5, 10]),
            "repetitions": plan.get("bootstrap_samples", 999),
            "seed": experiment.get("seed", 17),
            "practical_effect": plan.get("practical_effect", 0.01),
        },
    )
    from .replication import replicate_exp001

    replication = replicate_exp001(frame, dataset, experiment, features, predictions)
    return {
        "outcome": inference["outcome"],
        "definition": EXP001_DEFINITION,
        "metrics": {
            "baseline_mae_bp": float(final.baseline_loss.mean()),
            "candidate_mae_bp": float(final.candidate_loss.mean()),
            "control_mae_bp": float(final.control_loss.mean()),
            "n_sessions": len(final),
            "eligible_sessions": len(ledger),
            "missing_sessions": int(ledger.status.ne("ELIGIBLE").sum()),
            "validation_n": int((scored.session <= validation_end).sum()),
        },
        "inference": inference,
        "session_estimates": final[["session", "baseline_loss", "candidate_loss"]].to_dict(
            "records"
        ),
        "artifacts": artifacts,
        "robustness": robust,
        "replication": replication,
        "limitations": [
            "Spot prediction is not four-leg profitability, a causal claim, or validation of the live HF gate",
            "All previously exposed history remains exploratory",
        ],
    }


def _model_quotes(frame: pd.DataFrame, dataset: dict[str, Any]) -> pd.DataFrame:
    meta = metadata(dataset)
    contracts = meta.get("contracts", [])
    if not contracts or not {"spot", "iv"} <= set(frame):
        raise DataQualificationError(
            "model path requires explicit contracts, spot and physical/scenario IV path"
        )
    from scipy.special import ndtr

    rows = []
    rate = float(meta.get("risk_free_rate", 0))
    for row in frame.to_dict("records"):
        for contract in contracts:
            expiry = pd.Timestamp(f"{contract['expiry']} 15:30:00", tz="Asia/Kolkata").tz_convert(
                "UTC"
            )
            tau = max((expiry - row["event_at"]).total_seconds() / (365 * 86400), 1e-12)
            sigma, spot, strike = float(row["iv"]), float(row["spot"]), float(contract["strike"])
            if sigma <= 0 or spot <= 0:
                raise DataQualificationError("model volatility and spot must be positive")
            d1 = (math.log(spot / strike) + (rate + sigma * sigma / 2) * tau) / (
                sigma * math.sqrt(tau)
            )
            d2 = d1 - sigma * math.sqrt(tau)
            call = spot * ndtr(d1) - strike * math.exp(-rate * tau) * ndtr(d2)
            mark = (
                call
                if contract["option_type"] == "CE"
                else call - spot + strike * math.exp(-rate * tau)
            )
            spread = float(meta.get("model_spread", 0))
            rows.append(
                {
                    **row,
                    **contract,
                    "bid": max(float(mark) - spread / 2, 0.000001),
                    "ask": max(float(mark) + spread / 2, 0.000001),
                    "bid_size": int(meta.get("assumed_size_units", 100000)),
                    "ask_size": int(meta.get("assumed_size_units", 100000)),
                }
            )
    return pd.DataFrame(rows)


class _Book:
    def __init__(self, frame: pd.DataFrame, params: dict[str, Any]):
        self.frame, self.params = frame, params
        self.consumed: dict[tuple[str, str, str], int] = {}

    def at(self, instant: pd.Timestamp, contracts: list[str] | None = None) -> pd.DataFrame:
        rows = self.frame[self.frame.available_at <= instant]
        if contracts:
            rows = rows[rows.contract_id.isin(contracts)]
        rows = rows.sort_values("available_at").drop_duplicates("contract_id", keep="last")
        max_age = float(self.params.get("max_quote_age_seconds", 60))
        rows = rows[(instant - rows.event_at).dt.total_seconds() <= max_age]
        if contracts and set(rows.contract_id) != set(contracts):
            raise DataQualificationError("missing/stale contract in chain")
        if rows.empty:
            raise DataQualificationError("empty eligible chain")
        skew = (rows.event_at.max() - rows.event_at.min()).total_seconds()
        if skew > float(self.params.get("max_chain_skew_seconds", 2)):
            raise DataQualificationError("cross-leg synchronization failed")
        return rows

    def execute(
        self,
        account: Account,
        orders: list[tuple[Contract, int]],
        instant: pd.Timestamp,
        fees: list[dict[str, Any]],
        reason: str,
        cycle: str,
    ) -> tuple[bool, pd.Timestamp]:
        latency = float(self.params.get("latency_seconds", 0))
        spacing = float(self.params.get("leg_spacing_seconds", 0))
        max_wait = float(self.params.get("max_fill_wait_seconds", 60))
        all_filled = True
        latest = instant
        for index, (contract, desired) in enumerate(orders):
            target = instant + pd.Timedelta(seconds=latency + index * spacing)
            available = self.frame[
                self.frame.contract_id.eq(contract.contract_id)
                & (self.frame.available_at >= target)
                & (self.frame.available_at <= target + pd.Timedelta(seconds=max_wait))
            ]
            if available.empty:
                all_filled = False
                break
            row = available.sort_values("available_at").iloc[0]
            latest = max(latest, row.available_at)
            if (row.available_at - row.event_at).total_seconds() > float(
                self.params.get("max_quote_age_seconds", 60)
            ):
                all_filled = False
                break
            side = "ask" if desired > 0 else "bid"
            key = (contract.contract_id, row.event_at.isoformat(), side)
            remaining_size = max(0, int(row[side + "_size"]) - self.consumed.get(key, 0))
            # Contract-unit fills, never lot multiplication here. Partial units
            # remain real inventory and are unwound under the abort policy.
            quantity = min(abs(desired), remaining_size)
            if quantity == 0:
                all_filled = False
                break
            self.consumed[key] = self.consumed.get(key, 0) + quantity
            signed = quantity if desired > 0 else -quantity
            price = float(row[side]) + (1 if signed > 0 else -1) * float(
                self.params.get("slippage_points", 0)
            )
            price = max(0.0, price)
            charge = fee_for_fill(fees, row.available_at.isoformat(), signed, price)
            if signed > 0 and account.cash - signed * price - charge + float(
                self.params.get("available_capital_inr", float("inf"))
            ) < float(self.params.get("reserve_inr", 0)):
                all_filled = False
                break
            account.fill(
                contract, signed, price, charge, row.available_at.isoformat(), reason, cycle
            )
            all_filled &= quantity == abs(desired)
            if quantity != abs(desired):
                break  # partial protective fills never authorize the next short
        return all_filled, latest


def _orders_to_close(
    account: Account, contracts: dict[str, Contract]
) -> list[tuple[Contract, int]]:
    # Cover short risk before disposing of protective longs.
    return [
        (contracts[k], -q)
        for k, q in sorted(account.inventory.items(), key=lambda item: (item[1] > 0, item[0]))
        if q
    ]


def _holding_marks(
    book: _Book, account: Account, origin: pd.Timestamp, latest: pd.Timestamp, cycle: str
) -> list[dict[str, Any]]:
    """Replay signed fills through each observed clock, preserving missing marks."""
    if not account.fills:
        return []
    clocks = sorted(
        set(
            book.frame.loc[
                (book.frame.available_at >= origin) & (book.frame.available_at <= latest),
                "available_at",
            ]
        )
        | {pd.Timestamp(f["timestamp"]) for f in account.fills}
    )
    events = sorted(account.fills, key=lambda f: (f["timestamp"], f["fill_id"]))
    cursor, cash, inventory = 0, 0.0, {}
    marks = []
    for timestamp in clocks:
        while cursor < len(events) and pd.Timestamp(events[cursor]["timestamp"]) <= timestamp:
            event = events[cursor]
            cash += event["cashflow"]
            key = event["contract_id"]
            inventory[key] = inventory.get(key, 0) + event["units"]
            cursor += 1
        active = [key for key, qty in inventory.items() if qty]
        equity, reason = cash, ""
        if active:
            try:
                quotes = book.at(timestamp, active).set_index("contract_id")
                for key in active:
                    qty = inventory[key]
                    equity += qty * float(quotes.loc[key, "bid" if qty > 0 else "ask"])
            except DataQualificationError as exc:
                equity, reason = None, str(exc)
        marks.append(
            {
                "timestamp": timestamp.isoformat(),
                "cash": cash,
                "inventory": dict(inventory),
                "liquidation_equity_inr": equity,
                "mark_unknown_reason": reason,
                "cycle_id": cycle,
                "kind": "holding_mark",
            }
        )
    return marks


def _simulate_policy(
    frame: pd.DataFrame,
    dataset: dict[str, Any],
    params: dict[str, Any],
    policy: str,
    baseline_id: str,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    meta = metadata(dataset)
    fees, specs = meta.get("fee_schedule"), meta.get("contract_specs")
    if not fees or not specs:
        raise DataQualificationError(
            "effective fee schedule and contract-lot specifications required"
        )
    capital = params.get("capital_inr")
    margin = params.get("margin_per_cycle_inr")
    if capital is None or margin is None or float(capital) <= 0 or float(margin) <= 0:
        raise DataQualificationError(
            "positive declared capital and margin/proxy requirement needed; expiry max loss is not margin"
        )
    if not params.get("margin_basis"):
        raise DataQualificationError("historical margin or explicit proxy basis must be labelled")
    opportunities = params.get("opportunities")
    if opportunities is None:
        opportunities = [
            {"session": d, "entry": params.get("entry_time", "10:00:00")}
            for d in sorted(set(frame.session) | set(dataset.get("session_dates", [])))
        ]
    book = _Book(frame, params)
    output, all_fills, all_paths = [], [], []
    cumulative = 0.0
    blocked_until: pd.Timestamp | None = None
    for index, opportunity in enumerate(
        sorted(opportunities, key=lambda x: (x["session"], x.get("entry", "10:00:00")))
    ):
        session = opportunity["session"]
        origin = pd.Timestamp(
            f"{session} {opportunity.get('entry', '10:00:00')}", tz="Asia/Kolkata"
        ).tz_convert("UTC")
        cycle = str(opportunity.get("id", f"cycle-{index}"))
        exit_at = origin + pd.Timedelta(minutes=float(params.get("hold_minutes", 30)))
        deadline = pd.Timestamp(f"{session} 15:00:00", tz="Asia/Kolkata").tz_convert("UTC")
        exit_at = min(exit_at, deadline)
        record = {
            "session": session,
            "opportunity_id": cycle,
            "policy": policy,
            "status": "SKIPPED",
            "reason": "",
            "pnl_inr": 0.0,
            "entry_at": origin.isoformat(),
            "exit_at": exit_at.isoformat(),
            "turnover": 0.0,
            "fees": 0.0,
            "exposure_seconds": 0.0,
        }
        if origin >= deadline or (blocked_until is not None and origin < blocked_until):
            record["reason"] = "deadline_or_overlapping_exposure"
            output.append(record)
            continue
        reserve = float(params.get("reserve_inr", 1000 if baseline_id == "B-policy" else 0))
        if float(capital) + cumulative < float(margin) + reserve:
            record["reason"] = "capital_or_peak_margin"
            output.append(record)
            continue
        packet = {
            **meta.get("policy_packets", {}).get(session, {}),
            "decision_at": origin.isoformat(),
            "held": False,
        }
        decision = policy_decision(packet, baseline_id)
        if decision["action"] not in {"ENTRY", "CANDIDATES"}:
            record["reason"] = decision.get(
                "reason", decision.get("terminal_gate", "baseline_gate")
            )
            output.append(record)
            continue
        try:
            chain = book.at(origin)
            if "spot" not in chain:
                raise DataQualificationError("observable spot required for centre selection")
            if chain.spot.max() - chain.spot.min() > float(
                params.get("max_spot_disagreement", 0.01)
            ):
                raise DataQualificationError("incoherent contemporaneous spot references")
            legs = select_b0(
                chain,
                spot=float(chain.spot.iloc[0]),
                session=session,
                width_floor=float(params.get("width_floor", 500)),
                lots=int(params.get("lots", 1)),
                expiry=params.get("expiry"),
            )
            for contract, _ in legs:
                dated_spec(contract, session, specs)
            book.at(origin, [c.contract_id for c, _ in legs])
        except (ValueError, DataQualificationError) as exc:
            record.update(reason=str(exc), status="INELIGIBLE_ENTRY")
            output.append(record)
            continue
        account = Account()
        book.params["available_capital_inr"] = float(capital) + cumulative
        contracts = {c.contract_id: c for c, _ in legs}
        entry_orders = sorted(legs, key=lambda item: (item[1] < 0, item[0].contract_id))
        filled, entry_completed = book.execute(account, entry_orders, origin, fees, "entry", cycle)
        record["status"] = "COMPLETED"
        if not filled:
            _, latest = book.execute(
                account,
                _orders_to_close(account, contracts),
                entry_completed + pd.Timedelta(microseconds=1),
                fees,
                "abort_partial_entry",
                cycle,
            )
            record.update(
                status="ABORTED_ENTRY" if account.flat else "UNRESOLVED_EXIT",
                reason="partial_entry_unwound"
                if account.flat
                else "partial_entry_unwind_unavailable",
            )
        else:
            trigger = origin + pd.Timedelta(
                minutes=float(params.get("management_after_minutes", 15))
            )
            latest = entry_completed
            if policy in {"close", "recenter"} and trigger < exit_at:
                closed, latest = book.execute(
                    account,
                    _orders_to_close(account, contracts),
                    trigger,
                    fees,
                    "management_close",
                    cycle,
                )
                if not closed or not account.flat:
                    record.update(
                        status="UNRESOLVED_EXIT", reason="management_exit_missing_or_partial"
                    )
                elif policy == "recenter":
                    # Sequential old-close/new-open, no invented overlapping margin relief.
                    reopen = latest + pd.Timedelta(microseconds=1)
                    try:
                        chain2 = book.at(reopen)
                        replacement = select_b0(
                            chain2,
                            spot=float(chain2.spot.iloc[0]),
                            session=session,
                            width_floor=float(params.get("width_floor", 500)),
                            lots=int(params.get("lots", 1)),
                            expiry=params.get("expiry"),
                        )
                        for contract, _ in replacement:
                            dated_spec(contract, session, specs)
                            contracts[contract.contract_id] = contract
                        if float(capital) + cumulative + account.cash < float(margin) + reserve:
                            record["reason"] = "recenter_capital_blocked_after_close"
                        else:
                            ok, latest = book.execute(
                                account,
                                sorted(replacement, key=lambda item: item[1] < 0),
                                reopen,
                                fees,
                                "recenter_entry",
                                cycle,
                            )
                            if not ok:
                                record["reason"] = "partial_recenter_entry"
                    except (ValueError, DataQualificationError) as exc:
                        record["reason"] = f"replacement_ineligible:{exc}"
            if not account.flat and record["status"] != "UNRESOLVED_EXIT":
                closed, latest = book.execute(
                    account,
                    _orders_to_close(account, contracts),
                    exit_at,
                    fees,
                    "scheduled_exit",
                    cycle,
                )
                if not closed or not account.flat or latest > deadline:
                    record.update(status="UNRESOLVED_EXIT", reason="missing_partial_or_late_exit")
        reconciliation = account.reconcile()
        if not reconciliation["valid"]:
            raise ValueError("cash/inventory reconciliation failed")
        if record["status"] == "UNRESOLVED_EXIT":
            record["pnl_inr"] = None
            blocked_until = pd.Timestamp.max.tz_localize("UTC")
        else:
            record["pnl_inr"] = account.cash
            cumulative += account.cash
            blocked_until = latest
        record.update(
            turnover=sum(abs(x["units"]) * x["price"] for x in account.fills),
            fees=sum(x["fees"] for x in account.fills),
            exposure_seconds=max(0.0, (latest - origin).total_seconds()),
            cash_residual=reconciliation["cash_residual"],
            unclosed_units=sum(abs(q) for q in account.inventory.values()),
        )
        all_fills += [{**f, "policy": policy, "session": session} for f in account.fills]
        all_paths += [
            {**p, "policy": policy, "inventory": json.dumps(p["inventory"], sort_keys=True)}
            for p in account.paths + _holding_marks(book, account, origin, latest, cycle)
        ]
        output.append(record)
    return pd.DataFrame(output), pd.DataFrame(all_fills), pd.DataFrame(all_paths)


def _ironfly(
    experiment: dict[str, Any], dataset: dict[str, Any], frame: pd.DataFrame, directory: Path
) -> dict[str, Any]:
    params = {**experiment.get("parameters", {}), **experiment.get("dsl", {})}
    if dataset.get("kind") == "model":
        frame = _model_quotes(frame, dataset)
    elif dataset.get("kind") == "option_bars":
        if params.get("bar_fill") != "available_close_adverse_spread":
            raise DataQualificationError(
                "F2 requires registered available_close_adverse_spread fill assumption"
            )
        if params.get("assumed_spread_points") is None or params.get("assumed_size_units") is None:
            raise DataQualificationError(
                "bar spread and size are unknown without explicit assumptions"
            )
        half = float(params["assumed_spread_points"]) / 2
        frame = frame.copy()
        frame["bid"] = np.maximum(frame.close - half, 0)
        frame["ask"] = frame.close + half
        frame["bid_size"] = frame["ask_size"] = int(params["assumed_size_units"])
    if not {"bid", "ask", "bid_size", "ask_size", "contract_id"} <= set(frame):
        raise DataQualificationError(
            "four-leg evaluator requires identified quote/model/bar price paths"
        )
    meta = metadata(dataset)
    try:
        if not meta.get("fee_schedule") or not meta.get("contract_specs"):
            raise ValueError("effective fees and contract specifications missing")
        for session in sorted(frame.session.unique()):
            fee_for_fill(meta["fee_schedule"], f"{session}T10:00:00+05:30", 1, 0)
        for row in (
            frame[
                [
                    "session",
                    "contract_id",
                    "underlying",
                    "expiry",
                    "strike",
                    "option_type",
                    "lot_size",
                ]
            ]
            .drop_duplicates()
            .to_dict("records")
        ):
            contract = Contract(
                row["contract_id"],
                row["underlying"],
                row["expiry"],
                row["strike"],
                row["option_type"],
                int(row["lot_size"]),
            )
            dated_spec(contract, row["session"], meta["contract_specs"])
    except ValueError as exc:
        raise DataQualificationError(str(exc)) from exc
    if params.get("stop_points") is not None:
        raise DataQualificationError(
            "intrabar stop trigger ordering is unobservable; use registered review-time policy primitives"
        )
    management = params.get("management", "hold")
    if management not in {"hold", "close", "recenter"}:
        raise ValueError("unregistered management primitive")
    policies = list(
        dict.fromkeys(
            ["hold", "close", "recenter"] if management == "recenter" else ["hold", management]
        )
    )
    ledgers, fills, paths = [], [], []
    for policy in policies:
        rows, execution, path = _simulate_policy(
            frame, dataset, params, policy, experiment.get("baseline_id", "B0-simple")
        )
        ledgers.append(rows)
        fills.append(execution)
        paths.append(path)
    opportunities = pd.concat(ledgers, ignore_index=True)
    executions = pd.concat(fills, ignore_index=True)
    inventory = pd.concat(paths, ignore_index=True)
    baseline = opportunities[opportunities.policy.eq("hold")].set_index("opportunity_id")
    candidate = opportunities[opportunities.policy.eq(management)].set_index("opportunity_id")
    if set(baseline.index) != set(candidate.index):
        raise ValueError("comparison opportunity sets differ")
    combined = (
        baseline[["session", "pnl_inr"]]
        .rename(columns={"pnl_inr": "baseline_pnl"})
        .join(candidate[["pnl_inr"]].rename(columns={"pnl_inr": "candidate_pnl"}))
    )
    sessions = (
        combined.groupby("session", sort=True)
        .agg(
            baseline_pnl=("baseline_pnl", lambda x: x.sum(min_count=len(x))),
            candidate_pnl=("candidate_pnl", lambda x: x.sum(min_count=len(x))),
        )
        .reset_index()
    )
    artifacts = {
        "opportunities": _write(opportunities, directory, "opportunities"),
        "fills": _write(executions, directory, "fills"),
        "paths": _write(inventory, directory, "paths"),
        "session_outcomes": _write(sessions, directory, "session_outcomes"),
        "exclusions": _write(
            opportunities[opportunities.status.ne("COMPLETED")], directory, "exclusions"
        ),
    }
    from .replication import replicate_accounting

    replication = replicate_accounting(executions, opportunities)
    metrics = {
        "n_sessions": len(sessions),
        "opportunities": len(baseline),
        "unresolved_opportunities": int(opportunities.pnl_inr.isna().sum()),
        "fees_inr": float(executions.fees.sum()) if len(executions) else 0.0,
        "net_pnl_currency": "INR",
    }
    limitations = [
        "Counterfactual fills assume displayed liquidity is available; no market impact reconstruction",
        f"Capital requirement basis: {params.get('margin_basis')}",
        "Session-level inference, not individual legs or overlapping trades",
    ]
    if sessions.empty or sessions[["baseline_pnl", "candidate_pnl"]].isna().any().any():
        return {
            "outcome": "DATA_LIMITED",
            "metrics": metrics,
            "artifacts": artifacts,
            "replication": replication,
            "limitations": limitations
            + [
                "Missing exits remain unresolved; aggregate P&L and inference withheld, not complete-case selected"
            ],
            "inference": None,
        }
    inference = _infer(
        sessions.baseline_pnl.tolist(), sessions.candidate_pnl.tolist(), experiment, "pnl"
    )
    metrics.update(
        baseline_mean_pnl_inr=float(sessions.baseline_pnl.mean()),
        candidate_mean_pnl_inr=float(sessions.candidate_pnl.mean()),
        candidate_worst_session_inr=float(sessions.candidate_pnl.min()),
        candidate_turnover_inr=float(candidate.turnover.sum()),
        candidate_exposure_seconds=float(candidate.exposure_seconds.sum()),
        candidate_executed_cycles=int(candidate.status.isin(["COMPLETED", "ABORTED_ENTRY"]).sum()),
        candidate_rejection_rate=float(
            candidate.status.isin(["SKIPPED", "INELIGIBLE_ENTRY"]).mean()
        ),
    )
    plan = experiment.get("inference", {})
    robust = robustness(
        sessions.baseline_pnl.tolist(),
        sessions.candidate_pnl.tolist(),
        {
            "block_lengths": plan.get("robustness_block_lengths", [1, 5, 10]),
            "repetitions": plan.get("bootstrap_samples", 999),
            "seed": experiment.get("seed", 17),
            "practical_effect": plan.get("practical_effect", 0.01),
            "relative": False,
        },
        metric="pnl",
    )
    candidate_fill_count = int(executions.policy.eq(management).sum()) if len(executions) else 0
    robust["cost_stress"] = {
        "additional_rupees_per_fill": [1, 5],
        "candidate_net_total": {
            str(extra): float(candidate.pnl_inr.sum() - extra * candidate_fill_count)
            for extra in [1, 5]
        },
        "registered": "cost_stress" in experiment.get("robustness", ["cost_stress"]),
    }
    return {
        "outcome": inference["outcome"],
        "metrics": metrics,
        "inference": inference,
        "artifacts": artifacts,
        "session_estimates": sessions.to_dict("records"),
        "replication": replication,
        "robustness": robust,
        "limitations": limitations,
    }


def _controlled(
    experiment: dict[str, Any], dataset: dict[str, Any], directory: Path
) -> dict[str, Any]:
    if dataset.get("provenance") != "SYNTHETIC" or dataset.get("fidelity") != "F0":
        raise DataQualificationError("controlled benchmark must remain SYNTHETIC/F0")
    params = {**metadata(dataset), **experiment.get("parameters", {})}
    n = int(params.get("n_sessions", 48))
    if not 5 <= n <= 10000:
        raise ValueError("controlled fixture size outside bound")
    rng = np.random.default_rng(int(experiment.get("seed", 17)))
    effect = float(params.get("effect", 0))
    noise = rng.normal(0, float(params.get("noise", 0.1)), n)
    baseline = np.full(n, 1.0)
    candidate = baseline - effect + noise
    rows = pd.DataFrame(
        {
            "session": pd.date_range("2020-01-01", periods=n, freq="B").strftime("%Y-%m-%d"),
            "baseline_loss": baseline,
            "candidate_loss": candidate,
        }
    )
    inference = _infer(baseline.tolist(), candidate.tolist(), experiment, "loss")
    artifact = _write(rows, directory, "session_outcomes")
    from .replication import replicate_controlled

    return {
        "outcome": inference["outcome"],
        "metrics": {
            "n_sessions": n,
            "baseline_mean": float(baseline.mean()),
            "candidate_mean": float(candidate.mean()),
            "known_effect": effect,
        },
        "inference": inference,
        "session_estimates": rows.to_dict("records"),
        "artifacts": {
            "opportunities": artifact,
            "session_outcomes": artifact,
            "exclusions": _write(rows.iloc[:0], directory, "exclusions"),
        },
        "replication": replicate_controlled(rows, inference["estimate"]),
        "robustness": {"known_truth": effect, "predefined_seed": experiment.get("seed", 17)},
        "limitations": ["Controlled synthetic benchmark, not historical strategy evidence"],
    }


def evaluate(
    experiment: dict[str, Any], dataset: dict[str, Any], output_dir: Path
) -> dict[str, Any]:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    evaluator = experiment.get("evaluator", experiment.get("dsl", {}).get("evaluator"))
    try:
        if dataset.get("fidelity") == "F4":
            raise DataQualificationError(
                "F4 depth/event fill replay is explicitly unsupported in this release"
            )
        if experiment.get("fidelity", dataset.get("fidelity")) != dataset.get("fidelity"):
            raise DataQualificationError(
                "requested fidelity differs from certified dataset ceiling"
            )
        if evaluator == "controlled":
            result = _controlled(experiment, dataset, output_dir)
        else:
            report = qualify_dataset(dataset)
            if report["status"] != "PASS":
                raise DataQualificationError("; ".join(report["errors"]))
            frame = load_dataset(dataset)
            if evaluator == "exp001":
                result = _exp001(experiment, dataset, frame, output_dir)
            elif evaluator == "iron_butterfly":
                result = _ironfly(experiment, dataset, frame, output_dir)
            else:
                raise ValueError("unknown protected evaluator")
        result.update(
            fidelity=dataset.get("fidelity"),
            provenance=dataset.get("provenance"),
            evaluator_version="1",
        )
        if result.get("replication", {}).get("status") == "FAIL":
            result["outcome"] = "INVALID_RESULT"
        # JSON roundtrip rejects NaN and external path objects at the worker boundary.
        return json.loads(json.dumps(result, allow_nan=False))
    except DataQualificationError as exc:
        return {
            "outcome": "DATA_LIMITED",
            "fidelity": dataset.get("fidelity"),
            "provenance": dataset.get("provenance"),
            "evaluator_version": "1",
            "metrics": {},
            "artifacts": {},
            "limitations": [str(exc)],
            "replication": {
                "status": "NOT_APPLICABLE",
                "reason": "data qualification failed before economics",
            },
        }
