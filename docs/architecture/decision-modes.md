# Decision modes for Volarb and the Execution Engine

Decision date: **2026-10-05**. Reviewed source: `61471deaa3cc35da2d88b1bef251680829daaef8` on `feature/command-commit-guard`.

**Decision:** the current reusable Execution Engine is `PURE_ALGORITHMIC`. Contextual strategy reasoning is `HYBRID`. No current registered operational entity is assigned `PURE_AGENTIC`.

These decisions govern implementation planning. They do not declare the remaining components implemented, introduce new trading permissions, or change the current operating covenant. The classification was requested after the Python Command Commit Guard work; the guard remains the first implemented production execution box.

## Scope and coverage

This review covers the entire active numbered workflow, including all execution boxes and sub-boxes and the upstream strategy modules that explain where LLM judgment belongs.

| Scope | Active entities classified | Algorithmic | Hybrid | Agentic |
|---|---:|---:|---:|---:|
| Reusable Execution Engine, canonical `[5,0,...]` | 43 | 43 | 0 | 0 |
| Strategy and global orchestration, `[0,...]` through `[4,...]` | 52 | 42 | 10 | 0 |
| Total | **95** | **85** | **10** | **0** |

The 95 records comprise 12 aggregate containers, 30 decision/process nodes including Passive Chase, 12 interfaces/resources/schedulers, 27 data contracts and 14 states. There are **17 active execution containers/processes** within the engine's 43 records. All 17 are algorithmic.

The count of ten hybrids includes four aggregate containers: Master Architecture, Regime Gate, Underlying Allocation and Position Management. The remaining six are strategy processes. Position Management's strategy/risk engine coordinates its judgment-bearing children; it need not make a separate model call. A hybrid label is not an instruction to instantiate an agent per VID.

The machine-readable decisions live in:

- [Execution Engine decision inventory](../../architecture/components/execution-engine/decision-modes.json), keyed to the canonical component registry.
- [Strategy and orchestration decision inventory](../../architecture/strategies/volarb/decision-modes.json), keyed to the assembled registry outside namespace 5.

Every active non-edge VID is covered exactly once across these files. Retired entities remain tombstones and are excluded. Edges are routing and transition rules, rather than independent decision makers; they are executed deterministically over validated outputs. The `[3,0,...]` decisions apply to every runtime Trade Selection instance. Supporting contracts and states are classified by their validation/storage behavior, not by whether their producer uses an LLM.

## What the three modes mean

| Mode | Meaning | Consequence |
|---|---|---|
| `PURE_AGENTIC` | Open-ended LLM reasoning owns the substantive decision. Generic transport, logging and schema validation alone do not make it hybrid. | Appropriate for some research, interpretation or explanation tasks with no operational authority. None of the current registered operational boxes has only that responsibility. |
| `PURE_ALGORITHMIC` | Numerical methods, predicates, optimization algorithms or state machines determine behavior without runtime LLM judgment. | Observations may be uncertain and solvers may use bounded heuristics. Their inputs, policy, tolerances, seeds where relevant and transitions must still be inspectable and replayable. |
| `HYBRID` | LLM interpretation influences a proposal or assessment, while substantive numerical policy and deterministic admission determine what is accepted. | The model's permitted outputs, validator, final authority and unavailable/invalid-output behavior must be explicit. |

Classification follows responsibility, not implementation language, labels such as "agent" or "optimizer", or the use of LangGraph. LangGraph's official [Graph API overview](https://docs.langchain.com/oss/python/langgraph/graph-api) explicitly permits nodes and edges containing ordinary code as well as LLM calls. Python/LangGraph orchestration therefore remains compatible with a fully algorithmic execution engine.

The central design question is: **what uncertainty does reasoning resolve here?** News relevance and economic interpretation can require contextual judgment. Quantity conservation, hedge coverage, account capacity, current intent, observed fills and emergency priority require formal rules and authoritative observations. An LLM cannot turn an unknown broker outcome into a known one.

## Complete box and runtime-component classification

The following tables include every active container, process, scheduler, resource and interface. Contracts and states appear in the complete supporting inventory at the end.

### Global orchestration

| VID | Box or sub-box | Classification | Judgment |
|---|---|---|---|
| `[0,0,0,0,0]` | Master Architecture | `HYBRID` | Aggregates hybrid strategy judgment and algorithmic execution. Scheduling, routing and committed state changes remain deterministic; this is an aggregate classification, not an additional LLM agent. |
| `[0,0,1,1,1]` | Start / Wake | `PURE_ALGORITHMIC` | Wake conditions, session identity and duplicate-start suppression are explicit orchestration rules. |
| `[0,0,2,1,1]` | Fan out one Trade Selection instance per selected X | `PURE_ALGORITHMIC` | Fan out exactly once per valid underlying commitment and instance identity; reasoning must not create duplicate graphs or unreserved work. |

