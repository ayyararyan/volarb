import 'dotenv/config';
import { ensureToken, invalidateTokenCache } from './web-token.mjs';
import { installExecutionOAuth } from './execution-oauth.mjs';
import { join } from 'node:path';
import { createExecutor, buildExecutionServer, bearerAuthorized } from './execution-mcp.mjs';
import { createMcpExpressApp } from '@modelcontextprotocol/express';
import { toNodeHandler } from '@modelcontextprotocol/node';
import { createMcpHandler, McpServer } from '@modelcontextprotocol/server';
import * as z from 'zod/v4';
import { DhanApiError, DhanClient } from './dhan-client.mjs';
import { basketMarginSchema, butterflyMarginSchema, basketMargin, checkButterflyMargin } from './margin-preflight.mjs';
import { InstrumentMaster } from './instrument-master.mjs';
import {
  analyzeOptionSurface,
  inferIronButterfly,
  matchLegGreeks,
  nearestExpiry,
  normalizeDhanChain
} from './surface-analytics.mjs';

const HOST = process.env.MCP_HOST || '127.0.0.1';
const PORT = Number(process.env.MCP_PORT || 3000);
const ALLOWED_HOSTS = (process.env.MCP_ALLOWED_HOSTS || '')
  .split(',')
  .map((v) => v.trim())
  .filter(Boolean);

const EXCHANGE_SEGMENTS = [
  'IDX_I',
  'NSE_EQ',
  'NSE_FNO',
  'NSE_CURRENCY',
  'BSE_EQ',
  'MCX_COMM',
  'BSE_CURRENCY',
  'BSE_FNO'
];

const exchangeSegmentSchema = z.enum(EXCHANGE_SEGMENTS);
const indexSymbolSchema = z.string().min(1).describe('Index name. Aliases such as NIFTY 50, NIFTY BANK and BSE SENSEX are accepted.');
const instrumentSchema = z.object({
  exchangeSegment: exchangeSegmentSchema.describe('Dhan exchange segment, e.g. NSE_FNO'),
  securityId: z.coerce.number().int().positive().describe('Dhan security ID')
});

function createDhanClient() {
  return new DhanClient({
    clientId: process.env.DHAN_CLIENT_ID,
    accessToken: process.env.DHAN_ACCESS_TOKEN,
    tokenProvider: async () => (await ensureToken({ allowBrowser: true })).token,
    onAuthRejected: invalidateTokenCache
  });
}

const instrumentMaster = new InstrumentMaster({
  url: process.env.DHAN_INSTRUMENT_MASTER_URL || undefined,
  ttlMs: Number(process.env.DHAN_INSTRUMENT_MASTER_TTL_MS || 21600000)
});

function ok(data) {
  const wrapped = { data };
  return {
    content: [{ type: 'text', text: JSON.stringify(wrapped) }],
    structuredContent: wrapped
  };
}

function fail(error) {
  const safe = error instanceof DhanApiError
    ? {
        error: error.message,
        status: error.status ?? null,
        details: error.payload ?? null
      }
    : {
        error: error instanceof Error ? error.message : String(error)
      };

  return {
    content: [{ type: 'text', text: JSON.stringify(safe) }],
    isError: true
  };
}

function readOnlyTool(server, name, config, handler) {
  server.registerTool(
    name,
    {
      ...config,
      annotations: {
        readOnlyHint: true,
        destructiveHint: false,
        idempotentHint: true,
        openWorldHint: true
      }
    },
    async (args) => {
      try {
        return ok(await handler(args));
      } catch (error) {
        return fail(error);
      }
    }
  );
}

function unwrapApiData(response) {
  return response?.data ?? response;
}

async function resolveAndExpiries(dhan, symbol) {
  const resolved = await instrumentMaster.resolveIndex(symbol);
  const expiryResponse = await dhan.getOptionExpiries(resolved);
  const expiries = unwrapApiData(expiryResponse);
  if (!Array.isArray(expiries)) throw new Error('Dhan did not return an expiry list');
  return { resolved, expiries };
}

