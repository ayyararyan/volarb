# Implemented architecture

The implementation is the proposal's deterministic scientific spine plus registry
claims, with bounded role assistance. It is not a swarm, execution platform or
Sharpe optimizer. LangGraph **1.2.12**, checkpoint SQLite **3.0.3** and Python3.12
were installed and exercised; `requirements.lock` pins the resolved environment.

| Component | Implemented authority |
|---|---|
| `graph.py` | Campaign batching; specification/critique/review subgraphs; durable experiment and protected-confirmation threads |
| `registry.py` | Interprocess-controlled SQLite writer, immutable science, lineage, search/exposure history, budgets, outbox, claims and events |
| `workers.py` | Independent supervisor and sandboxed numerical child; leases, fencing, resource bounds, cancellation, reconciliation |
| `data.py`, `baselines.py` | Qualification and frozen baseline semantics; no live adapters |
| `evaluators.py`, `accounting.py` | Spot prediction and full path four-leg economics at admitted fidelity |
| `replication.py`, `statistics.py` | Independent reconstruction and registered paired-session uncertainty |
| `agents.py`, `providers.py` | Six bounded role profiles; real configurable provider, recorded replay and labelled fixtures |
| `settings.py`, `provider_factory.py`, `codex_provider.py` | One `.env`, default managed Codex app-server, ChatGPT-owned login, structured role transport and durable subscription-call ceilings |
| `confirmation.py`, `security.py` | Frozen batch, release authority, isolated evaluation, signed bundle, consumed-partition history |
| `evidence.py` | Deterministic grades and evidence-linked research memory |
| `artifacts.py`, `backup.py` | Atomic content addressing, verified references and consistent recoverable snapshots |

State stores IDs and compact summaries; Parquet tables stay in artifacts. Registry
state, not a conversational summary, determines campaign completion. Parallel
preparation uses `Send` and a keyed conflict-detecting reducer. Numerical jobs are
never a single graph-wide barrier. A completion already present when a graph
registers its wait is ingested immediately; otherwise the graph parks durably.

Interrupted nodes restart at their beginning, so side effects are registry-idempotent.
Preparation now constructs a draft before its typed methodological review, with at
most two critic-driven revisions. Immutable registry versions and accepted role-call
receipts survive checkpoints; ambiguous calls are not automatically redispatched.
Final synthesis and steward run only after all numerical findings exist. See the
[live lifecycle and root-cause audit](live-research-lifecycle.md).
`Command(resume=...)` carries a registry event or signed release reference, not a
caller-authored success claim. Checkpoints cannot provide exactly-once external
computation; fenced single acceptance and reconciliation are application code.
See the official [interrupt](https://docs.langchain.com/oss/python/langgraph/interrupts),
[Graph API](https://docs.langchain.com/oss/python/langgraph/graph-api),
[persistence](https://docs.langchain.com/oss/python/langgraph/persistence) and
[subgraph](https://docs.langchain.com/oss/python/langgraph/use-subgraphs) documentation.

## Editable and rendered diagrams

| Diagram | Editable source | Rendered |
|---|---|---|
| Components/stores | [Mermaid](diagrams/components.mmd) | [SVG](diagrams/components.svg) |
| Campaign/experiment/confirmation | [Mermaid](diagrams/workflow.mmd) | [SVG](diagrams/workflow.svg) |
| Numerical recovery | [Mermaid](diagrams/recovery.mmd) | [SVG](diagrams/recovery.svg) |
| Data/evidence lineage | [Mermaid](diagrams/lineage.mmd) | [SVG](diagrams/lineage.svg) |
| Permission boundaries | [Mermaid](diagrams/permissions.mmd) | [SVG](diagrams/permissions.svg) |

F4 depth replay and adaptive allocation remain explicitly optional, unsupported
extensions. Arbitrary generated Python is not an extension mechanism: new numerical
primitives require a reviewed versioned source change, tests and new experiment IDs.