### Regime Gate

| VID | Box or sub-box | Classification | Judgment |
|---|---|---|---|
| `[1,0,0,0,0]` | Regime Gate | `HYBRID` | Combines numerical regime evidence with interpretation of macroeconomic and event context. Deterministic admission rules must validate the resulting permission to consider new exposure. |
| `[1,0,1,1,1]` | Start / scheduled regime review | `PURE_ALGORITHMIC` | Trigger a review from approved time or event conditions, preserving review identity and rate limits. |
| `[1,0,2,1,1]` | Collect regime-relevant market context | `HYBRID` | Code acquires numerical observations and checks provenance, timestamps and duplicates; an LLM identifies relevant news, interprets events and assembles evidence-backed context. |
| `[1,0,3,1,1]` | Multi-day Regime Gate | `HYBRID` | An LLM synthesizes multi-day evidence and proposes a regime. Code enforces the calibrated policy, evidence sufficiency, expiry and hard prohibitions before publishing an admissible decision. |
| `[1,0,5,1,1]` | Hand off to Underlying Allocation | `PURE_ALGORITHMIC` | Handoff requires a current, validated favorable regime. Narrative confidence cannot bypass the gate. |
| `[1,0,5,3,1]` | Regime Recheck Scheduler | `PURE_ALGORITHMIC` | Execute versioned deadlines and typed invalidation triggers. An LLM may propose a trigger during review; it does not control the live scheduler or postpone mandatory reviews. |

### Underlying Allocation

| VID | Box or sub-box | Classification | Judgment |
|---|---|---|---|
| `[2,0,0,0,0]` | Underlying Allocation | `HYBRID` | Combines contextual opportunity evaluation with numerical feasibility, allocation and atomic capital reservation. Only opportunity evaluation needs LLM judgment. |
| `[2,0,2,1,1]` | Read normalized market data and account/capital state | `PURE_ALGORITHMIC` | Read and normalize market/account facts with freshness checks. Account balances and observations must never be reconstructed from an LLM narrative. |
| `[2,0,3,1,1]` | Evaluate NIFTY / BANKNIFTY / SENSEX opportunities | `HYBRID` | Code computes comparable volatility, liquidity, cost and risk measures; an LLM supplies bounded contextual labels about event exposure and suitability within the declared opportunity policy. |
| `[2,0,4,1,1]` | Apply capital and margin feasibility constraints | `PURE_ALGORITHMIC` | Apply broker-backed margin/capital constraints, portfolio limits and reservations exactly. A plausible trade narrative cannot make an infeasible position feasible. |
| `[2,0,5,1,1]` | Selected set S empty? | `PURE_ALGORITHMIC` | Emptiness is a predicate over the validated eligible set, with a fixed wait transition. |
| `[2,0,7,3,1]` | Intraday Opportunity Recheck Scheduler | `PURE_ALGORITHMIC` | Run bounded time/event rechecks against current commitment and regime validity; deduplicate triggers and enforce end-of-session rules. |
| `[2,0,7,1,1]` | Portfolio Capital Allocator | `PURE_ALGORITHMIC` | Allocate capital with a declared objective, quantitative inputs and hard portfolio constraints. The objective remains to be specified; that gap does not justify discretionary LLM sizing. |
| `[2,0,8,9,1]` | Assign W_X to every X in S | `PURE_ALGORITHMIC` | Assign exact budget values from the accepted allocation result; rounding, conservation and units are deterministic. |
| `[2,0,10,9,1]` | Reserve each W_X | `PURE_ALGORITHMIC` | Reserve budgets atomically across concurrent graphs and preserve them while a graph waits. This is transactional accounting. |
| `[2,0,11,1,1]` | For each X in S | `PURE_ALGORITHMIC` | Iterate over the validated committed set without inventing, dropping or duplicating members. |
| `[2,0,12,1,1]` | Launch Trade Selection X | `PURE_ALGORITHMIC` | Launch the correct instance with its committed budget, identity and version using idempotent orchestration. |

### Trade Selection

| VID | Box or sub-box | Classification | Judgment |
|---|---|---|---|
| `[3,0,0,0,0]` | Trade Selection | `PURE_ALGORITHMIC` | Enumerates approved structures and solves an explicit constrained selection problem. With frozen objectives and admissibility rules, an LLM is unnecessary in the live selection loop. |
| `[3,0,3,1,1]` | Build or refresh admissible structure universe C_X | `PURE_ALGORITHMIC` | Enumerate the approved catalogue against listed contracts, expiries, quotes and the current covenant; reject unsupported structures and missing observations. |
| `[3,0,5,1,1]` | Constrained Structure Optimizer | `PURE_ALGORITHMIC` | Evaluate explicit payoff, risk, cost and capital constraints, optimize the frozen objective, and apply reproducible tie-breaking or return no candidate. |
| `[3,0,7,3,1]` | Within-Hour Structure Recheck Scheduler | `PURE_ALGORITHMIC` | Apply bounded within-hour review rules while preserving reservations and respecting regime/session expiry. |

