function num(value) {
  const n = Number(value);
  return Number.isFinite(n) ? n : null;
}

function normalizeIv(value) {
  const v = num(value);
  if (v === null || v <= 0) return null;
  return v > 2 ? v / 100 : v;
}

function unwrapPayload(raw) {
  let p = raw;
  for (let i = 0; i < 4; i += 1) {
    if (p && typeof p === 'object' && p.data && !p.oc) p = p.data;
    else break;
  }
  return p;
}

function mapSide(side = {}) {
  const oi = num(side.oi) ?? 0;
  const previousOi = num(side.previous_oi) ?? 0;
  return {
    security_id: num(side.security_id),
    ltp: num(side.last_price),
    bid: num(side.top_bid_price),
    ask: num(side.top_ask_price),
    bid_qty: num(side.top_bid_quantity),
    ask_qty: num(side.top_ask_quantity),
    iv: normalizeIv(side.implied_volatility),
    oi,
    previous_oi: previousOi,
    change_oi: oi - previousOi,
    volume: num(side.volume) ?? 0,
    previous_volume: num(side.previous_volume) ?? 0,
    average_price: num(side.average_price),
    greeks: {
      delta: num(side.greeks?.delta),
      theta: num(side.greeks?.theta),
      gamma: num(side.greeks?.gamma),
      vega: num(side.greeks?.vega)
    }
  };
}

export function normalizeDhanChain(raw, { symbol, expiry, retrievedAt = new Date().toISOString() } = {}) {
  const payload = unwrapPayload(raw);
  if (!payload?.oc || payload.last_price === undefined) {
    throw new Error('Unexpected Dhan option-chain payload');
  }

  const chain = Object.entries(payload.oc)
    .map(([strike, row]) => ({
      strike: Number(strike),
      call: mapSide(row?.ce ?? {}),
      put: mapSide(row?.pe ?? {})
    }))
    .filter((row) => Number.isFinite(row.strike))
    .sort((a, b) => a.strike - b.strike);

  return {
    provider: 'DhanHQ',
    symbol: symbol ?? null,
    expiry: expiry ?? null,
    underlying_value: Number(payload.last_price),
    retrieved_at_utc: retrievedAt,
    chain
  };
}

function pickMid(side) {
  const bid = num(side?.bid);
  const ask = num(side?.ask);
  if (bid !== null && ask !== null && bid > 0 && ask >= bid) return 0.5 * (bid + ask);
  const ltp = num(side?.ltp);
  return ltp !== null && ltp > 0 ? ltp : null;
}

function spreadFraction(side) {
  const bid = num(side?.bid);
  const ask = num(side?.ask);
  if (bid === null || ask === null || bid <= 0 || ask < bid) return null;
  const mid = 0.5 * (bid + ask);
  return mid > 0 ? (ask - bid) / mid : null;
}

function median(values) {
  const xs = values.filter((v) => Number.isFinite(v)).sort((a, b) => a - b);
  if (!xs.length) return null;
  const m = Math.floor(xs.length / 2);
  return xs.length % 2 ? xs[m] : 0.5 * (xs[m - 1] + xs[m]);
}

function weightedMedian(entries) {
  const xs = entries.filter((x) => Number.isFinite(x.value) && Number.isFinite(x.weight) && x.weight > 0)
    .sort((a, b) => a.value - b.value);
  if (!xs.length) return null;
  const total = xs.reduce((s, x) => s + x.weight, 0);
  let acc = 0;
  for (const x of xs) {
    acc += x.weight;
    if (acc >= total / 2) return x.value;
  }
  return xs[xs.length - 1].value;
}

