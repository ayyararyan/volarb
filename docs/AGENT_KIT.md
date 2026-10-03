# Portable VolArb agent kit

Rebuild software from GitHub; restore private continuity separately. The default
installation is **SHADOW**, creates no financial ledgers and starts no services.
This is steps 1–5 of portability, not a completed live-device migration.

## Three separate locations

| Location | Contents |
|---|---|
| Source checkout | Code, dependency locks, templates, reference skills, tests |
| Workspace | Installed skills and personal agent instructions; personal files preserved |
| Private data | `config.json`, `dhan/.env`, browser/token state, `Trading/ledger` and observations |

No private data directory may be inside the checkout. `VOLARB_SOURCE_DIR` selects
the controller/collector source. `VOLARB_DATA_DIR` selects the one private runtime
root: all accounting modules use `<data>/Trading/ledger`, observations use
`<data>/Trading/snapshots/dhan-workflow-private`, and MCP state uses `<data>/dhan`.
`DHAN_RUNTIME_DIR` optionally selects an existing MCP state location when running
the service directly. It does not redirect the financial ledger.

## Prerequisites

Install Python **3.12.13**, Node **26.5.0** and npm **11.17.0** using your existing
runtime manager. `.python-version`, `.node-version` and `agent-kit/manifest.json`
record the exact targets. The installer checks versions instead of changing global
runtimes or shell configuration. macOS/Linux/WSL2 only. See the
[dependency inventory](DEPENDENCY_INVENTORY.md) for external integrations and gaps.

For agent registration, separately install/authenticate **OpenClaw 2026.9.5** and
configure a model provider. Use existing OpenClaw onboarding; this kit does not
create a second agent framework or duplicate its credential storage.

## Repeatable setup

From a cloned or unpacked source tree:

```sh
python3.12 tools/volarb.py setup \
  --data-dir "$HOME/.local/share/volarb" \
  --workspace "$HOME/.openclaw/workspace/volarb-dhandho" \
  --agent-id volarb-dhandho
```

Setup creates a checkout-local `.venv`, installs hash-locked Python dependencies
and `npm ci --ignore-scripts`, installs all three skills, writes a sanitized
Dhandho profile and creates a **blank** private credentials template. No API call,
model login, broker call, ledger initialization, job registration, service start,
order or token recovery occurs. The run never touches existing Dhandho installation
paths unless you deliberately supply them, and conflicting managed files stop it.

- `--dev` installs the complete locked test/packaging dependencies.
- `--no-install` only prepares files; this is not a working dependency installation.
- `--mode read-only` enables explicit read-only capture commands through the
  launcher. It does not start capture, authenticate, activate execution or schedule.
- `--register-agent` explicitly adds this isolated workspace using OpenClaw's
  supported CLI, checks agent identity/workspace conflicts and verifies skill
  discovery. No channel bindings or jobs are added. Without this flag, registration
  is deliberately deferred; `doctor` reports it.

Repeat the same command safely. Existing personal `AGENTS.md`, `SOUL.md`,
`IDENTITY.md`, `USER.md` and `TOOLS.md` are retained, not reset. Skill/config/profile
conflicts stop before writing. Review and merge local edits manually; there is no
`--force` or silent upgrade. When changing mode or source location, review the
config and workspace install manifest together, or prepare a separate installation.
A dependency-install failure is reported and can be retried without replacing
personal files. Do not share a virtual environment across moved checkouts.

## Diagnostics

```sh
python3.12 tools/volarb.py doctor \
  --config "$HOME/.local/share/volarb/config.json"
```

JSON output includes actionable PASS/FAIL/WARN checks for runtimes, dependencies,
skill drift, workspace files, OpenClaw registration, private credential presence,
both canonical/compatibility mutation flags,
canonical ledger presence, browser support and GitHub CLI availability. It never
prints secrets. `READY` means the software checks passed—not account access,
provider authentication, broker connectivity or trading readiness. Exit 2 means
required checks failed; optional integration gaps remain warnings.

Use `--require-read-only` to make missing read-only mode, credentials and restored
canonical accounting files blocking. This still does not validate their business
contents or contact Dhan. Optional `--probe-mcp` checks loopback port 3000 `/healthz`
only; a healthy server is not authenticated broker access. No automatic repairs.

