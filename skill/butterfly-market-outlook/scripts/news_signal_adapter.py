#!/usr/bin/env python3
"""Small deterministic adapter for Market News Signal Filter packets.

This module does not classify raw news. It only normalizes the already-classified
child-skill packet for butterfly regime and latency gates.
"""

SEV_ORDER = {"low": 0, "medium": 1, "high": 2, "critical": 3, "unknown": -1}
GAP_ORDER = {"none": 0, "low": 1, "moderate": 2, "high": 3, "extreme": 4, "unknown": -1}
REL_ORDER = {"ignore": 0, "watch": 1, "material": 2, "critical": 3, "unknown": -1}
OVERNIGHT_ORDER = {"none": 0, "low": 1, "moderate": 2, "high": 3, "extreme": 4, "unknown": -1}


def status(packet):
    if not isinstance(packet, dict) or not packet:
        return "UNAVAILABLE"
    value = str(packet.get("status", packet.get("calibration_status", "CURRENT"))).upper()
    return value if value in {"CURRENT", "STALE_CALIBRATION", "UNAVAILABLE", "INVALID"} else "INVALID"


def _max_sev(a, b):
    return a if SEV_ORDER.get(a, -1) >= SEV_ORDER.get(b, -1) else b


def latency_severity(packet):
    """Map a normalized child packet to low/medium/high/critical/unknown."""
    st = status(packet)
    if st in {"UNAVAILABLE", "INVALID"}:
        return "unknown"

    best = str(packet.get("max_latency_severity", "low")).lower()
    if best not in SEV_ORDER:
        best = "low"

    for e in packet.get("events", []) or []:
        if not isinstance(e, dict):
            continue
        if not e.get("inside_untradeable_window", e.get("latency_critical", False)):
            continue
        sev = str(e.get("latency_severity", e.get("severity", "low"))).lower()
        if sev not in SEV_ORDER:
            sev = "low"
        gap = str(e.get("gap_risk", "unknown")).lower()
        rel = str(e.get("butterfly_relevance", "unknown")).lower()
        ov = str(e.get("overnight_relevance", "unknown")).lower()
        if GAP_ORDER.get(gap, -1) >= GAP_ORDER["extreme"] or REL_ORDER.get(rel, -1) >= REL_ORDER["critical"]:
            sev = _max_sev(sev, "critical")
        elif GAP_ORDER.get(gap, -1) >= GAP_ORDER["high"] or REL_ORDER.get(rel, -1) >= REL_ORDER["material"] or OVERNIGHT_ORDER.get(ov, -1) >= OVERNIGHT_ORDER["high"]:
            sev = _max_sev(sev, "high")
        elif GAP_ORDER.get(gap, -1) >= GAP_ORDER["moderate"] or REL_ORDER.get(rel, -1) >= REL_ORDER["watch"]:
            sev = _max_sev(sev, "medium")
        best = _max_sev(best, sev)

    agg = str(packet.get("aggregate_state", "UNKNOWN")).upper()
    max_gap = str(packet.get("max_gap_risk", "unknown")).lower()
    max_rel = str(packet.get("max_butterfly_relevance", "unknown")).lower()
    max_ov = str(packet.get("max_overnight_relevance", "unknown")).lower()
    if agg == "TAIL_RISK_ACTIVE":
        if GAP_ORDER.get(max_gap, -1) >= GAP_ORDER["extreme"] or REL_ORDER.get(max_rel, -1) >= REL_ORDER["critical"]:
            best = _max_sev(best, "critical")
        elif OVERNIGHT_ORDER.get(max_ov, -1) >= OVERNIGHT_ORDER["high"]:
            best = _max_sev(best, "high")
    elif agg == "HIGH_UNCERTAINTY" and OVERNIGHT_ORDER.get(max_ov, -1) >= OVERNIGHT_ORDER["moderate"]:
        best = _max_sev(best, "high")

    return best


def compact(packet):
    if not isinstance(packet, dict):
        packet = {}
    return {
        "status": status(packet),
        "calibration_asof": packet.get("calibration_asof"),
        "aggregate_state": str(packet.get("aggregate_state", "UNKNOWN")).upper(),
        "max_gap_risk": str(packet.get("max_gap_risk", "unknown")).lower(),
        "max_butterfly_relevance": str(packet.get("max_butterfly_relevance", "unknown")).lower(),
        "max_overnight_relevance": str(packet.get("max_overnight_relevance", "unknown")).lower(),
        "max_latency_severity": latency_severity(packet),
        "dominant_channels": list(packet.get("dominant_channels", []) or []),
    }
