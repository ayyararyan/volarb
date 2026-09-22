#!/usr/bin/env python3
"""Fetch and normalize the official NSE option-chain JSON feed.

Primary flow (current NSE site):
  0. Prefer curl_cffi Chrome TLS/HTTP2 impersonation when available.
  1. GET /option-chain to establish the browser/Akamai cookie session.
  2. GET /api/option-chain-contract-info?symbol=... to resolve valid expiries.
  3. GET /api/option-chain-v3?type=Indices|Equity&symbol=...&expiry=DD-MMM-YYYY.
  4. If NSE returns 401/403, an HTML challenge, or empty JSON, refresh the
     session cookies once and retry.
  5. Fall back to the older option-chain-indices/equities endpoint only if
     the v3 endpoint is unavailable.

The script intentionally emits a compact, stable schema for downstream
butterfly analysis instead of exposing NSE's raw response shape.
"""

from __future__ import annotations

import argparse
import datetime as dt
import gzip
import http.cookiejar
import json
import math
import sys
import urllib.error
import urllib.parse
import urllib.request
import zlib
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

BASE_URL = "https://www.nseindia.com"
OPTION_CHAIN_PAGE = f"{BASE_URL}/option-chain"
ALL_INDICES = f"{BASE_URL}/api/allIndices"
CONTRACT_INFO = f"{BASE_URL}/api/option-chain-contract-info"
V3_ENDPOINT = f"{BASE_URL}/api/option-chain-v3"
LEGACY_INDEX_ENDPOINT = f"{BASE_URL}/api/option-chain-indices"
LEGACY_EQUITY_ENDPOINT = f"{BASE_URL}/api/option-chain-equities"

# Keep this conservative; unknown symbols default to Equity unless overridden.
KNOWN_INDEX_SYMBOLS = {
    "NIFTY",
    "BANKNIFTY",
    "FINNIFTY",
    "MIDCPNIFTY",
    "NIFTYNXT50",
    "NIFTY NEXT 50",
}

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/130.0.0.0 Safari/537.36"
)


class NSEFetchError(RuntimeError):
    pass