### Position Management

| VID | Box or sub-box | Classification | Judgment |
|---|---|---|---|
| `[4,0,0,0,0]` | Position Management | `HYBRID` | Combines contextual economic decisions with deterministic risk limits, margin validation, exact intent construction and mandatory emergency handling. |
| `[4,0,2,1,1]` | Volarb Execution + Risk Management Engine | `HYBRID` | An LLM may choose an economic response from admissible alternatives; code computes exposures, enforces limits and versions intent. This orchestrator delegates judgment to the monitoring/action nodes. |
| `[4,0,3,1,1]` | Build intended execution plan | `PURE_ALGORITHMIC` | Compile an accepted economic decision into exact instrument identities, signed quantities, constraints and runtime versions. An underspecified decision returns for clarification instead of being guessed. |
| `[4,0,4,1,1]` | Pre-trade Margin Feasibility Check | `PURE_ALGORITHMIC` | Use current normalized broker margin/account facts for the actual proposed transition, including live orders and existing positions; infeasibility returns to strategy policy. |
| `[4,0,5,6,1]` | BrokerMarginFeasibilityPort | `PURE_ALGORITHMIC` | A typed query/normalization interface transports broker facts. It has no discretion to grant margin or reinterpret feasibility. |
| `[4,0,6,6,1]` | OptimalExecutionPort | `PURE_ALGORITHMIC` | Validate and transport versioned broker-neutral economic intent to the generic engine. Transport does not add strategy authority. |
| `[4,0,3,1,2]` | Live execution / risk / monitoring policy | `HYBRID` | Deterministic monitors enforce continuous hard risk conditions; an LLM periodically interprets changing context. Mandatory risk actions must proceed without waiting for the LLM. |
| `[4,0,4,1,2]` | Hold / adjust / recenter / hedge / reduce / exit | `HYBRID` | An LLM selects or explains an admissible economic action; code independently evaluates its quantitative consequences and enforces mandatory exits, constraints and authorization. |

### Execution Engine