function estimateForward(snapshot, r = 0.06, dte = 0) {
  const spot = snapshot.underlying_value;
  const t = Math.max(dte, 0) / 365;
  const df = Math.exp(-r * t);
  const candidates = [];

  for (const row of snapshot.chain) {
    if (Math.abs(row.strike / spot - 1) > 0.04) continue;
    const c = pickMid(row.call);
    const p = pickMid(row.put);
    if (c === null || p === null) continue;
    const f = row.strike + (c - p) / Math.max(df, 1e-12);
    const spreadC = spreadFraction(row.call) ?? 0.25;
    const spreadP = spreadFraction(row.put) ?? 0.25;
    const liq = Math.log1p((row.call.oi ?? 0) + (row.put.oi ?? 0))
      + Math.log1p((row.call.volume ?? 0) + (row.put.volume ?? 0));
    const weight = Math.max(1, liq) / (1 + 5 * (spreadC + spreadP));
    if (Number.isFinite(f) && f > 0) candidates.push({ value: f, weight });
  }

  return weightedMedian(candidates) ?? spot;
}

function calendarDays(expiry, asof = new Date()) {
  if (!expiry) return 0;
  const end = new Date(`${expiry}T00:00:00+05:30`);
  if (Number.isNaN(end.getTime())) return 0;
  return Math.max((end.getTime() - asof.getTime()) / 86400000, 0);
}

function solve3x3(a, b) {
  const m = a.map((row, i) => [...row, b[i]]);
  for (let col = 0; col < 3; col += 1) {
    let pivot = col;
    for (let r = col + 1; r < 3; r += 1) if (Math.abs(m[r][col]) > Math.abs(m[pivot][col])) pivot = r;
    if (Math.abs(m[pivot][col]) < 1e-14) return null;
    [m[col], m[pivot]] = [m[pivot], m[col]];
    const div = m[col][col];
    m[col] = m[col].map((x) => x / div);
    for (let r = 0; r < 3; r += 1) {
      if (r === col) continue;
      const f = m[r][col];
      m[r] = m[r].map((x, j) => x - f * m[col][j]);
    }
  }
  return [m[0][3], m[1][3], m[2][3]];
}

function quadraticFit(points) {
  if (points.length < 3) return null;
  let s0 = 0, sx = 0, sx2 = 0, sx3 = 0, sx4 = 0, sy = 0, sxy = 0, sx2y = 0;
  for (const { x, y, w } of points) {
    const ww = Math.max(w, 1e-6);
    const x2 = x * x;
    s0 += ww; sx += ww * x; sx2 += ww * x2; sx3 += ww * x2 * x; sx4 += ww * x2 * x2;
    sy += ww * y; sxy += ww * x * y; sx2y += ww * x2 * y;
  }
  return solve3x3(
    [[s0, sx, sx2], [sx, sx2, sx3], [sx2, sx3, sx4]],
    [sy, sxy, sx2y]
  );
}

function ivAt(fit, x) {
  if (!fit) return null;
  const [a, b, c] = fit;
  const v = a + b * x + c * x * x;
  return v > 0 ? v : null;
}

function liquidityWeight(row, forward) {
  const side = row.strike < forward ? row.put : row.call;
  const oi = num(side?.oi) ?? 0;
  const volume = num(side?.volume) ?? 0;
  const spread = spreadFraction(side);
  const penalty = spread === null ? 1 : 1 / (1 + 10 * spread);
  return Math.max(1, Math.log1p(oi) + Math.log1p(volume)) * penalty;
}

function weightedIsotonicDecreasing(values) {
  const blocks = [];
  values.forEach((v, i) => {
    blocks.push({ start: i, end: i, mean: -v, weight: 1 });
    while (blocks.length >= 2 && blocks[blocks.length - 2].mean > blocks[blocks.length - 1].mean) {
      const b2 = blocks.pop();
      const b1 = blocks.pop();
      const weight = b1.weight + b2.weight;
      blocks.push({
        start: b1.start,
        end: b2.end,
        mean: (b1.mean * b1.weight + b2.mean * b2.weight) / weight,
        weight
      });
    }
  });
  const out = new Array(values.length).fill(0);
  for (const block of blocks) {
    for (let i = block.start; i <= block.end; i += 1) out[i] = -block.mean;
  }
  return out;
}