class BrowserSession:
    """Browser-like NSE session with optional TLS/browser impersonation.

    `curl_cffi` is preferred when installed because NSE/Akamai can reject clients
    whose TLS/HTTP2 fingerprint does not look like a browser even when cookies and
    HTTP headers are correct. The stdlib urllib path remains as a dependency-free
    fallback for environments where NSE permits it.
    """

    def __init__(self, timeout: float = 10.0, transport: str = "auto"):
        self.timeout = timeout
        self.transport_requested = transport
        self.backend = "urllib"
        self._curl_requests = None
        self._curl_session = None
        self.cookie_jar = None
        self.opener = None

        if transport in ("auto", "curl-cffi"):
            try:
                from curl_cffi import requests as curl_requests  # type: ignore
            except Exception as e:
                if transport == "curl-cffi":
                    raise NSEFetchError(
                        "curl_cffi is not installed; install it or use --transport urllib"
                    ) from e
            else:
                self.backend = "curl-cffi"
                self._curl_requests = curl_requests
                self._new_curl_session()

        if self.backend == "urllib":
            self._new_urllib_session()

    @staticmethod
    def _headers(json_mode: bool = False) -> Dict[str, str]:
        if json_mode:
            accept = "application/json,text/plain,*/*"
        else:
            accept = (
                "text/html,application/xhtml+xml,application/xml;q=0.9,"
                "image/avif,image/webp,*/*;q=0.8"
            )
        return {
            "User-Agent": UA,
            "Accept": accept,
            "Accept-Language": "en-US,en;q=0.9",
            # Avoid brotli so stdlib can always decode the response.
            "Accept-Encoding": "gzip, deflate",
            "Connection": "keep-alive",
            "Referer": OPTION_CHAIN_PAGE,
        }

    @staticmethod
    def _curl_headers(json_mode: bool = False) -> Dict[str, str]:
        # Let curl_cffi supply the browser-matched UA, Accept-Encoding and HTTP2
        # fingerprint. Only add request-context headers here to avoid a TLS/UA mismatch.
        return {
            "Accept": "application/json,text/plain,*/*" if json_mode else "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": OPTION_CHAIN_PAGE,
        }

    def _new_urllib_session(self) -> None:
        self.cookie_jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.cookie_jar)
        )

    def _new_curl_session(self) -> None:
        if self._curl_requests is None:
            raise NSEFetchError("curl_cffi transport is unavailable")
        if self._curl_session is not None:
            try:
                self._curl_session.close()
            except Exception:
                pass
        self._curl_session = self._curl_requests.Session(
            impersonate="chrome",
            timeout=self.timeout,
        )

    def reset(self) -> None:
        if self.backend == "curl-cffi":
            self._new_curl_session()
        else:
            if self.cookie_jar is not None:
                try:
                    self.cookie_jar.clear()
                except Exception:
                    pass
            self._new_urllib_session()

    @staticmethod
    def _decode_body(resp: Any, raw: bytes) -> str:
        enc = (resp.headers.get("Content-Encoding") or "").lower()
        if enc == "gzip":
            raw = gzip.decompress(raw)
        elif enc == "deflate":
            try:
                raw = zlib.decompress(raw)
            except zlib.error:
                raw = zlib.decompress(raw, -zlib.MAX_WBITS)
        charset = resp.headers.get_content_charset() or "utf-8"
        return raw.decode(charset, errors="replace")

    def get_text(self, url: str, json_mode: bool = False) -> Tuple[int, str, str]:
        if self.backend == "curl-cffi":
            try:
                resp = self._curl_session.get(
                    url,
                    headers=self._curl_headers(json_mode=json_mode),
                    timeout=self.timeout,
                    allow_redirects=True,
                )
                return (
                    int(resp.status_code),
                    resp.text or "",
                    str(resp.headers.get("content-type", "")),
                )
            except Exception as e:
                raise NSEFetchError(f"network error fetching NSE with curl_cffi: {e}") from e

        req = urllib.request.Request(url, headers=self._headers(json_mode=json_mode))
        try:
            with self.opener.open(req, timeout=self.timeout) as resp:
                raw = resp.read()
                text = self._decode_body(resp, raw)
                return int(resp.status), text, resp.headers.get("Content-Type", "")
        except urllib.error.HTTPError as e:
            raw = e.read() if hasattr(e, "read") else b""
            try:
                text = raw.decode("utf-8", errors="replace")
            except Exception:
                text = ""
            return int(e.code), text, e.headers.get("Content-Type", "") if e.headers else ""
        except urllib.error.URLError as e:
            raise NSEFetchError(f"network error fetching NSE: {e}") from e

    def bootstrap(self) -> None:
        status, text, _ = self.get_text(OPTION_CHAIN_PAGE, json_mode=False)
        if status >= 400:
            raise NSEFetchError(f"NSE session bootstrap failed with HTTP {status}")
        if not text:
            raise NSEFetchError("NSE session bootstrap returned an empty page")

        # A light API warm-up helps establish the same cookie/session path used by
        # NSE's frontend. Failure is non-fatal because the option-chain calls below
        # remain the authoritative test.
        if self.backend == "curl-cffi":
            try:
                self.get_text(ALL_INDICES, json_mode=True)
            except NSEFetchError:
                pass

    @staticmethod
    def _looks_like_json(text: str) -> bool:
        stripped = text.lstrip()
        return stripped.startswith("{") or stripped.startswith("[")

    def get_json(self, url: str, *, refresh_on_failure: bool = True) -> Dict[str, Any]:
        attempts = 2 if refresh_on_failure else 1
        last_error = "unknown NSE response"
        for attempt in range(attempts):
            status, text, ctype = self.get_text(url, json_mode=True)
            blocked = status in (401, 403, 404, 429)
            if status < 400 and text and self._looks_like_json(text):
                try:
                    data = json.loads(text)
                except json.JSONDecodeError as e:
                    last_error = f"invalid JSON from NSE: {e}"
                else:
                    if isinstance(data, dict) and data:
                        return data
                    last_error = "NSE returned empty JSON"
            else:
                snippet = " ".join(text[:180].split())
                last_error = (
                    f"HTTP {status}; content-type={ctype or 'unknown'}; "
                    f"body={snippet!r}"
                )

            if attempt + 1 < attempts and (
                blocked or not self._looks_like_json(text) or "text/html" in ctype.lower()
            ):
                # Akamai/NSE sessions expire/challenge frequently. Re-establish a
                # fresh browser-like session instead of hard-coding cookies.
                self.reset()
                self.bootstrap()
                continue
            break
        raise NSEFetchError(last_error)