| VID | Box or sub-box | Classification | Judgment |
|---|---|---|---|
| `[5,0,0,0,0]` | Execution Engine | `PURE_ALGORITHMIC` | Converge exact, approved economic intent to authoritative broker state through explicit numerical policies and state machines. The selected baseline has no unresolved semantic task for an LLM. |
| `[5,0,1,9,1]` | Active Instrument Execution Registry | `PURE_ALGORITHMIC` | Maintain versioned economic requirements, confirmed effects and remaining work with scoped concurrency control. Supersession and cancellation cannot depend on language-model interpretation. |
| `[5,0,3,6,1]` | Broker Execution Port | `PURE_ALGORITHMIC` | Validate and transport provider-neutral commands, queries and streams; normalize outcomes while leaving execution policy in the engine. |
| `[5,0,2,1,2]` | Hedge / Offset Relationship Analyzer | `PURE_ALGORITHMIC` | Derive coverage and offsets from typed instrument/payoff relationships, current positions and authoritative margin facts. Unsupported instruments remain unsupported; an LLM cannot certify a hedge. |
| `[5,0,2,1,3]` | Margin Sequence Optimizer | `PURE_ALGORITHMIC` | Search feasible intermediate execution states under explicit margin, coverage and quantity constraints. Emit ORDERED or UNCONSTRAINED only with a verifiable feasibility basis. |
| `[5,0,3,0,1]` | Optimal Execution | `PURE_ALGORITHMIC` | Run the specified algorithm on released slices under deterministic ordering, quantity, integrity and interrupt constraints. |
| `[5,0,4,1,1]` | Temporal Execution Controller | `PURE_ALGORITHMIC` | Drive timers and broker events, invoke the selected execution algorithm, validate its output and submit only through the guard; stale or delayed work is rejected. |
| `[5,0,4,6,1]` | Execution Algorithm Port | `PURE_ALGORITHMIC` | A typed plugin boundary exposes only eligible work and permitted actions. A future agentic plugin would require a new decision review; the current binding is Passive Chase. |
| `[5,0,2,0,1]` | Margin Optimization | `PURE_ALGORITHMIC` | Solve numerical path feasibility and ordering using typed instruments and broker-backed account capacity. Difficulty or combinatorial complexity does not imply a need for an LLM. |
| `[5,0,5,5,1]` | Passive Chase | `PURE_ALGORITHMIC` | The documented BUY-bid/SELL-ask, wait T, evaluate at most N intervals, cancel/reconcile and market-remainder policy is a complete state-machine specification. |
| `[5,0,5,3,1]` | Passive Reprice Timer | `PURE_ALGORITHMIC` | Use the injected clock to schedule T, enforce cycle counters and cancel stale callbacks. LLM latency must not control repricing. |
| `[5,0,3,1,1]` | Ordering Constraint Enforcer | `PURE_ALGORITHMIC` | Release only work permitted by the dependency graph and confirmed predecessor effects. Missing or invalid ordering permits no execution. |
| `[5,0,6,0,1]` | Interrupt Control | `PURE_ALGORITHMIC` | Emergency preemption, priority, cancellation, flattening and persistent latching follow fixed rules and must remain available when an LLM is unavailable. |
| `[5,0,6,1,1]` | Interrupt Arbiter | `PURE_ALGORITHMIC` | Validate scope and authority, enforce L3 > L2 > L1 > normal, and prevent downgrade or unauthorized latch clearing. |
| `[5,0,7,0,1]` | Execution Slicing | `PURE_ALGORITHMIC` | Transform already-permitted quantity into bounded slices while conserving quantity and precedence. The current one-slice sequential policy needs no judgment. |
| `[5,0,7,1,1]` | Slice Planner | `PURE_ALGORITHMIC` | Implement slice_count=1 and SEQUENTIAL first. Later numerical impact or liquidity optimization can remain algorithmic with explicit constraints and reproducible policy versions. |
| `[5,0,8,0,1]` | Execution Recovery | `PURE_ALGORITHMIC` | Coordinate durable admission and authoritative reconstruction after uncertainty. A model cannot substitute inferred broker state for verified orders, fills and positions. |
| `[5,0,8,9,1]` | Execution Ledger | `PURE_ALGORITHMIC` | Persist action/correlation identity and state transitions before broker release, enforce atomic uniqueness, and recover history after restart; broker observations remain authoritative. |
| `[5,0,8,1,1]` | Reconciliation Engine | `PURE_ALGORITHMIC` | Reconcile ledger entries against authoritative orders, trades and positions; deduplicate facts, resolve races and preserve ambiguity when evidence is insufficient. |
| `[5,0,8,1,2]` | Command Commit Guard | `PURE_ALGORITHMIC` | Enforce current intent, interrupt compatibility, integrity permission, unique identity and durable write-ahead recording before broker release. No LLM may waive these predicates. |
| `[5,0,9,0,1]` | State Integrity | `PURE_ALGORITHMIC` | Compute action-specific permission from explicit freshness, completeness, consistency and recovery predicates. |
| `[5,0,9,1,1]` | State Integrity Guard | `PURE_ALGORITHMIC` | Apply the correct integrity requirements to normal adds, reductions, cancellations and emergency flattening. Missing required evidence denies the affected action. |

## Exact boundaries for the hybrid processes

### Regime context collection — `[1,0,2,1,1]`

Code acquires time-stamped market features and records sources. The model identifies relevant developments, distinguishes new information from repetition, links events to transmission channels and flags conflicting evidence. Its output is a contextual evidence packet, not permission to trade.

Trusted numerical observations come from acquisition/calculation tools. Model-produced numbers cannot silently enter those fields. Referenced sources, event time versus publication time, provenance and freshness are checked before admission. Source text is evidence, never executable instructions. Missing or unverified context is marked incomplete rather than filled with a plausible narrative.

### Multi-day Regime Gate — `[1,0,3,1,1]`

The model synthesizes the supplied evidence and proposes `FAVORABLE`, `UNFAVORABLE` or `UNCERTAIN`, with reasons and a proposed review condition from a typed vocabulary. Code applies the adopted regime policy, calibrated numerical gates, hard prohibitions, evidence sufficiency and maximum validity period. The validated favorable result permits downstream consideration; it never forces an allocation or trade.

The exact regime model and calibration are still open. This classification does not invent thresholds or make an uncalibrated narrative an operational gate. Until the policy exists and is validated, insufficient evidence remains `UNCERTAIN`. Missing output cannot extend an earlier favorable assessment. A prior assessment may survive only while its independent, precommitted validity and invalidation conditions still hold.

### Cross-index opportunity assessment — `[2,0,3,1,1]`

Code computes comparable volatility, liquidity, transaction-cost, capital and risk measures. The model can attach bounded contextual labels concerning index-specific event exposure or suitability. A versioned quantitative policy maps admitted labels and measured features into the eligible opportunity set or scores. The model does not invent an IV/RV estimate, choose arbitrary scoring weights, or reserve money.

Numerical capital allocation is a separate algorithmic step. When contextual evidence required by the selected policy is unavailable, no new commitment relying on it is admitted. An eventual numerical-only operating variant needs its own explicit configuration and validation; it is not an automatic fallback.