function buildCallCurve(snapshot, forward, r, dte) {
  const t = Math.max(dte, 0) / 365;
  const df = Math.exp(-r * t);
  return snapshot.chain.map((row) => {
    const cm = pickMid(row.call);
    const pm = pickMid(row.put);
    let callMark = null;
    if (row.strike < forward && pm !== null) callMark = pm + df * (forward - row.strike);
    else if (row.strike >= forward && cm !== null) callMark = cm;
    else if (cm !== null) callMark = cm;
    else if (pm !== null) callMark = pm + df * (forward - row.strike);
    return { strike: row.strike, callMark };
  }).filter((x) => x.callMark !== null && x.callMark >= 0);
}

function riskNeutralDistribution(snapshot, forward, r, dte) {
  const curve = buildCallCurve(snapshot, forward, r, dte).sort((a, b) => a.strike - b.strike);
  if (curve.length < 4) return null;
  const t = Math.max(dte, 0) / 365;
  const df = Math.exp(-r * t);
  const mids = [];
  const surv = [];
  for (let i = 0; i < curve.length - 1; i += 1) {
    const dk = curve[i + 1].strike - curve[i].strike;
    if (dk <= 0) continue;
    const slope = (curve[i + 1].callMark - curve[i].callMark) / dk;
    mids.push(0.5 * (curve[i].strike + curve[i + 1].strike));
    surv.push(Math.min(1, Math.max(0, -slope / Math.max(df, 1e-12))));
  }
  if (mids.length < 3) return null;
  const iso = weightedIsotonicDecreasing(surv).map((x) => Math.min(1, Math.max(0, x)));
  const masses = [];
  const stepLo = curve[1].strike - curve[0].strike;
  const stepHi = curve[curve.length - 1].strike - curve[curve.length - 2].strike;
  masses.push([Math.max(0, mids[0] - 0.5 * stepLo), Math.max(0, 1 - iso[0])]);
  for (let i = 0; i < mids.length - 1; i += 1) {
    masses.push([0.5 * (mids[i] + mids[i + 1]), Math.max(0, iso[i] - iso[i + 1])]);
  }
  masses.push([mids[mids.length - 1] + 0.5 * stepHi, Math.max(0, iso[iso.length - 1])]);
  const total = masses.reduce((s, [, p]) => s + p, 0);
  if (total <= 0) return null;
  return masses.map(([s, p]) => [s, p / total]);
}

function quantile(dist, q) {
  if (!dist?.length) return null;
  let c = 0;
  for (const [s, p] of [...dist].sort((a, b) => a[0] - b[0])) {
    c += p;
    if (c >= q) return s;
  }
  return dist[dist.length - 1][0];
}

function probLe(dist, level) {
  return dist?.reduce((s, [x, p]) => s + (x <= level ? p : 0), 0) ?? null;
}

function probGe(dist, level) {
  return dist?.reduce((s, [x, p]) => s + (x >= level ? p : 0), 0) ?? null;
}

function delta25Metrics(snapshot) {
  const puts = [];
  const calls = [];
  for (const row of snapshot.chain) {
    const pd = num(row.put?.greeks?.delta);
    const cd = num(row.call?.greeks?.delta);
    const piv = row.put?.iv;
    const civ = row.call?.iv;
    if (pd !== null && piv && piv > 0) puts.push({ diff: Math.abs(Math.abs(pd) - 0.25), strike: row.strike, iv: piv });
    if (cd !== null && civ && civ > 0) calls.push({ diff: Math.abs(cd - 0.25), strike: row.strike, iv: civ });
  }
  if (!puts.length || !calls.length) return { put25_strike: null, call25_strike: null, put25_iv: null, call25_iv: null, rr25_vp: null };
  puts.sort((a, b) => a.diff - b.diff);
  calls.sort((a, b) => a.diff - b.diff);
  const p = puts[0], c = calls[0];
  return {
    put25_strike: p.strike,
    call25_strike: c.strike,
    put25_iv: p.iv,
    call25_iv: c.iv,
    rr25_vp: (c.iv - p.iv) * 100
  };
}

