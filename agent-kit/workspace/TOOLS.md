# Portable tool routing

`volarb-install.json` provides absolute resolved paths for this device. From its
`source_dir`, use `python3 tools/volarb.py doctor --config <config_file>`.
Use `tools/volarb.py run --config <config_file> -- <command> ...` to pass the correct
source/data paths and the isolated Python and Node tool environment to commands.
The wrapper suppresses execution and browser recovery; it never starts a job.

Three installed skills: butterfly-market-outlook, market-news-signal-filter,
intraday-realized-volatility-forecast. The wide-selection implementation is
`services/day-workflow/wide_butterfly_selector.py`; historical model helpers remain
shadow-only and cannot override the current-data controller.

Dhan MCP source: `services/dhan-chatgpt-mcp`. Optional browser recovery is macOS-only;
Linux/WSL uses a privately provisioned Dhan Web token. Credentials belong in the
manifest's data directory under `dhan/.env` with owner-only permissions.
No credentials are supplied by this kit. Provider login, connector setup, memory
restoration and any later scheduler activation are separate operations.