### Position strategy/risk engine — `[4,0,2,1,1]`

This box coordinates economic interpretation and desired exposure. Model judgment may influence which admissible adjustment addresses the current situation. Code owns exact risk computation, admissible action construction, sizing, intent identity/version and the acceptance of a proposed change.

The judgment can be supplied by the monitoring and action-selection children. Adding a second model merely to approve the first adds no established control. The engine must reject an underspecified economic proposal rather than guess instruments, direction or size while compiling execution intent.

### Live monitoring policy — `[4,0,3,1,2]`

Use two independent paths: deterministic monitors for approved hard risk/session conditions, and slower contextual reviews where model interpretation can help. Loss limits, mandatory session exit, data integrity and emergency conditions cannot wait for a model response or be suppressed by a convincing explanation.

A delayed model response is tied to its input snapshot and intent/policy version. If those inputs have been superseded, the response is invalid. During model unavailability, hard monitoring and authorized risk responses continue. The system does not interpret model silence as permission to hold.

### Economic action selection — `[4,0,4,1,2]`

The model may propose `HOLD`, `ADJUST`, `RECENTRE`, `HEDGE`, `REDUCE` or `EXIT` only within the approved action set. Code computes or checks the exact candidate, transition margin, exposures, transaction costs, session/covenant restrictions and current version. It emits an accepted economic intent; execution remains downstream.

Mandatory risk actions dominate discretionary choice. `HOLD` must pass the same applicable hard constraints as any other outcome; it is not a universal error fallback. A rejected discretionary proposal does not suspend independently required cancellation, reduction or exit. The existing covenant and authorization model still determine which actions are permitted.

## Why the difficult execution boxes remain algorithmic

### Hedge/offset analysis and margin sequencing

The word "infer" in the Hedge / Offset Relationship Analyzer means deriving relationships from instrument attributes, signed quantities, payoff structure, existing positions and provider-normalized margin facts. It does not require semantic guessing. A strategy-agnostic engine can use typed instrument models without knowing terms such as butterfly, body, wing or recenter.

Offsets must account for quantity, expiry, instrument compatibility and coverage already committed elsewhere. Similar Greeks or a model's claim that two positions "hedge each other" is insufficient proof of bounded payoff or broker margin relief. Unsupported instruments require an explicit model/adapter extension; they are not a reason to ask an LLM to certify coverage.

The Margin Sequence Optimizer must test feasible **intermediate** states, not only the final portfolio. It must consider outstanding orders, possible partial fills, account capacity and protective inventory. An `UNCONSTRAINED` plan must be feasible for the permitted concurrent work and its relevant fill combinations, rather than merely for one favorable sequence. Budgeted search may return a verified feasible plan without claiming global optimality. Timeout or lack of a feasibility basis means no release of unverified work.

The objective, available margin-query capability and conservative treatment of unobservable states remain implementation decisions. They must be formalized and benchmarked. Code validates mathematical feasibility; it does not guarantee that future market conditions or execution costs stay favorable.

### Capital allocation and structure selection

Both are explicit constrained numerical problems. The objectives and calibration still require research, but live LLM sizing would hide that unresolved design choice. Freeze the objective, constraints, measurement inputs, rounding and tie-breaking under a policy version. Allow a no-candidate outcome. Preserve reservations across waiting graphs and avoid shared-capital double counting.

An LLM may assist offline with hypotheses, candidate research or interpretation. Such work does not silently expand the approved structure catalogue, change risk budgets or modify a deployed objective. Future evidence may justify a specifically bounded hybrid selector; the current selection contract does not require one.

### Slicing and Passive Chase

The first Slice Planner has one slice and sequential scheduling. Later impact/liquidity optimization can be numerical. Quantity conservation, minimum lot sizes and inherited precedence remain hard invariants.

Passive Chase already specifies every substantive step: buy at the current bid or sell at the ask, wait `T`, consume confirmed fills, refresh only the remainder and fall back after `N` evaluation intervals. There are at most `N-1` repricing opportunities; `N=1` means one wait followed by fallback. No LLM is needed in this timing loop.

Before market fallback, the old order must be authoritatively unable to fill further and the exact remainder must be recomputed. Unknown cancellation is a recovery state. It is never evidence that the order was cancelled. Missing `T`/`N`, invalid units or unverified work must block initial execution until valid configuration/state is supplied.

### Recovery, integrity and mutation admission

The ledger records intended actions and observed outcomes. Broker observations establish actual orders, fills and positions. Reconciliation compares the two, deduplicates observations and preserves uncertainty where the evidence is insufficient. It must never use an LLM's best guess as recovered broker truth.

State Integrity checks are action-specific. A cancellation can have different data requirements from a new risk-adding order; emergency flattening still requires sufficiently authoritative position/order state and connectivity. A single permissive readiness boolean is inadequate.