function lossStats(dist, { lower, center, upper, debit }) {
  if (!dist?.length || ![lower, center, upper, debit].every(Number.isFinite)) return null;
  const payoff = (s) => Math.max(s - lower, 0) - 2 * Math.max(s - center, 0) + Math.max(s - upper, 0) - debit;
  const losses = [];
  let pLoss = 0, expectedLoss = 0;
  for (const [s, p] of dist) {
    const pnl = payoff(s);
    if (pnl < 0) {
      const loss = -pnl;
      pLoss += p;
      expectedLoss += p * loss;
      losses.push({ loss, p });
    }
  }
  losses.sort((a, b) => b.loss - a.loss);
  let tailP = 0, tailLoss = 0;
  for (const x of losses) {
    if (tailP >= 0.05) break;
    const take = Math.min(x.p, 0.05 - tailP);
    tailP += take;
    tailLoss += take * x.loss;
  }
  return {
    p_loss: pLoss,
    expected_loss_points: expectedLoss,
    cvar95_points: tailP > 0 ? tailLoss / tailP : 0
  };
}

function topOi(snapshot, sideName, n = 5) {
  return snapshot.chain
    .map((row) => ({
      strike: row.strike,
      oi: num(row[sideName]?.oi) ?? 0,
      change_oi: num(row[sideName]?.change_oi) ?? 0,
      volume: num(row[sideName]?.volume) ?? 0
    }))
    .filter((x) => x.oi > 0)
    .sort((a, b) => b.oi - a.oi)
    .slice(0, n);
}

export function analyzeOptionSurface(snapshot, { expiry = snapshot.expiry, riskFreeRate = 0.06, butterfly = null, asof = new Date() } = {}) {
  const spot = snapshot.underlying_value;
  const dte = calendarDays(expiry, asof);
  const forward = estimateForward(snapshot, riskFreeRate, dte);
  const points = [];
  for (const row of snapshot.chain) {
    const iv = row.strike < forward ? row.put?.iv : row.call?.iv;
    if (!iv || iv <= 0) continue;
    const x = Math.log(row.strike / forward);
    if (Math.abs(x) > 0.08) continue;
    points.push({ x, y: iv, w: liquidityWeight(row, forward) });
  }
  const fit = quadraticFit(points);
  const atm = [...snapshot.chain].sort((a, b) => Math.abs(a.strike - forward) - Math.abs(b.strike - forward))[0];
  const atmStrike = atm?.strike ?? null;
  const atmCallIv = atm?.call?.iv ?? null;
  const atmPutIv = atm?.put?.iv ?? null;
  const atmIv = (atmCallIv && atmPutIv) ? 0.5 * (atmCallIv + atmPutIv) : (atmCallIv ?? atmPutIv ?? ivAt(fit, 0));
  const callMid = atm ? pickMid(atm.call) : null;
  const putMid = atm ? pickMid(atm.put) : null;
  const straddle = callMid !== null && putMid !== null ? callMid + putMid : null;
  const ivDn = ivAt(fit, -0.02), ivUp = ivAt(fit, 0.02), iv0 = ivAt(fit, 0);
  const d25 = delta25Metrics(snapshot);
  const bf25 = d25.put25_iv && d25.call25_iv && atmIv ? (0.5 * (d25.put25_iv + d25.call25_iv) - atmIv) * 100 : null;
  const dist = riskNeutralDistribution(snapshot, forward, riskFreeRate, dte);
  const mode = dist?.length ? dist.reduce((a, b) => b[1] > a[1] ? b : a) : null;

  const nearRows = snapshot.chain.filter((r) => Math.abs(r.strike / spot - 1) <= 0.03);
  const spreadValues = nearRows.flatMap((r) => [spreadFraction(r.call), spreadFraction(r.put)]).filter(Number.isFinite);
  const liveQuoteSides = nearRows.flatMap((r) => [r.call, r.put]);
  const twoSided = liveQuoteSides.filter((s) => spreadFraction(s) !== null).length;

  const result = {
    provider: snapshot.provider,
    symbol: snapshot.symbol,
    expiry,
    retrieved_at_utc: snapshot.retrieved_at_utc,
    spot,
    forward,
    dte_calendar: dte,
    strikes: snapshot.chain.length,
    surface_points: points.length,
    atm: {
      strike: atmStrike,
      iv: atmIv,
      call_iv: atmCallIv,
      put_iv: atmPutIv,
      straddle
    },
    smile: {
      skew_slope: fit?.[1] ?? null,
      curvature_coeff: fit?.[2] ?? null,
      downside_minus_upside_iv_2pct_vp: ivDn !== null && ivUp !== null ? (ivDn - ivUp) * 100 : null,
      symmetric_wing_richness_2pct_vp: ivDn !== null && ivUp !== null && iv0 !== null ? (0.5 * (ivDn + ivUp) - iv0) * 100 : null,
      ...d25,
      bf25_vp: bf25
    },
    risk_neutral_distribution: dist ? {
      q10: quantile(dist, 0.10),
      median: quantile(dist, 0.50),
      q90: quantile(dist, 0.90),
      mode_bucket: mode?.[0] ?? null,
      mode_bucket_probability: mode?.[1] ?? null,
      p_down_1pct: probLe(dist, spot * 0.99),
      p_up_1pct: probGe(dist, spot * 1.01),
      p_down_1_5pct: probLe(dist, spot * 0.985),
      p_up_1_5pct: probGe(dist, spot * 1.015)
    } : null,
    positioning: {
      total_call_oi: snapshot.chain.reduce((s, r) => s + (num(r.call?.oi) ?? 0), 0),
      total_put_oi: snapshot.chain.reduce((s, r) => s + (num(r.put?.oi) ?? 0), 0),
      top_call_oi: topOi(snapshot, 'call'),
      top_put_oi: topOi(snapshot, 'put')
    },
    liquidity: {
      near_atm_two_sided_quote_ratio: liveQuoteSides.length ? twoSided / liveQuoteSides.length : null,
      near_atm_median_relative_spread: median(spreadValues)
    }
  };

  if (butterfly && dist) {
    const { lower, center, upper, debit } = butterfly;
    const mapping = {
      lower,
      center,
      upper,
      center_minus_rnd_median: Number.isFinite(center) ? center - quantile(dist, 0.50) : null,
      p_below_lower: Number.isFinite(lower) ? probLe(dist, lower) : null,
      p_above_upper: Number.isFinite(upper) ? probGe(dist, upper) : null
    };
    if (Number.isFinite(mapping.p_below_lower) && Number.isFinite(mapping.p_above_upper)) {
      mapping.p_outside_wings = mapping.p_below_lower + mapping.p_above_upper;
      mapping.p_inside_wings = Math.max(0, 1 - mapping.p_outside_wings);
    }
    if ([lower, center, upper, debit].every(Number.isFinite)) Object.assign(mapping, lossStats(dist, { lower, center, upper, debit }));
    result.butterfly_mapping = mapping;
  }

  return result;
}