## Run with the correct paths

```sh
python3.12 tools/volarb.py run \
  --config "$HOME/.local/share/volarb/config.json" -- \
  python services/day-workflow/day_workflow.py --help
```

The launcher sets source/data paths, prepends `.venv/bin`, pins both
`DHAN_PROVIDER_COMMANDS_ENABLED=false` (canonical provider) and
`DHAN_EXECUTION_ENABLED=false` (compatibility executor), and disables browser recovery, and selects whether explicit read-only capture is allowed.
It is an environment launcher, **not a security sandbox** for arbitrary commands.
The profile expresses the adopted covenant; it is not authorization for trading.

After separately provisioning credentials, an explicitly selected read-only
installation can run `day_workflow.py --capture account` or `--capture position`.
HF collection is `node services/dhan-chatgpt-mcp/src/workflow-data-cli.mjs --scope hf`.
The shared accounting modules are the existing writers, not a new financial book.
Actual fill commits require explicit commands/evidence and are never setup effects.
Do not initialize blank ledgers to hide missing migrated records.

## Platform-specific Dhan authentication

For direct MCP service use outside the launcher, explicitly set
`VOLARB_OBSERVE_ENABLED=true` after provisioning; it defaults off.
Tokens are loaded from `<data>/dhan/.env`, never the shell's arbitrary working
folder. Keep it mode 600 in owner-only directories. The example is blank.
Browser recovery is off by default. Optional **macOS** recovery uses
`DHAN_PIN_FILE` (explicit private file), `DHAN_BROWSER_EXECUTABLE`, and
`DHAN_BROWSER_PORT`; no username is embedded in source. Native Mac mobile-number
setup is `npm run auth:setup` with the correct data environment. Linux/WSL needs a
privately provisioned Web token; OTP/captcha cannot be bypassed by this kit.

Build the [Dhan Dockerfile](../services/dhan-chatgpt-mcp/Dockerfile) from the
repository root (`docker build -f services/dhan-chatgpt-mcp/Dockerfile .`) so its
shared Execution Engine contracts are present. It serves MCP, uses `npm ci` and
non-root external `/data`; it does not bundle a desktop browser, enable execution, or migrate state.
The optional shell/ngrok launcher requires separate private tunnel configuration.
No launcher or background service is invoked by setup.

## Reusable archive

```sh
python3.12 tools/volarb.py package --output dist/volarb-agent-kit-0.1.0.zip
```

The explicit manifest roots include code, templates, tests, locks, canonical
architecture, Execution Engine contracts, execution environment definitions and
documentation. `execution-testkit` is included as a separate source-only test area,
never as a production dependency. Dhan's exported provider library imports the
shared `execution-engine` contracts, so those paths must travel together. Archive
documents are included as clearly marked non-operational history; no archive is
imported by setup or production code. The separate `agent/` research lab, prompts, workflow definitions and repository
navigation are included as source-only context. The lab retains its own dependency
lock and separate environment; kit setup does not install or execute it. Financial
history directories contain generated README omission notices only, directing
authorized operators to their configured private records—not dummy trades or copied journals. Raw lab runtime stores,
artifacts, databases and environments remain excluded. Private
state, credentials, personal memory, financial ledgers, raw evidence and historical
journals are excluded. Each archive contains SHA256SUMS.json for its source files.
Publicly viewable source does not make private runtime records distributable or
grant software-use rights beyond the root LICENSE. Packaging is not encrypted
backup or a tagged GitHub release.

## Validation

```sh
python3.12 tools/volarb.py setup --dev
.venv/bin/python -B -m unittest discover -s tests -v
.venv/bin/python -B -m unittest discover -s services/day-workflow -p 'test_*.py'
.venv/bin/python -B -m pytest -q skill/butterfly-market-outlook/tests
.venv/bin/python -B .github/skill-tools/check_rv_fixtures.py
npm test --prefix services/dhan-chatgpt-mcp
```

Tests are synthetic and use temporary directories. No credentials are required.
Encrypted state restoration and a real second-device migration rehearsal remain
separate next steps. Installing source never refreshes the currently running Mac.