async function chainBySymbol(dhan, { symbol, expiry, expiryIndex = 0 }) {
  const { resolved, expiries } = await resolveAndExpiries(dhan, symbol);
  const selectedExpiry = expiry || nearestExpiry(expiries, expiryIndex);
  if (!expiries.includes(selectedExpiry)) {
    throw new Error(`Expiry ${selectedExpiry} is not currently active for ${resolved.symbol}`);
  }
  const raw = await dhan.getOptionChain({
    underlyingScrip: resolved.underlyingScrip,
    underlyingSeg: resolved.underlyingSeg,
    expiry: selectedExpiry
  });
  const snapshot = normalizeDhanChain(raw, { symbol: resolved.symbol, expiry: selectedExpiry });
  return { resolved, expiries, selectedExpiry, raw, snapshot };
}

function buildServer() {
  const server = new McpServer({
    name: 'dhan-readonly',
    version: '0.3.0'
  });

  const dhan = createDhanClient();

  readOnlyTool(server, 'dhan_get_profile', {
    title: 'Get Dhan profile',
    description: 'Check DhanHQ API connectivity, token validity, active segments and data-plan status.'
  }, () => dhan.getProfile());

  readOnlyTool(server, 'dhan_get_funds', {
    title: 'Get Dhan funds',
    description: 'Get current available balance, utilised amount, collateral and withdrawable balance from Dhan.'
  }, () => dhan.getFunds());

  readOnlyTool(server, 'dhan_calculate_basket_margin', {
    title: 'Calculate Dhan basket margin (no orders)',
    description: 'Indicative combined margin for exact intraday option legs, including current positions and outstanding orders. This is NOT an affordability pass; use dhan_check_butterfly_margin for funds and sequence checks.',
    inputSchema: basketMarginSchema
  }, args => basketMargin(dhan, args));

  readOnlyTool(server, 'dhan_check_butterfly_margin', {
    title: 'Check butterfly entry affordability (no orders)',
    description: 'Resolve exact index iron-butterfly contracts and lots; get fresh funds, positions, orders and executable quotes; calculate every chosen entry-sequence prefix via Dhan basket margin. Default WINGS_FIRST; use entrySequence PAIRED_HEDGES to match the separate executor. Returns PASS/FAIL/UNVERIFIED with sequence-bound peak/final requirements and headroom. Requires explicit reserve for PASS. ENTRY ONLY; not recenter/exit simulation or trading approval. Never places orders.',
    inputSchema: butterflyMarginSchema
  }, args => checkButterflyMargin(dhan, instrumentMaster, args));

  readOnlyTool(server, 'dhan_get_positions', {
    title: 'Get Dhan positions',
    description: 'Get all current Dhan positions, including carry-forward F&O positions and realised/unrealised P&L.'
  }, () => dhan.getPositions());

  readOnlyTool(server, 'dhan_get_holdings', {
    title: 'Get Dhan holdings',
    description: 'Get demat holdings from Dhan, including available, T1 and collateral quantities.'
  }, () => dhan.getHoldings());

  readOnlyTool(server, 'dhan_get_orders', {
    title: 'Get Dhan orders',
    description: 'Get the current trading-day Dhan order book. This tool cannot place, modify or cancel orders.'
  }, () => dhan.getOrders());

  readOnlyTool(server, 'dhan_get_trades', {
    title: 'Get Dhan trades',
    description: 'Get all trades executed in the current trading day from Dhan.'
  }, () => dhan.getTrades());

  readOnlyTool(server, 'dhan_get_ltp', {
    title: 'Get live LTP',
    description: 'Fetch current last-traded prices for up to 1000 Dhan instruments in one snapshot request.',
    inputSchema: z.object({
      instruments: z.array(instrumentSchema).min(1).max(1000)
    })
  }, ({ instruments }) => dhan.getLtp(instruments));

  readOnlyTool(server, 'dhan_get_market_quote', {
    title: 'Get market quote and depth',
    description: 'Fetch Dhan quote snapshots including LTP, OHLC, OI, volume and market depth where available.',
    inputSchema: z.object({
      instruments: z.array(instrumentSchema).min(1).max(1000)
    })
  }, ({ instruments }) => dhan.getQuote(instruments));

  readOnlyTool(server, 'dhan_get_option_expiries', {
    title: 'Get option expiries by security ID',
    description: 'Get active option expiry dates for an underlying instrument from Dhan using a Dhan security ID.',
    inputSchema: z.object({
      underlyingScrip: z.coerce.number().int().positive().describe('Security ID of the underlying instrument'),
      underlyingSeg: exchangeSegmentSchema.describe('Underlying segment; index underlyings normally use IDX_I')
    })
  }, (args) => dhan.getOptionExpiries(args));

  readOnlyTool(server, 'dhan_get_option_chain', {
    title: 'Get option chain by security ID',
    description: 'Get the full Dhan option chain for one underlying and expiry using a Dhan security ID.',
    inputSchema: z.object({
      underlyingScrip: z.coerce.number().int().positive().describe('Security ID of the underlying instrument'),
      underlyingSeg: exchangeSegmentSchema.describe('Underlying segment; index underlyings normally use IDX_I'),
      expiry: z.string().regex(/^\d{4}-\d{2}-\d{2}$/).describe('Expiry date in YYYY-MM-DD format')
    })
  }, (args) => dhan.getOptionChain(args));

  readOnlyTool(server, 'dhan_resolve_underlying', {
    title: 'Resolve index symbol',
    description: 'Resolve NIFTY, BANKNIFTY or SENSEX to the current Dhan underlying security ID and lot size using the live Dhan instrument master. No security ID is required from the user.',
    inputSchema: z.object({ symbol: indexSymbolSchema })
  }, ({ symbol }) => instrumentMaster.resolveIndex(symbol));

  readOnlyTool(server, 'dhan_get_option_expiries_by_symbol', {
    title: 'Get option expiries by symbol',
    description: 'Get active expiries for NIFTY, BANKNIFTY or SENSEX without requiring a security ID.',
    inputSchema: z.object({ symbol: indexSymbolSchema })
  }, async ({ symbol }) => {
    const { resolved, expiries } = await resolveAndExpiries(dhan, symbol);
    return { symbol: resolved.symbol, underlying: resolved, expiries };
  });

  readOnlyTool(server, 'dhan_get_option_chain_by_symbol', {
    title: 'Get full option chain by symbol',
    description: 'Get the complete Dhan option chain for NIFTY, BANKNIFTY or SENSEX. If expiry is omitted, the nearest active expiry is selected automatically. Returns normalized IV, Greeks, OI, change-OI, volume and top bid/ask for every strike.',
    inputSchema: z.object({
      symbol: indexSymbolSchema,
      expiry: z.string().regex(/^\d{4}-\d{2}-\d{2}$/).optional(),
      expiryIndex: z.coerce.number().int().min(0).max(20).default(0).describe('0=nearest active expiry, 1=next expiry, etc. Used only when expiry is omitted.')
    })
  }, async (args) => {
    const result = await chainBySymbol(dhan, args);
    return {
      symbol: result.resolved.symbol,
      underlying: result.resolved,
      expiry: result.selectedExpiry,
      expiries: result.expiries,
      surface: result.snapshot
    };
  });

  readOnlyTool(server, 'dhan_analyze_option_surface', {
    title: 'Analyze option surface',
    description: 'Resolve the index symbol, fetch the full Dhan option chain, and calculate ATM IV/straddle, forward, skew, smile curvature, 25-delta risk reversal/butterfly, risk-neutral distribution, OI concentrations and liquidity. Optionally map an existing butterfly onto the distribution.',
    inputSchema: z.object({
      symbol: indexSymbolSchema,
      expiry: z.string().regex(/^\d{4}-\d{2}-\d{2}$/).optional(),
      expiryIndex: z.coerce.number().int().min(0).max(20).default(0),
      riskFreeRate: z.coerce.number().min(-0.05).max(0.25).default(0.06),
      butterfly: z.object({
        lower: z.coerce.number(),
        center: z.coerce.number(),
        upper: z.coerce.number(),
        debit: z.coerce.number().optional().describe('Equivalent long-fly debit in index points. For a symmetric iron fly, width minus entry credit.')
      }).optional()
    })
  }, async (args) => {
    const result = await chainBySymbol(dhan, args);
    return {
      symbol: result.resolved.symbol,
      underlying: result.resolved,
      expiry: result.selectedExpiry,
      analytics: analyzeOptionSurface(result.snapshot, {
        expiry: result.selectedExpiry,
        riskFreeRate: args.riskFreeRate,
        butterfly: args.butterfly ?? null
      })
    };
  });

  readOnlyTool(server, 'dhan_get_butterfly_state', {
    title: 'Get live butterfly state',
    description: 'Read the current Dhan positions for NIFTY, BANKNIFTY or SENSEX, recognize a carried iron butterfly when possible, fetch its full expiry option surface, and return position geometry, live leg IV/Greeks/OI/bid-ask, net Greeks and distribution mapping. This is the preferred backend tool for the Butterfly Market Outlook workflow.',
    inputSchema: z.object({
      symbol: indexSymbolSchema,
      riskFreeRate: z.coerce.number().min(-0.05).max(0.25).default(0.06)
    })
  }, async ({ symbol, riskFreeRate }) => {
    const resolved = await instrumentMaster.resolveIndex(symbol);
    const positionsResponse = await dhan.getPositions();
    const positions = unwrapApiData(positionsResponse);
    if (!Array.isArray(positions)) throw new Error('Dhan did not return a position array');

    const fly = inferIronButterfly(positions, resolved.symbol);
    if (!fly) {
      return {
        symbol: resolved.symbol,
        underlying: resolved,
        openButterfly: null,
        message: `No open ${resolved.symbol} option position was found.`
      };
    }

    const expiry = fly.expiry;
    const raw = await dhan.getOptionChain({
      underlyingScrip: resolved.underlyingScrip,
      underlyingSeg: resolved.underlyingSeg,
      expiry
    });
    const snapshot = normalizeDhanChain(raw, { symbol: resolved.symbol, expiry });
    const matched = matchLegGreeks(snapshot, fly.legs);
    const butterfly = fly.recognized && Number.isFinite(fly.equivalent_long_fly_debit_points)
      ? { lower: fly.lower, center: fly.center, upper: fly.upper, debit: fly.equivalent_long_fly_debit_points }
      : (fly.recognized ? { lower: fly.lower, center: fly.center, upper: fly.upper } : null);
    const analytics = analyzeOptionSurface(snapshot, { expiry, riskFreeRate, butterfly });

    return {
      symbol: resolved.symbol,
      underlying: resolved,
      openButterfly: fly,
      liveLegState: matched,
      surface: analytics
    };
  });

  return server;
}