export function nearestExpiry(expiries, index = 0) {
  const dates = (expiries ?? []).map(String).filter((x) => /^\d{4}-\d{2}-\d{2}$/.test(x)).sort();
  if (!dates.length) throw new Error('No active option expiries returned by Dhan');
  return dates[Math.min(Math.max(index, 0), dates.length - 1)];
}

export function inferIronButterfly(positions, canonicalSymbol) {
  const token = String(canonicalSymbol).toUpperCase();
  const legs = (positions ?? []).filter((p) => {
    const qty = Number(p.netQty ?? 0);
    return qty !== 0 && String(p.tradingSymbol ?? '').toUpperCase().includes(token) && ['CALL', 'PUT'].includes(String(p.drvOptionType ?? '').toUpperCase());
  });
  if (!legs.length) return null;

  const byExpiry = new Map();
  for (const leg of legs) {
    const exp = leg.drvExpiryDate;
    if (!byExpiry.has(exp)) byExpiry.set(exp, []);
    byExpiry.get(exp).push(leg);
  }
  const [expiry, group] = [...byExpiry.entries()].sort((a, b) => String(a[0]).localeCompare(String(b[0])))[0];
  const shortCalls = group.filter((p) => p.netQty < 0 && p.drvOptionType === 'CALL');
  const shortPuts = group.filter((p) => p.netQty < 0 && p.drvOptionType === 'PUT');
  const longCalls = group.filter((p) => p.netQty > 0 && p.drvOptionType === 'CALL');
  const longPuts = group.filter((p) => p.netQty > 0 && p.drvOptionType === 'PUT');
  const centerPair = [];
  for (const c of shortCalls) for (const p of shortPuts) if (Number(c.drvStrikePrice) === Number(p.drvStrikePrice)) centerPair.push([c, p]);
  if (!centerPair.length || !longCalls.length || !longPuts.length) {
    return { symbol: canonicalSymbol, expiry, recognized: false, legs: group };
  }
  const [sc, sp] = centerPair[0];
  const center = Number(sc.drvStrikePrice);
  const lp = longPuts.filter((p) => Number(p.drvStrikePrice) < center).sort((a, b) => Number(b.drvStrikePrice) - Number(a.drvStrikePrice))[0];
  const lc = longCalls.filter((p) => Number(p.drvStrikePrice) > center).sort((a, b) => Number(a.drvStrikePrice) - Number(b.drvStrikePrice))[0];
  if (!lp || !lc) return { symbol: canonicalSymbol, expiry, recognized: false, legs: group };

  const lower = Number(lp.drvStrikePrice), upper = Number(lc.drvStrikePrice);
  const leftWidth = center - lower, rightWidth = upper - center;
  const quantities = [lp, sp, sc, lc].map((p) => Math.abs(Number(p.netQty)));
  const baseQty = Math.min(...quantities.filter((q) => q > 0));

  const perUnitEntry = [lp, sp, sc, lc].reduce((sum, p) => {
    const qtyRatio = Number(p.netQty) / baseQty;
    const avg = p.netQty > 0 ? Number(p.buyAvg ?? p.costPrice ?? 0) : Number(p.sellAvg ?? p.costPrice ?? 0);
    return sum - qtyRatio * avg;
  }, 0);
  // Positive perUnitEntry is net entry credit for the iron fly.
  const symmetricWidth = Math.abs(leftWidth - rightWidth) < 1e-9 ? leftWidth : null;
  const equivalentDebit = symmetricWidth !== null ? symmetricWidth - perUnitEntry : null;

  return {
    symbol: canonicalSymbol,
    expiry,
    recognized: true,
    structure: 'iron_butterfly',
    lower,
    center,
    upper,
    left_width: leftWidth,
    right_width: rightWidth,
    quantity: baseQty,
    entry_credit_points: perUnitEntry,
    equivalent_long_fly_debit_points: equivalentDebit,
    lower_break_even: perUnitEntry > 0 ? center - perUnitEntry : null,
    upper_break_even: perUnitEntry > 0 ? center + perUnitEntry : null,
    legs: group
  };
}

