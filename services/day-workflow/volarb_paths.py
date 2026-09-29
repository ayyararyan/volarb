"""Portable source/data paths. Importing this module creates no files."""
import os
from pathlib import Path

SOURCE_ROOT = Path(os.environ.get('VOLARB_SOURCE_DIR', Path(__file__).resolve().parents[2])).expanduser().resolve()
DATA_ROOT = Path(os.environ.get('VOLARB_DATA_DIR', Path.home() / '.local/share/volarb')).expanduser().resolve()
TRADING_ROOT = DATA_ROOT / 'Trading'
EVIDENCE_ROOT = TRADING_ROOT / 'snapshots/dhan-workflow-private'
COLLECTOR = SOURCE_ROOT / 'services/dhan-chatgpt-mcp/src/workflow-data-cli.mjs'
