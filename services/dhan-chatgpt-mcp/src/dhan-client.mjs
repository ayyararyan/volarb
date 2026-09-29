const DEFAULT_BASE_URL = 'https://api.dhan.co/v2';
const DEFAULT_TIMEOUT_MS = 15000;

export class DhanApiError extends Error {
  constructor(message, { status, payload, path } = {}) {
    super(message);
    this.name = 'DhanApiError';
    this.status = status;
    this.payload = payload;
    this.path = path;
  }
}

export class DhanClient {
  constructor({ clientId, accessToken, tokenProvider, onAuthRejected, baseUrl = DEFAULT_BASE_URL, timeoutMs = DEFAULT_TIMEOUT_MS }) {
    if (!clientId) throw new Error('DHAN_CLIENT_ID is required');
    if (!accessToken && !tokenProvider) throw new Error('DHAN_ACCESS_TOKEN is required');

    this.clientId = clientId;
    this.accessToken = accessToken;
    this.tokenProvider = tokenProvider;
    this.onAuthRejected = onAuthRejected;
    this.baseUrl = baseUrl.replace(/\/$/, '');
    this.timeoutMs = timeoutMs;
  }

  async request(path, { method = 'GET', body } = {}) {
    const accessToken = this.tokenProvider ? await this.tokenProvider() : this.accessToken;
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), this.timeoutMs);

    try {
      const response = await fetch(`${this.baseUrl}${path}`, {
        method,
        headers: {
          'Accept': 'application/json',
          'Content-Type': 'application/json',
          'access-token': accessToken,
          'client-id': this.clientId,
          'User-Agent': 'dhan-chatgpt-mcp/0.1.0'
        },
        body: body === undefined ? undefined : JSON.stringify(body),
        signal: controller.signal
      });

      const raw = await response.text();
      let payload = null;
      if (raw) {
        try {
          payload = JSON.parse(raw);
        } catch {
          payload = { raw };
        }
      }

      if (!response.ok) {
        if (response.status === 401) this.onAuthRejected?.();
        const apiMessage = payload?.errorMessage || payload?.message || response.statusText;
        throw new DhanApiError(`Dhan API request failed: ${apiMessage}`, {
          status: response.status,
          payload,
          path
        });
      }

      return payload;
    } catch (error) {
      if (error?.name === 'AbortError') {
        throw new DhanApiError(`Dhan API request timed out after ${this.timeoutMs}ms`, { path });
      }
      throw error;
    } finally {
      clearTimeout(timer);
    }
  }

  getWhitelistedIps() { return this.request('/ip/getIP'); }

  getOrder(id) { return this.request(`/orders/${encodeURIComponent(id)}`); }

  getOrderByCorrelation(id) { return this.request(`/orders/external/${encodeURIComponent(id)}`); }

  getOrderTrades(id) { return this.request(`/trades/${encodeURIComponent(id)}`); }

  getMargin(order) {
    return this.request('/margincalculator', { method: 'POST', body: { ...order, dhanClientId: this.clientId } });
  }

  getBasketMargin(scripList, { includePosition = true, includeOrder = true } = {}) {
    // Official Dhan SDK payload; calculator only, never an order submission.
    return this.request('/margincalculator/multi', { method: 'POST', body: {
      dhanClientId: this.clientId, includePosition, includeOrder, scripList
    } });
  }

  placeLimitOrder(order) {
    return this.request('/orders', { method: 'POST', body: {
      ...order, dhanClientId: this.clientId, orderType: 'LIMIT', productType: 'INTRADAY',
      validity: 'DAY', disclosedQuantity: 0, triggerPrice: 0, afterMarketOrder: false
    } });
  }

  cancelOrder(id) { return this.request(`/orders/${encodeURIComponent(id)}`, { method: 'DELETE' }); }

  getProfile() {
    return this.request('/profile');
  }

  getFunds() {
    return this.request('/fundlimit');
  }

  getPositions() {
    return this.request('/positions');
  }

  getHoldings() {
    return this.request('/holdings');
  }

  getOrders() {
    return this.request('/orders');
  }

  getTrades() {
    return this.request('/trades');
  }

  getOptionExpiries({ underlyingScrip, underlyingSeg }) {
    return this.request('/optionchain/expirylist', {
      method: 'POST',
      body: {
        UnderlyingScrip: underlyingScrip,
        UnderlyingSeg: underlyingSeg
      }
    });
  }

  getOptionChain({ underlyingScrip, underlyingSeg, expiry }) {
    return this.request('/optionchain', {
      method: 'POST',
      body: {
        UnderlyingScrip: underlyingScrip,
        UnderlyingSeg: underlyingSeg,
        Expiry: expiry
      }
    });
  }

  getLtp(instruments) {
    return this.request('/marketfeed/ltp', {
      method: 'POST',
      body: groupInstruments(instruments)
    });
  }

  getQuote(instruments) {
    return this.request('/marketfeed/quote', {
      method: 'POST',
      body: groupInstruments(instruments)
    });
  }
}

export function groupInstruments(instruments) {
  const grouped = {};
  for (const { exchangeSegment, securityId } of instruments) {
    if (!grouped[exchangeSegment]) grouped[exchangeSegment] = [];
    grouped[exchangeSegment].push(Number(securityId));
  }
  return grouped;
}
