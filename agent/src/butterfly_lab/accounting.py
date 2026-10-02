"""Pure signed-unit accounting; independent of operational ledgers/broker APIs."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any


@dataclass(frozen=True)
class Contract:
    contract_id: str
    underlying: str
    expiry: str
    strike: float
    option_type: str
    lot_size: int


def validate_iron_butterfly(legs: list[tuple[Contract, int]]) -> None:
    if len(legs) != 4 or len({c.contract_id for c, _ in legs}) != 4:
        raise ValueError("four distinct contracts required")
    if len({(c.underlying, c.expiry) for c, _ in legs}) != 1:
        raise ValueError("one underlying and expiry required")
    if len({abs(q) for _, q in legs}) != 1 or any(q == 0 for _, q in legs):
        raise ValueError("matched nonzero signed units required")
    if any(abs(q) % c.lot_size or c.lot_size <= 0 for c, q in legs):
        raise ValueError("units must match effective contract lots")
    by = {(c.option_type, 1 if q > 0 else -1): c for c, q in legs}
    if set(by) != {("PE", 1), ("PE", -1), ("CE", -1), ("CE", 1)}:
        raise ValueError("protective wings and short body required")
    if not (by["PE", 1].strike < by["PE", -1].strike == by["CE", -1].strike < by["CE", 1].strike):
        raise ValueError("iron butterfly strike geometry violated")


def dated_spec(contract: Contract, session: str, specifications: list[dict[str, Any]]) -> int:
    matches = [
        x
        for x in specifications
        if x.get("contract_id", contract.contract_id) == contract.contract_id
        and x.get("underlying", contract.underlying) == contract.underlying
        and x["effective_from"] <= session <= x.get("effective_to", "9999-12-31")
    ]
    if len(matches) != 1:
        raise ValueError("exactly one effective-dated lot specification required")
    if matches[0].get("known_at", session)[:10] > session:
        raise ValueError("contract specification unavailable at decision")
    units = int(matches[0]["lot_size"])
    if units <= 0 or units != contract.lot_size:
        raise ValueError("observed lot differs from dated specification")
    return units


def fee_for_fill(
    schedule: list[dict[str, Any]],
    timestamp: str,
    signed_units: int,
    price: float,
    *,
    exercise: bool = False,
) -> float:
    session = (
        datetime.fromisoformat(timestamp)
        .astimezone(__import__("zoneinfo").ZoneInfo("Asia/Kolkata"))
        .date()
        .isoformat()
    )
    matches = [
        x for x in schedule if x["effective_from"] <= session <= x.get("effective_to", "9999-12-31")
    ]
    if len(matches) != 1:
        raise ValueError("missing or overlapping effective fee schedule; unknown is not zero")
    band = matches[0]
    required = {
        "brokerage_per_fill",
        "exchange_rate",
        "regulatory_rate",
        "gst_rate",
        "sell_tax_rate",
        "buy_stamp_rate",
    }
    if not required <= band.keys() or any(band[x] is None or float(band[x]) < 0 for x in required):
        raise ValueError("complete nonnegative fee components required")
    value = abs(signed_units) * price
    service = float(band["brokerage_per_fill"]) + value * (
        float(band["exchange_rate"]) + float(band["regulatory_rate"])
    )
    tax = value * (
        float(band["sell_tax_rate"]) if signed_units < 0 else float(band["buy_stamp_rate"])
    )
    if exercise:
        if "exercise_tax_rate" not in band:
            raise ValueError("exercise fee unknown")
        tax += value * float(band["exercise_tax_rate"])
    total = service * (1 + float(band["gst_rate"])) + tax
    return float(Decimal(str(total)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


@dataclass
class Account:
    cash: float = 0.0
    inventory: dict[str, int] = field(default_factory=dict)
    fills: list[dict[str, Any]] = field(default_factory=list)
    paths: list[dict[str, Any]] = field(default_factory=list)

    def fill(
        self,
        contract: Contract,
        units: int,
        price: float,
        fees: float | None,
        timestamp: str,
        reason: str,
        cycle_id: str,
    ) -> None:
        if fees is None:
            raise ValueError("fees unknown; cannot silently replace with zero")
        if not isinstance(units, int) or units == 0 or price < 0 or fees < 0:
            raise ValueError("invalid fill")
        clock = datetime.fromisoformat(timestamp)
        if clock.tzinfo is None:
            raise ValueError("offset-aware fill time required")
        if self.fills and clock < datetime.fromisoformat(self.fills[-1]["timestamp"]):
            raise ValueError("dependent fill chronology cannot move backwards")
        self.cash += -units * price - fees
        self.inventory[contract.contract_id] = self.inventory.get(contract.contract_id, 0) + units
        self.fills.append(
            {
                "fill_id": len(self.fills) + 1,
                "contract_id": contract.contract_id,
                "units": units,
                "price": price,
                "fees": fees,
                "cashflow": -units * price - fees,
                "timestamp": timestamp,
                "reason": reason,
                "cycle_id": cycle_id,
                "currency": "INR",
            }
        )
        self.paths.append(
            {
                "timestamp": timestamp,
                "cash": self.cash,
                "inventory": dict(self.inventory),
                "cycle_id": cycle_id,
            }
        )

    def equity(self, quotes: dict[str, dict[str, float]]) -> float | None:
        total = self.cash
        for key, units in self.inventory.items():
            if units:
                if key not in quotes or quotes[key].get("bid" if units > 0 else "ask") is None:
                    return None
                total += units * quotes[key]["bid" if units > 0 else "ask"]
        return total

    @property
    def flat(self) -> bool:
        return all(q == 0 for q in self.inventory.values())

    def reconcile(self) -> dict[str, Any]:
        cash = sum(-f["units"] * f["price"] - f["fees"] for f in self.fills)
        reconstructed: dict[str, int] = {}
        for fill in self.fills:
            k = fill["contract_id"]
            reconstructed[k] = reconstructed.get(k, 0) + fill["units"]
        ok = reconstructed == self.inventory and abs(cash - self.cash) < 1e-7
        return {
            "valid": ok,
            "cash_residual": cash - self.cash,
            "inventory_matches": reconstructed == self.inventory,
            "flat": self.flat,
            "net_pnl": self.cash if self.flat else None,
            "unknown_reason": None if self.flat else "unclosed_inventory",
        }


def expiry_payoff(legs: list[tuple[Contract, int]], spot: float, entry_cash: float) -> float:
    """Fixture invariant only; never used as a replacement for an intraday exit."""
    return entry_cash + sum(
        q * max(spot - c.strike if c.option_type == "CE" else c.strike - spot, 0) for c, q in legs
    )