The Command Commit Guard is the final deterministic admission point. Durable identity, current intent, integrity and interrupt checks apply to normal and emergency mutations. LLM confidence, urgency or a graph retry cannot bypass it.

## Subprocedures without separate canonical VIDs

These are named responsibilities inside existing boxes, not new architectural entities. Do not allocate or renumber VIDs merely to create an agent per procedural step.

| Owning VID | Internal procedure | Mode and boundary |
|---|---|---|
| `[5,0,6,0,1]` | L1 `CANCEL_WORK` | `PURE_ALGORITHMIC`: suppress normal work, cancel/reconcile unfilled orders, preserve confirmed positions and keep the latch. |
| `[5,0,6,0,1]` | L2 `FLATTEN_SCOPE` | `PURE_ALGORITHMIC`: cancel/reconcile, obtain confirmed scoped positions, flatten exact net quantities through the guard. |
| `[5,0,6,0,1]` | L3 `FLATTEN_ALL` | `PURE_ALGORITHMIC`: preempt all normal managed work and flatten the explicitly controlled scope; never silently include unrelated holdings. |
| `[5,0,6,1,1]` | Clear/resume admission | `PURE_ALGORITHMIC`: require a valid clear from the designated upstream authority and fresh state. Selecting that authority remains an open control-plane decision; handler completion alone cannot clear it. |
| `[5,0,5,5,1]` | Initial placement | `PURE_ALGORITHMIC`: current eligible quantity, valid same-side quote and approved configuration. |
| `[5,0,5,5,1]` | Wait/evaluate/reprice | `PURE_ALGORITHMIC`: injected clock, exact cycle count and confirmed remainder; interrupted or superseded callbacks have no authority. |
| `[5,0,5,5,1]` | Cancel/reconcile/market fallback | `PURE_ALGORITHMIC`: resolve the prior order before any replacement quantity can be admitted. |
| `[5,0,8,1,2]` | Validate, reserve identity, write ahead, release, record outcome | `PURE_ALGORITHMIC`: ordered durable transitions with scoped concurrency controls and no blind retry. |
| `[5,0,8,1,1]` | Restart and unknown-outcome recovery | `PURE_ALGORITHMIC`: rebuild from durable history and authoritative observations before admitting new work in the affected scope. |

The unnumbered Dhan provider is algorithmic translation/transport/normalization. The optional Strategy Execution Adapter is algorithmic when compiling an already complete economic decision; unresolved strategy choices return upstream. Testkit clocks, simulated brokers, fault injection and trace checking are algorithmic infrastructure. None of these receives a new Volarb VID through this review.

## Authority, failure and replay rules

1. A hybrid process emits a typed proposal linked to an evidence snapshot, event/source timestamps, policy version, decision identity, expiry and applicable runtime intent/version. Retain model and prompt/configuration identifiers and the accepted proposal for audit. These are required design fields, not an assertion that a complete proposal schema exists today.
2. Code separately validates evidence references, enum/range constraints, units, numerical consequences, current versions and authorization. Shape validation alone cannot establish an economically sound proposal; calibration and policy evaluation remain necessary.
3. LLM tasks receive read-only evidence/calculation tools and a proposal channel. Broker mutation credentials and direct mutation tools belong behind the execution boundary. The runtime must enforce this separation; merely asking the model to respect it is insufficient.
4. The deterministic monitors can issue authorized risk interrupts independently of discretionary model reviews. A model may propose an interrupt, but it cannot veto a mandatory one, downgrade its priority, clear its latch or enlarge its scope through prose.
5. Record nondeterministic model responses and external observations as events. Deterministic replay consumes the recorded responses; it does not ask a model to reproduce an answer. Fresh model evaluation belongs in a separate experiment.
6. Workflow checkpoints do not replace the Execution Ledger or prove that a broker side effect happened exactly once. Resuming a graph may encounter a previous action: action identity, durable admission and reconciliation decide whether anything further is permitted.
7. A new action ID must not provide a route around unresolved ambiguity. Recovery state gates subsequent work in the affected economic scope, including after restart or a post-mutation ledger failure.
8. Safe unavailability is action-specific: stop discretionary risk increases, preserve integrity/reconciliation, and continue independently authorized hard-risk handling. Neither unconditional `HOLD` nor an indiscriminate automatic market exit is a suitable universal fallback.

## Implementation gaps exposed by the review

The current Python guard checks injected authorities, rejects action/correlation reuse, writes ahead and records ambiguous outcomes. Its in-process lock serializes one guard instance. The broader production guarantees still require:

- A durable ledger with atomic action/correlation reservation and correct transaction boundaries across processes or a documented single-writer topology. Replaying a graph must not allocate a fresh identity for the same economic attempt.
- An admission boundary that coordinates intent supersession, interrupt/integrity changes and broker release. Checking a boolean before an awaited ledger operation is not by itself proof that the permission remains valid at release. An accepted in-flight action cannot be retroactively unsent; subsequent preemption must reconcile it.
- Real intent, integrity and interrupt authorities, persistent latches and scope-aware recovery that blocks unresolved work after timeout, cancellation, crash or incomplete outcome recording.
- A finalized strategy-to-engine intent/constraint schema, explicit quantity units and composition/mount context. The existing implementation does not establish every field described in the broader architecture.
- Numeric objectives for portfolio allocation, structure selection and margin sequencing; calibrated regime/admission policies; approved structure catalogue; review expiry/invalidation rules; and Passive Chase parameters.
- A verified Python composition-test boundary and provider bridge. The retained JavaScript testkit/provider contracts do not by themselves demonstrate end-to-end execution by the Python engine.

These are design and implementation obligations, not findings that a live system has failed. The complete system is not implemented. Classification makes the responsibility for resolving each obligation explicit.

## Implementation and validation order

| Stage | Deliverable | Evidence required |
|---|---|---|
| 1 | Integrate the existing Python guard branch with current main and retain these decisions. | Review the final changes, preserve the Mac runner work, and pass the affected CI checks. |
| 2 | Durable ledger plus intent/version admission and recovery semantics. | Duplicate attempts across concurrent writers, write failure before send, crash after send, lost acknowledgement, restart and post-send ledger failure leave no path to an unverified replacement action. |
| 3 | State Integrity and Interrupt Control, composed with the guard and reconciliation. | Stale/unknown state denies the correct action classes; L3 preempts L1; interrupted work cannot restart through a stale timer; failed flattening remains unresolved. |
| 4 | Python component/composition harness and provider bridge; then margin, slicing and Passive Chase. | The same production code runs under injected time/broker/ledger dependencies. Test partial fills, intermediate margin feasibility, sequential release, cancel/fill races and exact remainder conservation. |
| 5 | Explicit numerical strategy policies and the six bounded hybrid responsibilities. | Data/model/policy versions are retained; malformed, stale, unsupported, unavailable or instruction-bearing source content cannot bypass constraints; mandatory risk handling survives model failure. |
| 6 | Complete scenarios, seeded campaigns, replay and shadow evaluation. | Compare economic quality against declared numerical baselines using dated holdout/walk-forward evidence, realistic costs and measured latency. Model benefit must be demonstrated rather than assumed. |

Classifying a component algorithmic does not settle the quality of its model. Classifying it hybrid does not establish that an LLM improves it. Judge contextual model contributions on incremental decision quality, stability, latency and cost; judge the execution layer on invariants and authoritative convergence. Future classification changes require an explicit architecture revision with a bounded role and validation evidence.

## Complete supporting contract and state inventory

These entries carry no independent discretionary authority. A contract may transport a validated hybrid judgment while its schema remains algorithmic; a state may reflect that judgment while its transition rules remain algorithmic. This distinction prevents accidentally counting every message or state as another agent.

