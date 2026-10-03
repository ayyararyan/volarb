import { DhanClient } from './dhan-client.mjs';
import { DhanProvider } from './dhan-provider.mjs';
import { DhanBrokerPort } from './dhan-broker-port.mjs';
import { DhanReadiness } from './dhan-readiness.mjs';
import { loadDhanConfig } from './dhan-config.mjs';
import { InstrumentMaster } from './instrument-master.mjs';
import { DhanStreamManager } from './dhan-streams.mjs';
import { DhanTranslator } from './dhan-translator.mjs';

export function createDhanRuntime({
  env = process.env,
  tokenProvider,
  onAuthRejected,
  fetchFn = fetch,
  egressIpResolver,
  WebSocketImpl = globalThis.WebSocket,
  now = Date.now
} = {}) {
  const config = loadDhanConfig(env, { hasTokenProvider: Boolean(tokenProvider) });
  const client = config.queryConfigured ? new DhanClient({
    clientId: config.clientId,
    accessToken: String(env.DHAN_ACCESS_TOKEN || '').trim() || undefined,
    tokenProvider,
    onAuthRejected,
    baseUrl: config.apiBaseUrl,
    timeoutMs: config.apiTimeoutMs,
    fetchFn
  }) : null;

  const instrumentMaster = new InstrumentMaster({
    url: config.instrumentMasterUrl,
    ttlMs: config.instrumentMasterTtlMs,
    fetchFn
  });
  const readiness = new DhanReadiness({ client, config, fetchFn, egressIpResolver, now });
  const provider = new DhanProvider({ client, instrumentMaster, readiness });
  const resolveToken = tokenProvider
    ? tokenProvider
    : async () => String(env.DHAN_ACCESS_TOKEN || '').trim();
  const streams = new DhanStreamManager({ config, readiness, resolveToken, WebSocketImpl });
  const translator = new DhanTranslator();
  const port = new DhanBrokerPort({ provider, readiness, config, streams, translator, now });

  return {
    config, client, instrumentMaster, readiness, provider, streams, translator, port,
    async warmup({ instrumentMaster: warmMaster = true, readiness: warmReady = true } = {}) {
      const tasks = [];
      if (warmMaster && config.queryConfigured) tasks.push(instrumentMaster.getRows());
      if (warmReady) tasks.push(readiness.inspect({ refresh: true }));
      return {
        warmed: true,
        queryConfigured: config.queryConfigured,
        commandsEnabled: config.commandsEnabled,
        results: await Promise.all(tasks)
      };
    }
  };
}