const execution = createExecutor({ broker: createDhanClient(), master: instrumentMaster });
const executionHandler = createMcpHandler(() => buildExecutionServer(execution.executor, execution.readiness, execution.enabled));
const executionNodeHandler = toNodeHandler(executionHandler);

const handler = createMcpHandler(() => buildServer());
const nodeHandler = toNodeHandler(handler);

const appOptions = { host: HOST };
if (HOST === '0.0.0.0' && ALLOWED_HOSTS.length > 0) {
  appOptions.allowedHosts = ALLOWED_HOSTS;
}

const app = createMcpExpressApp(appOptions);
// Only local reverse proxies (ngrok) may supply the client IP used by OAuth rate limits.
app.set('trust proxy', 'loopback');

app.get('/healthz', (_req, res) => {
  res.json({ ok: true, service: 'dhan-chatgpt-mcp', version: '0.3.0' });
});

const oauth = process.env.MCP_PUBLIC_ORIGIN && execution.token ? installExecutionOAuth(app, {
  issuer: process.env.MCP_PUBLIC_ORIGIN, ownerToken: execution.token,
  dir: join(execution.executor.store.dir, 'oauth'),
  allowedRedirects: (process.env.MCP_OAUTH_REDIRECT_URIS || '').split(',').filter(Boolean)
}) : null;