export function matchLegGreeks(snapshot, legs) {
  const byStrike = new Map(snapshot.chain.map((row) => [Number(row.strike), row]));
  let delta = 0, theta = 0, gamma = 0, vega = 0;
  const detail = [];
  for (const leg of legs ?? []) {
    const row = byStrike.get(Number(leg.drvStrikePrice));
    const side = String(leg.drvOptionType).toUpperCase() === 'CALL' ? row?.call : row?.put;
    const qty = Number(leg.netQty ?? 0);
    const g = side?.greeks ?? {};
    for (const key of ['delta', 'theta', 'gamma', 'vega']) {
      const value = num(g[key]);
      if (value !== null) {
        if (key === 'delta') delta += qty * value;
        if (key === 'theta') theta += qty * value;
        if (key === 'gamma') gamma += qty * value;
        if (key === 'vega') vega += qty * value;
      }
    }
    detail.push({
      tradingSymbol: leg.tradingSymbol,
      strike: Number(leg.drvStrikePrice),
      optionType: leg.drvOptionType,
      netQty: qty,
      ltp: side?.ltp ?? null,
      bid: side?.bid ?? null,
      ask: side?.ask ?? null,
      iv: side?.iv ?? null,
      oi: side?.oi ?? null,
      volume: side?.volume ?? null,
      greeks: g
    });
  }
  return { net: { delta, theta, gamma, vega }, legs: detail };
}