def make_url(base: str, params: Dict[str, Any]) -> str:
    query = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
    return f"{base}?{query}"


def normalize_expiry(value: str) -> str:
    value = value.strip()
    for fmt in ("%d-%b-%Y", "%Y-%m-%d", "%d-%m-%Y"):
        try:
            parsed = dt.datetime.strptime(value, fmt)
            return parsed.strftime("%d-%b-%Y")
        except ValueError:
            pass
    raise ValueError(
        f"Unsupported expiry {value!r}; use DD-MMM-YYYY, YYYY-MM-DD, or DD-MM-YYYY"
    )


def get_expiry_dates(payload: Dict[str, Any]) -> List[str]:
    candidates: Sequence[Any] = ()
    if isinstance(payload.get("expiryDates"), list):
        candidates = payload["expiryDates"]
    elif isinstance(payload.get("records"), dict) and isinstance(
        payload["records"].get("expiryDates"), list
    ):
        candidates = payload["records"]["expiryDates"]
    elif isinstance(payload.get("data"), dict) and isinstance(
        payload["data"].get("expiryDates"), list
    ):
        candidates = payload["data"]["expiryDates"]
    out = []
    for item in candidates:
        if isinstance(item, str) and item.strip():
            out.append(item.strip())
    return out


def records_container(payload: Dict[str, Any]) -> Dict[str, Any]:
    rec = payload.get("records")
    return rec if isinstance(rec, dict) else {}


