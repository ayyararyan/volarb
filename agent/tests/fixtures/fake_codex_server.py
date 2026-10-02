#!/usr/bin/env python3
"""Controlled stdio protocol fixture; never calls a model or reads credentials.

Copy to an executable path; optional <path>.responses.json maps roles to a
payload or list of successive payloads. Basename prefixes select faults.
"""

import json
import os
from pathlib import Path
import sys
import time

if "--version" in sys.argv:
    print("codex-cli 0.149.1")
    raise SystemExit(0)

name = Path(sys.argv[0]).name
scenario = name.split("-", 1)[0]
config = {}
for index, argument in enumerate(sys.argv):
    if argument == "-c":
        key, raw = sys.argv[index + 1].split("=", 1)
        # Fixed controls use plain dotted paths. Quoted MCP names are only
        # needed for the inherited-server scenario below.
        parts = key.split(".")
        target = config
        for part in parts[:-1]:
            target = target.setdefault(part.strip('"'), {})
        target[parts[-1]] = json.loads(raw)
if scenario in {"mcp", "stubbornmcp"}:
    entry = config.setdefault("mcp_servers", {}).setdefault("inherited", {})
    if scenario == "stubbornmcp":
        entry["enabled"] = True
    else:
        entry.setdefault("enabled", True)
if scenario == "unsafe":
    config["features"]["shell_tool"] = True

responses_path = Path(str(Path(sys.argv[0])) + ".responses.json")
responses = json.loads(responses_path.read_text()) if responses_path.exists() else {}
counts = {}
threads = 0
current_thread = None


def send(message):
    print(json.dumps(message), flush=True)


def result(request, value):
    send({"id": request["id"], "result": value})


def event(method, params):
    send({"method": method, "params": params})


def strict_schema(value):
    """Relevant documented strict-output subset, independently checked here."""
    if not isinstance(value, dict):
        return False
    if value.get("type") == "object":
        properties = value.get("properties", {})
        if value.get("additionalProperties") is not False:
            return False
        if set(value.get("required", [])) != set(properties):
            return False
        if not all(strict_schema(child) for child in properties.values()):
            return False
    if "items" in value and not strict_schema(value["items"]):
        return False
    for key in ("$defs", "definitions"):
        if key in value and not all(strict_schema(child) for child in value[key].values()):
            return False
    if "anyOf" in value and not all(strict_schema(child) for child in value["anyOf"]):
        return False
    return True