| VID | Supporting entity | Role | Classification |
|---|---|---|---|
| `[1,0,4,7,1]` | REGIME_FAVORABLE | CONTRACT | `PURE_ALGORITHMIC` |
| `[1,0,4,2,1]` | NO-NEW-SHORT-GAMMA | STATE | `PURE_ALGORITHMIC` |
| `[1,0,6,2,1]` | Wait until next multi-day review condition | STATE | `PURE_ALGORITHMIC` |
| `[1,0,4,2,2]` | Fail-safe: do not deploy new short gamma | STATE | `PURE_ALGORITHMIC` |
| `[2,0,1,7,1]` | REGIME_FAVORABLE input | CONTRACT | `PURE_ALGORITHMIC` |
| `[2,0,6,2,1]` | INTRADAY OPPORTUNITY WAIT | STATE | `PURE_ALGORITHMIC` |
| `[2,0,8,2,1]` | Wait until next intraday scan | STATE | `PURE_ALGORITHMIC` |
| `[2,0,6,7,1]` | Selected set S | CONTRACT | `PURE_ALGORITHMIC` |
| `[2,0,9,7,1]` | DailyUnderlyingCommitment | CONTRACT | `PURE_ALGORITHMIC` |
| `[3,0,1,7,1]` | DailyUnderlyingCommitment + W_X input | CONTRACT | `PURE_ALGORITHMIC` |
| `[3,0,2,2,1]` | Graph X ACTIVE / COMMITTED | STATE | `PURE_ALGORITHMIC` |
| `[3,0,4,7,1]` | Candidate structure universe C_X | CONTRACT | `PURE_ALGORITHMIC` |
| `[3,0,6,2,1]` | WAITING_FOR_STRUCTURE | STATE | `PURE_ALGORITHMIC` |
| `[3,0,8,2,1]` | Wait minutes / within the hour | STATE | `PURE_ALGORITHMIC` |
| `[3,0,6,7,1]` | Selected StructureSpec | CONTRACT | `PURE_ALGORITHMIC` |
| `[3,0,7,2,1]` | Decision complete | STATE | `PURE_ALGORITHMIC` |
| `[3,0,8,7,1]` | TradeIntent | CONTRACT | `PURE_ALGORITHMIC` |
| `[4,0,1,7,1]` | TradeIntent input | CONTRACT | `PURE_ALGORITHMIC` |
| `[4,0,5,7,1]` | Atomic broker-neutral instrument execution intent | CONTRACT | `PURE_ALGORITHMIC` |
| `[5,0,4,7,1]` | Normalized Broker Execution Facts | CONTRACT | `PURE_ALGORITHMIC` |
| `[5,0,1,7,1]` | Live Market Execution State | CONTRACT | `PURE_ALGORITHMIC` |
| `[5,0,1,7,2]` | Live Broker Account State | CONTRACT | `PURE_ALGORITHMIC` |
| `[5,0,2,7,1]` | Execution Dependency Graph | CONTRACT | `PURE_ALGORITHMIC` |
| `[5,0,3,7,1]` | Eligible Execution Work Set | CONTRACT | `PURE_ALGORITHMIC` |
| `[5,0,4,7,2]` | Temporal Execution Decision | CONTRACT | `PURE_ALGORITHMIC` |
| `[5,0,5,7,1]` | Passive Chase Parameters | CONTRACT | `PURE_ALGORITHMIC` |
| `[5,0,5,2,1]` | Passive Chase State | STATE | `PURE_ALGORITHMIC` |
| `[5,0,2,7,2]` | Execution Ordering Plan | CONTRACT | `PURE_ALGORITHMIC` |
| `[5,0,6,7,1]` | Interrupt Directive | CONTRACT | `PURE_ALGORITHMIC` |
| `[5,0,6,2,1]` | Latched Interrupt State | STATE | `PURE_ALGORITHMIC` |
| `[5,0,6,7,2]` | Interrupt Action Plan | CONTRACT | `PURE_ALGORITHMIC` |
| `[5,0,1,7,3]` | Runtime Intent Identity | CONTRACT | `PURE_ALGORITHMIC` |
| `[5,0,7,7,1]` | Execution Slice Plan | CONTRACT | `PURE_ALGORITHMIC` |
| `[5,0,7,2,1]` | Slice Progress State | STATE | `PURE_ALGORITHMIC` |
| `[5,0,7,7,2]` | Slice Policy | CONTRACT | `PURE_ALGORITHMIC` |
| `[5,0,8,2,1]` | Recovery State | STATE | `PURE_ALGORITHMIC` |
| `[5,0,8,7,1]` | Execution Action Envelope | CONTRACT | `PURE_ALGORITHMIC` |
| `[5,0,8,7,2]` | Reconciliation Result | CONTRACT | `PURE_ALGORITHMIC` |
| `[5,0,9,7,1]` | Integrity Assessment | CONTRACT | `PURE_ALGORITHMIC` |
| `[5,0,9,2,1]` | Integrity State | STATE | `PURE_ALGORITHMIC` |
| `[0,0,1,7,1]` | Provider Error Envelope | CONTRACT | `PURE_ALGORITHMIC` |

## Sources and ownership

- [Canonical execution registry](../../architecture/components/execution-engine/vector-id-registry.json) and [assembled strategy registry](../workflows/vector-id-registry.json): entity coverage, identity and retirement status.
- [Execution Engine](../workflows/execution-engine.md), [Recovery](../workflows/execution-recovery.md), [State Integrity](../workflows/state-integrity.md), [Interrupt Control](../workflows/interrupt-control.md), [Slicing](../workflows/execution-slicing.md) and [Passive Chase](../execution-algorithms/passive-chase.md): current execution responsibilities.
- [Regime Gate](../workflows/regime-gate.md), [Underlying Allocation](../workflows/underlying-allocation.md), [Trade Selection](../workflows/trade-selection.md) and [Position Management](../workflows/position-management.md): strategy responsibilities and unresolved policies.
- [Python engine status](../../execution-engine/README.md), [Command Commit Guard](../../execution-engine/volarb_execution/recovery/command_commit_guard.py) and [current task ledger](../../tasks.md): implementation boundaries.
- [Personal covenant](../PERSONAL_BUTTERFLY_TRADING_GOVERNANCE.md): current operating authority, unchanged by this design decision.

All classifications and implementation recommendations in this document are architectural judgments based on those specifications. No classification renumbers a VID, makes a provider strategy-owned, grants broker credentials to a model or activates trading.