def extract_rows(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    paths: Iterable[Any] = (
        payload.get("records", {}).get("data") if isinstance(payload.get("records"), dict) else None,
        payload.get("filtered", {}).get("data") if isinstance(payload.get("filtered"), dict) else None,
        payload.get("data"),
    )
    for candidate in paths:
        if isinstance(candidate, list):
            rows = [x for x in candidate if isinstance(x, dict)]
            if rows:
                return rows
    raise NSEFetchError("NSE JSON did not contain an option-chain row list")


def first_present(mapping: Dict[str, Any], keys: Sequence[str]) -> Any:
    for key in keys:
        if key in mapping and mapping[key] is not None:
            return mapping[key]
    return None


def as_number(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return float(value)
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return number


def normalize_side(side: Any) -> Dict[str, Optional[float]]:
    if not isinstance(side, dict):
        return {}
    mapping = {
        "oi": ("openInterest", "oi", "open_interest"),
        "change_oi": ("changeinOpenInterest", "changeInOpenInterest", "change_oi", "changeInOI"),
        "volume": ("totalTradedVolume", "volume", "tradedVolume"),
        "iv": ("impliedVolatility", "iv", "IV"),
        "ltp": ("lastPrice", "ltp", "last_price"),
        "change": ("change", "priceChange"),
        "bid": ("bidprice", "bidPrice", "bid", "bestBidPrice"),
        "ask": ("askPrice", "askprice", "ask", "bestAskPrice"),
        "bid_qty": ("bidQty", "bidQuantity", "bid_qty", "bestBidQty"),
        "ask_qty": ("askQty", "askQuantity", "ask_qty", "bestAskQty"),
    }
    out: Dict[str, Optional[float]] = {}
    for target, keys in mapping.items():
        value = as_number(first_present(side, keys))
        if value is not None:
            out[target] = value
    return out


def normalize_chain(payload: Dict[str, Any], symbol: str, expiry: str, instrument_type: str) -> Dict[str, Any]:
    rows = extract_rows(payload)
    rec = records_container(payload)
    timestamp = first_present(rec, ("timestamp", "timeStamp", "lastUpdateTime"))
    if timestamp is None:
        timestamp = first_present(payload, ("timestamp", "timeStamp", "lastUpdateTime"))

    underlying = as_number(first_present(rec, ("underlyingValue", "underlying", "spot")))
    normalized: List[Dict[str, Any]] = []

    for row in rows:
        strike = as_number(first_present(row, ("strikePrice", "strike", "strike_price")))
        if strike is None:
            continue
        call_raw = first_present(row, ("CE", "ce", "call", "Call"))
        put_raw = first_present(row, ("PE", "pe", "put", "Put"))
        call = normalize_side(call_raw)
        put = normalize_side(put_raw)
        if underlying is None:
            for side_raw in (call_raw, put_raw):
                if isinstance(side_raw, dict):
                    underlying = as_number(
                        first_present(side_raw, ("underlyingValue", "underlying", "spot"))
                    )
                    if underlying is not None:
                        break
        normalized.append({"strike": strike, "call": call, "put": put})

    if not normalized:
        raise NSEFetchError("NSE JSON contained no usable strike rows")
    normalized.sort(key=lambda x: x["strike"])

    diffs = [
        b["strike"] - a["strike"]
        for a, b in zip(normalized[:-1], normalized[1:])
        if b["strike"] > a["strike"]
    ]
    strike_step = min(diffs) if diffs else None

    return {
        "provider": "NSE India",
        "source": "official NSE option-chain JSON",
        "symbol": symbol,
        "instrument_type": instrument_type,
        "expiry": expiry,
        "nse_timestamp": timestamp,
        "retrieved_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "underlying_value": underlying,
        "strike_step": strike_step,
        "chain": normalized,
    }


def filter_local_window(
    snapshot: Dict[str, Any],
    anchors: Sequence[Optional[float]],
    extra_strikes: int,
) -> Dict[str, Any]:
    usable = [float(x) for x in anchors if x is not None]
    if not usable:
        return snapshot
    chain = snapshot.get("chain") or []
    if not chain:
        return snapshot
    step = snapshot.get("strike_step")
    if not step or step <= 0:
        return snapshot
    lo = min(usable) - max(extra_strikes, 0) * step
    hi = max(usable) + max(extra_strikes, 0) * step
    filtered = [r for r in chain if lo <= float(r["strike"]) <= hi]
    if filtered:
        snapshot = dict(snapshot)
        snapshot["chain"] = filtered
        snapshot["window"] = {"lower": lo, "upper": hi, "extra_strikes": extra_strikes}
    return snapshot


def fetch_chain(
    symbol: str,
    expiry: Optional[str],
    instrument_type: str,
    timeout: float,
    transport: str = "auto",
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    symbol = symbol.strip().upper()
    if instrument_type == "auto":
        instrument_type = "index" if symbol in KNOWN_INDEX_SYMBOLS else "equity"
    nse_type = "Indices" if instrument_type == "index" else "Equity"

    session = BrowserSession(timeout=timeout, transport=transport)
    session.bootstrap()

    contract_url = make_url(CONTRACT_INFO, {"symbol": symbol})
    contract_info: Dict[str, Any] = {}
    expiry_dates: List[str] = []
    try:
        contract_info = session.get_json(contract_url)
        expiry_dates = get_expiry_dates(contract_info)
    except NSEFetchError:
        # An explicit expiry can still be attempted even if contract-info is blocked.
        if not expiry:
            raise

    if expiry:
        expiry = normalize_expiry(expiry)
        if expiry_dates and expiry not in expiry_dates:
            raise NSEFetchError(
                f"Expiry {expiry} is not listed by NSE for {symbol}. "
                f"Nearest advertised expiries: {', '.join(expiry_dates[:5])}"
            )
    else:
        if not expiry_dates:
            raise NSEFetchError(f"Could not resolve an NSE expiry for {symbol}")
        expiry = expiry_dates[0]

    v3_url = make_url(
        V3_ENDPOINT,
        {"type": nse_type, "symbol": symbol, "expiry": expiry},
    )
    endpoint_used = v3_url
    try:
        raw = session.get_json(v3_url)
    except NSEFetchError as v3_error:
        legacy_base = LEGACY_INDEX_ENDPOINT if instrument_type == "index" else LEGACY_EQUITY_ENDPOINT
        legacy_url = make_url(legacy_base, {"symbol": symbol})
        try:
            raw = session.get_json(legacy_url)
            endpoint_used = legacy_url
        except NSEFetchError as legacy_error:
            raise NSEFetchError(
                f"NSE v3 fetch failed ({v3_error}); legacy fallback failed ({legacy_error})"
            ) from legacy_error

    snapshot = normalize_chain(raw, symbol, expiry, instrument_type)
    snapshot["endpoint"] = endpoint_used
    snapshot["transport"] = session.backend
    snapshot["expiry_dates"] = expiry_dates
    return snapshot, raw


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Fetch and normalize the official NSE option chain")
    ap.add_argument("--symbol", required=True, help="NIFTY, BANKNIFTY, RELIANCE, etc.")
    ap.add_argument("--expiry", help="DD-MMM-YYYY, YYYY-MM-DD, or DD-MM-YYYY; defaults to nearest NSE expiry")
    ap.add_argument(
        "--instrument-type",
        choices=("auto", "index", "equity"),
        default="auto",
        help="Override index/equity detection",
    )
    ap.add_argument("--lower", type=float, help="Butterfly lower wing; used to trim the output window")
    ap.add_argument("--center", type=float, help="Butterfly body/centre; used to trim the output window")
    ap.add_argument("--upper", type=float, help="Butterfly upper wing; used to trim the output window")
    ap.add_argument(
        "--extra-strikes",
        type=int,
        default=5,
        help="How many strikes beyond the supplied anchors to retain (default: 5)",
    )
    ap.add_argument("--timeout", type=float, default=10.0)
    ap.add_argument(
        "--transport",
        choices=("auto", "curl-cffi", "urllib"),
        default="auto",
        help="HTTP transport. auto prefers curl_cffi Chrome impersonation when installed.",
    )
    ap.add_argument("--output", help="Write normalized JSON to this path instead of stdout")
    ap.add_argument("--raw-output", help="Optionally save the raw NSE JSON for diagnostics")
    ap.add_argument("--pretty", action="store_true")
    return ap.parse_args()


def main() -> int:
    args = parse_args()
    try:
        snapshot, raw = fetch_chain(
            args.symbol,
            args.expiry,
            args.instrument_type,
            args.timeout,
            args.transport,
        )
        snapshot = filter_local_window(
            snapshot,
            (args.lower, args.center, args.upper),
            args.extra_strikes,
        )
    except (NSEFetchError, ValueError) as e:
        print(json.dumps({"ok": False, "error": str(e)}), file=sys.stderr)
        return 2

    text = json.dumps(snapshot, indent=2 if args.pretty else None, sort_keys=True)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(text)
            f.write("\n")
    else:
        print(text)

    if args.raw_output:
        with open(args.raw_output, "w", encoding="utf-8") as f:
            json.dump(raw, f, indent=2 if args.pretty else None, sort_keys=True)
            f.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