app.all('/execution/mcp', (req, res) => {
  if (!bearerAuthorized(req.headers.authorization, execution.token)) {
    if (oauth) return oauth.guard(req, res, () => { void executionNodeHandler(req, res, req.body); });
    res.setHeader('WWW-Authenticate', 'Bearer realm="dhan-execution"');
    return res.status(401).json({ error: 'Authenticated execution client required' });
  }
  void executionNodeHandler(req, res, req.body);
});

app.all('/mcp', (req, res) => {
  void nodeHandler(req, res, req.body);
});

const listener = app.listen(PORT, HOST, () => {
  console.log(`Dhan MCP listening on http://${HOST}:${PORT}/mcp`);
  console.log(`Health check: http://${HOST}:${PORT}/healthz`);
});

async function shutdown(signal) {
  console.log(`Received ${signal}; shutting down.`);
  for (const job of Object.values(execution.executor.store.data.jobs)) {
    if (job.status === 'RUNNING') execution.executor.stop(job.id);
  }
  if (execution.executor.worker) await execution.executor.worker;
  listener.close(async () => {
    await handler.close();
    await executionHandler.close();
    execution.release();
    process.exit(0);
  });
}

process.on('SIGINT', () => void shutdown('SIGINT'));
process.on('SIGTERM', () => void shutdown('SIGTERM'));
