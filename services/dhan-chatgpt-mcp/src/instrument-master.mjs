const DEFAULT_MASTER_URL = 'https://images.dhan.co/api-data/api-scrip-master-detailed.csv';
const DEFAULT_TTL_MS = 6 * 60 * 60 * 1000;

const INDEX_ALIASES = {
  NIFTY: ['NIFTY', 'NIFTY50', 'NIFTY 50'],
  BANKNIFTY: ['BANKNIFTY', 'NIFTYBANK', 'NIFTY BANK', 'BANK NIFTY'],
  SENSEX: ['SENSEX', 'BSESENSEX', 'BSE SENSEX', 'S&P BSE SENSEX']
};

function normalizeToken(value) {
  return String(value ?? '')
    .toUpperCase()
    .replace(/&/g, 'AND')
    .replace(/[^A-Z0-9]+/g, '');
}

export function canonicalIndexSymbol(symbol) {
  const token = normalizeToken(symbol);
  for (const [canonical, aliases] of Object.entries(INDEX_ALIASES)) {
    if (aliases.some((alias) => normalizeToken(alias) === token)) return canonical;
  }
  throw new Error(`Unsupported index symbol: ${symbol}. Supported: NIFTY, BANKNIFTY, SENSEX.`);
}

export function parseCsv(text) {
  const rows = [];
  let row = [];
  let field = '';
  let quoted = false;

  for (let i = 0; i < text.length; i += 1) {
    const ch = text[i];
    if (quoted) {
      if (ch === '"') {
        if (text[i + 1] === '"') {
          field += '"';
          i += 1;
        } else {
          quoted = false;
        }
      } else {
        field += ch;
      }
      continue;
    }

    if (ch === '"') {
      quoted = true;
    } else if (ch === ',') {
      row.push(field);
      field = '';
    } else if (ch === '\n') {
      row.push(field.replace(/\r$/, ''));
      field = '';
      if (row.some((v) => v !== '')) rows.push(row);
      row = [];
    } else {
      field += ch;
    }
  }

  if (field.length || row.length) {
    row.push(field.replace(/\r$/, ''));
    if (row.some((v) => v !== '')) rows.push(row);
  }

  if (!rows.length) return [];
  const headers = rows[0].map((h) => h.trim());
  return rows.slice(1).map((values) => {
    const out = {};
    headers.forEach((header, idx) => {
      out[header] = values[idx] ?? '';
    });
    return out;
  });
}

function getField(row, names) {
  for (const name of names) {
    if (Object.prototype.hasOwnProperty.call(row, name) && row[name] !== '') return row[name];
  }
  const upperMap = new Map(Object.keys(row).map((key) => [key.toUpperCase(), key]));
  for (const name of names) {
    const key = upperMap.get(name.toUpperCase());
    if (key && row[key] !== '') return row[key];
  }
  return undefined;
}

function numeric(value) {
  const n = Number(value);
  return Number.isFinite(n) ? n : null;
}

function mode(values) {
  const counts = new Map();
  for (const value of values) {
    if (value === null || value === undefined || value === '') continue;
    const key = String(value);
    counts.set(key, (counts.get(key) ?? 0) + 1);
  }
  if (!counts.size) return null;
  return [...counts.entries()].sort((a, b) => b[1] - a[1])[0][0];
}

function rowUnderlyingSymbol(row) {
  return getField(row, ['UNDERLYING_SYMBOL', 'SEM_UNDERLYING_SYMBOL', 'UNDERLYING']);
}

function rowUnderlyingId(row) {
  return numeric(getField(row, ['UNDERLYING_SECURITY_ID', 'SEM_UNDERLYING_SECURITY_ID']));
}

function rowLotSize(row) {
  return numeric(getField(row, ['LOT_SIZE', 'SEM_LOT_UNITS']));
}

function rowInstrumentType(row) {
  return String(getField(row, ['INSTRUMENT_TYPE', 'SEM_EXCH_INSTRUMENT_TYPE', 'INSTRUMENT']) ?? '').toUpperCase();
}

function isLikelyOptionRow(row) {
  const t = rowInstrumentType(row);
  return t.includes('OPT') || t.includes('OPTION') || ['CE', 'PE'].includes(String(getField(row, ['OPTION_TYPE']) ?? '').toUpperCase());
}

export class InstrumentMaster {
  constructor({ url = DEFAULT_MASTER_URL, ttlMs = DEFAULT_TTL_MS, fetchFn = fetch } = {}) {
    this.url = url;
    this.ttlMs = ttlMs;
    this.fetchFn = fetchFn;
    this.cache = null;
    this.cachedAt = 0;
  }

  async getRows({ force = false } = {}) {
    const now = Date.now();
    if (!force && this.cache && now - this.cachedAt < this.ttlMs) return this.cache;

    const response = await this.fetchFn(this.url, {
      headers: { 'User-Agent': 'dhan-chatgpt-mcp/0.2.0' }
    });
    if (!response.ok) {
      throw new Error(`Could not fetch Dhan instrument master (${response.status} ${response.statusText})`);
    }
    const csv = await response.text();
    const rows = parseCsv(csv);
    if (!rows.length) throw new Error('Dhan instrument master was empty');
    this.cache = rows;
    this.cachedAt = now;
    return rows;
  }

  async resolveIndex(symbol) {
    const canonical = canonicalIndexSymbol(symbol);
    const aliases = new Set(INDEX_ALIASES[canonical].map(normalizeToken));
    const rows = await this.getRows();

    let matches = rows.filter((row) => aliases.has(normalizeToken(rowUnderlyingSymbol(row))));

    if (!matches.length) {
      matches = rows.filter((row) => {
        const text = [
          getField(row, ['SYMBOL_NAME', 'SM_SYMBOL_NAME']),
          getField(row, ['DISPLAY_NAME', 'SEM_CUSTOM_SYMBOL']),
          getField(row, ['SEM_TRADING_SYMBOL'])
        ].filter(Boolean).map(normalizeToken);
        return text.some((v) => aliases.has(v) || [...aliases].some((a) => v.startsWith(a)));
      });
    }

    const OPTION_CHAIN_UNDERLYINGS = {
      NIFTY: {
        underlyingScrip: 13,
        underlyingSeg: 'IDX_I'
      },
      BANKNIFTY: {
        underlyingScrip: 25,
        underlyingSeg: 'IDX_I'
      },
      SENSEX: {
        underlyingScrip: 1,
        underlyingSeg: 'BSE_FNO'
      }
    };

    const optionChainUnderlying = OPTION_CHAIN_UNDERLYINGS[canonical];

    if (!optionChainUnderlying) {
      throw new Error(`Unsupported index for Dhan option chain: ${canonical}`);
    }

    const {
      underlyingScrip,
      underlyingSeg
    } = optionChainUnderlying;

    const optionMatches = matches.filter(isLikelyOptionRow);
    const lotValues = (optionMatches.length ? optionMatches : matches)
      .map(rowLotSize)
      .filter((v) => Number.isFinite(v) && v > 0);
    const lotMode = mode(lotValues);

    return {
      symbol: canonical,
      underlyingScrip,
      underlyingSeg,
      lotSize: lotMode ? Number(lotMode) : null,
      matchedRows: matches.length,
      source: 'Dhan instrument master + Dhan option-chain mapping',
      masterUrl: this.url
    };
  }
}

export const DHAN_INSTRUMENT_MASTER_URL = DEFAULT_MASTER_URL;