for line in sys.stdin:
    request = json.loads(line)
    method = request["method"]
    with Path(str(Path(sys.argv[0])) + ".requests.jsonl").open("a") as trace:
        trace.write(json.dumps({"method": method}) + "\n")
    params = request.get("params", {})
    if method == "initialize":
        if scenario == "startup":
            time.sleep(20)
        result(request, {"userAgent": "controlled-fake/0.149.1"})
    elif method == "initialized":
        continue
    elif method == "config/read":
        effective = json.loads(json.dumps(config))
        effective["tools"] = {"web_search": None}  # 0.149.1 ToolsV2 serialization
        result(
            request,
            {
                "config": effective,
                "layers": [
                    {"name": {"type": "sessionFlags"}, "config": config, "version": "fixture"}
                ],
            },
        )
    elif method == "account/read":
        account = None if scenario == "unauthenticated" else {"type": "chatgpt"}
        if scenario == "apikey":
            account = {"type": "apiKey"}
        result(request, {"account": account, "requiresOpenaiAuth": True})
    elif method == "account/rateLimits/read":
        result(
            request,
            {
                "rateLimits": {
                    "primary": {
                        "usedPercent": 1,
                        "windowDurationMins": 300,
                        "resetsAt": 2000000000,
                        "email": "must-not-retain@example.test",
                    },
                    "secondary": None,
                }
            },
        )
    elif method == "model/list":
        result(
            request, {"data": [{"model": "fixture-model", "isDefault": True}], "nextCursor": None}
        )
    elif method == "thread/start":
        threads += 1
        current_thread = f"fixture-thread-{threads}"
        result(
            request,
            {
                "thread": {"id": current_thread, "ephemeral": True},
                "model": "fixture-model",
                "modelProvider": "openai",
                "approvalPolicy": "never",
                "instructionSources": [],
                "sandbox": {"type": "readOnly"},
            },
        )
        if scenario == "stallinput":
            time.sleep(20)
    elif method == "turn/start":
        if not strict_schema(params.get("outputSchema")):
            send(
                {
                    "id": request["id"],
                    "error": {"code": -32602, "message": "unsupported strict output schema"},
                }
            )
            continue
        turn_id = f"fixture-turn-{threads}"
        prompt = json.loads(params["input"][0]["text"])
        role = prompt["role"]
        counts[role] = counts.get(role, 0) + 1
        result(request, {"turn": {"id": turn_id, "status": "inProgress", "items": []}})
        if scenario == "timeout":
            time.sleep(20)
        if scenario == "crash":
            os._exit(3)
        if scenario == "slow":
            time.sleep(0.3)
        scoped = {"threadId": current_thread, "turnId": turn_id}
        if scenario == "tool":
            event(
                "item/started", scoped | {"item": {"id": "forbidden", "type": "commandExecution"}}
            )
            continue
        if scenario == "permission":
            send(
                {
                    "id": "server-request",
                    "method": "item/permissions/requestApproval",
                    "params": scoped,
                }
            )
            continue
        if scenario == "ratelimit":
            event(
                "turn/completed",
                {
                    "threadId": current_thread,
                    "turn": {
                        "id": turn_id,
                        "items": [],
                        "status": "failed",
                        "error": {"codexErrorInfo": "usageLimitExceeded"},
                    },
                },
            )
            continue
        value = responses.get(role, {"notes": ["bounded"]})
        if isinstance(value, list):
            value = value[min(counts[role] - 1, len(value) - 1)]
        inner = json.dumps(value) if scenario != "malformed" else "not-json"
        if scenario == "innerarray":
            inner = "[]"
        envelope = {"payload_json": inner}
        if scenario == "wireextra":
            envelope["extra"] = "not allowed"
        if scenario == "wiremissing":
            envelope = {}
        if scenario == "wiretype":
            envelope["payload_json"] = {"not": "a string"}
        text = json.dumps(envelope) if scenario != "wiremalformed" else "not-json"
        if scenario == "oversized":
            text = json.dumps({"payload_json": json.dumps({"text": "x" * 100000})})
        if scenario == "rerouted":
            event(
                "model/rerouted",
                scoped
                | {
                    "fromModel": "fixture-model",
                    "toModel": "fixture-rerouted",
                    "reason": "fixture",
                },
            )
        event("item/agentMessage/delta", scoped | {"itemId": "reply", "delta": text})
        event(
            "item/completed",
            scoped
            | {
                "item": {
                    "id": "reply",
                    "type": "agentMessage",
                    "phase": "final_answer",
                    "text": text,
                }
            },
        )
        if scenario != "nousage":
            event(
                "thread/tokenUsage/updated",
                scoped
                | {
                    "tokenUsage": {
                        "last": {
                            "inputTokens": 100,
                            "outputTokens": 100000 if scenario == "overflow" else 10,
                            "reasoningOutputTokens": 0,
                            "cachedInputTokens": 0,
                            "totalTokens": 110,
                        },
                        "total": {},
                    }
                },
            )
        event(
            "turn/completed",
            {
                "threadId": current_thread,
                "turn": {"id": turn_id, "items": [], "status": "completed"},
            },
        )
    elif method == "turn/interrupt":
        result(request, {})
    else:
        send(
            {
                "id": request.get("id"),
                "error": {"code": -32601, "message": "unsupported fixture method"},
            }
        )
