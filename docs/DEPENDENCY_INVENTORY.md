# Dependency inventory

Current source boundaries reviewed: **2026-10-03**. Host/integration observations
below are explicitly dated to **2026-09-29**, not a fresh live deployment audit.

Scope: repository plus read-only inspection of the active VolArb Python modules,
Dhan MCP source/manifests, installed tool versions, OpenClaw skill/plugin metadata,
automation metadata and relevant macOS service definitions. No credential contents,
raw broker evidence, provider config, session history or live ledger copied.

## Current shared execution dependencies

- The canonical [Execution Engine](../execution-engine/README.md) owns the shared
  broker vocabulary, runtime ports and global Provider Error Envelope.
- [Dhan Provider](../services/dhan-chatgpt-mcp/README.md) imports these shared
  contracts; service-only copies of its exported runtime are incomplete.
- [Execution Testbed](../execution-testkit/README.md) supplies separate deterministic
  dependencies. Production must not import `execution-testkit`.
- The portable archive and Docker context preserve the provider's shared import
  closure. Only the portable source archive includes the testkit; the production
  service image does not. The launcher disables both canonical and compatibility
  mutation flags, irrespective of inherited environment values.
- [eSSVI dashboard](../services/essvi-dashboard/README.md) is optional and requires
  external Shaurya packages plus deployment-specific authentication/capture paths.
  Its offline test dependencies are separate from the kit's Python lock; it is not
  a self-contained portable dashboard deployment.

## Historical 2026-09-29 component import inventory

| Component | Previous location/status | Reusable kit disposition |
|---|---|---|
| Butterfly v2.5 controller and RV model | Repository and separately pinned installed copies | All three repository skills installed together; doctor detects source/copy drift |
| News filter | Repository; not in the current workspace-installed skill list | Included as a required installed skill |
| Master workflow, research composition, observation ingress | Local `Trading/code`, absent from GitHub | Source and synthetic tests now in `services/day-workflow` |
| Canonical accounting | Local review writer, simple summary projection and trade-event ledger | Same writer source/schema, configurable single data root; no actual ledger copied or initialized |
| Wide selection / tail stress | Local pure Python modules; tail stress needs NumPy | Source/tests included; current-only use, no historical research enabled |
| Forecast/outcome scoring helpers | Local pure Python helpers | Packaged for audit/shadow use only; cannot override current controller |
| Read-only account/position/chain/HF acquisition | Local MCP additions absent from GitHub | Three Node modules and tests packaged; explicit read-only mode required |
| Dhan MCP / margin / optional execution source | Already in repository | Locked dependencies, external runtime paths; execution remains disabled |
| Dhan browser login | Fixed Mac username, fixed PIN path, Chrome/CDP assumptions | Configurable PIN/binary/port; macOS adapter explicit, disabled by default |
| Legacy SSH login, position-check and outcome adapters | External/old host paths | **Excluded and not required by new kit**. Legacy scheduled collectors need replacement/review before migration; no implicit fallback to the old machine |
| Dated historical selection/review runners | Local scripts depending on saved snapshots | Excluded; not reusable/current-observation dependencies |
| Canonical financial state | Private `Trading/ledger` | External data directory; restoration is separate step 6, never replaced by public source or journal projections |
| Agent identity/policy/memory | Live OpenClaw workspace | Sanitized Dhandho template and adopted risk profile packaged; private memory deliberately excluded |
| Model/provider credentials and channel bindings | OpenClaw-managed private state | Must provision separately; setup preserves global config and adds no binding |
| Public MCP tunnel | Host ngrok + private domain/config | Optional adapter; no tunnel required for offline/local install; config stays private |
| macOS service management | MCP and tunnel launch agents have RunAtLoad/KeepAlive | Inventoried, not copied/activated; no service restart or scheduler migration |
| OpenClaw scheduled work | One enabled weekly Dhandho skill-collection review observed | Not trading monitoring; no jobs recreated. Older recorded outcome-job IDs were not present in the current filtered listing |

Imported source hashes (before portable path adaptation) are recorded in
`agent-kit/source-inventory.json`. No financial data is embedded in that manifest.

## Runtime and dependency policy

- **Python 3.12.13**, **Node 26.5.0**, **npm 11.17.0**: exact installer pins.
  Python 3.14.6 was also on the inspected host but is not the reproducible kit target.
- **OpenClaw 2026.9.5**: tested CLI registration/discovery contract, explicitly
  checked before `--register-agent`. Install the runtime separately; no automatic
  global upgrade or provider login. The kit itself can run offline without it.
- Python runtime requirements: NumPy 2.4.3 for the optional tail-stress helper;
  controllers, RV, accounting and installer otherwise use the standard library.
  `requirements.lock` pins hashes; `requirements-dev.lock` also pins pytest,
  PyYAML and transitive validation dependencies. Both target Python 3.12.
- Node direct dependencies are pinned to their already-locked versions:
  MCP express/node/server 2.0.0, SDK 1.31.0, dotenv 18.0.1, Express 5.2.1,
  playwright-core 1.63.0, Zod 4.6.5. `npm ci --ignore-scripts` installs the full lock.
- POSIX `fcntl`, owner-only permissions and fsync are required: **macOS and Linux
  (including WSL2)**. Native Windows is unsupported; do not claim otherwise.
- Python `zoneinfo` requires the host IANA timezone database with Asia/Kolkata.
- macOS browser recovery uses host Chrome, lsof, ps, and optional osascript dialog.
  Chrome is detected, not bundled or arbitrarily pinned against security updates.
  Browser UI changes/OTP can require a human. Linux/WSL uses a privately supplied
  Dhan Web token; unattended cross-platform login is not claimed.
- Git/GitHub CLI is needed for authorized source updates, not private journal persistence or offline
  controller tests. GitHub authentication is an external prerequisite.
- Docker is optional; its MCP-only image does not contain the full agent, browser,
  workspace or authoritative accounting state. No image build is implied by YAML tests.

## OpenClaw integration inventory

Observed bundled runtime plugins included browser, codex, model providers and
other host-wide integrations at 2026.9.5; memory-lancedb was 2026.9.4 and
clawlink-plugin 0.3.6. They are **not all trading dependencies**. The kit needs a
configured model provider, shell/files and current-news access. Do not replicate
unrelated speech, messaging or UI plugins to make installation appear complete.
Browser recovery is implemented by the MCP's Playwright adapter, not by requiring
all OpenClaw browser plugins. Connector, provider and private-memory readiness
must be checked separately from successful installation.

## Deliberately outside steps 1–5

Encrypted backup/restore, real state migration, tagged release distribution,
clean-device migration rehearsal, live token recovery on another OS, automatic
scheduler re-creation, unattended execution and full live research orchestration.
The source exposes read-only capture and shared writers; setup never invokes them.
