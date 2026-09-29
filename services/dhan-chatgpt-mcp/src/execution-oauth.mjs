// Protocol validation, PKCE, discovery, registration and rate limits come from the MCP SDK.
import express from 'express';
import { randomBytes, createHash } from 'node:crypto';
import { rateLimit } from 'express-rate-limit';
import { mcpAuthRouter, getOAuthProtectedResourceMetadataUrl } from '@modelcontextprotocol/sdk/server/auth/router.js';
import { requireBearerAuth } from '@modelcontextprotocol/sdk/server/auth/middleware/bearerAuth.js';
import { InvalidGrantError, InvalidTokenError, InvalidRequestError, InvalidClientMetadataError } from '@modelcontextprotocol/sdk/server/auth/errors.js';
import { ExecutionStore } from './butterfly-executor.mjs';
import { bearerAuthorized } from './execution-mcp.mjs';
const secret = () => randomBytes(32).toString('base64url');
const hash = s => createHash('sha256').update(s).digest('hex');
const esc = s => String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const SCOPE = 'butterfly:execute';

export class ExecutionOAuthProvider {
  constructor({ issuer, ownerToken, store, allowedRedirects = [], now = Date.now }) {
    this.issuer = new URL(issuer); this.resource = new URL('/execution/mcp', this.issuer).href;
    this.ownerToken = ownerToken; this.store = store; this.now = now; this.pending = new Map(); this.allowedRedirects = allowedRedirects;
    if (this.issuer.protocol !== 'https:' && !['127.0.0.1','localhost'].includes(this.issuer.hostname)) throw new Error('OAuth issuer requires HTTPS');
    store.data.oauth ??= { clients: {}, codes: {}, access: {}, refresh: {}, ownerHash: hash(ownerToken) };
    this.db = store.data.oauth;
    if (this.db.ownerHash !== hash(ownerToken)) { this.db.access = {}; this.db.refresh = {}; this.db.codes = {}; this.db.ownerHash = hash(ownerToken); }
    store.save();
    this.clientsStore = {
      getClient: id => this.db.clients[id],
      registerClient: async client => {
        if (Object.keys(this.db.clients).length >= 100) throw new InvalidClientMetadataError('Client capacity reached');
        if (!client.redirect_uris?.length || !client.redirect_uris.every(uri => this.allowedRedirect(uri))) throw new InvalidClientMetadataError('Only ChatGPT callbacks or explicitly configured exact redirects allowed');
        if (!['none','client_secret_post'].includes(client.token_endpoint_auth_method || 'client_secret_post')) throw new InvalidClientMetadataError('Unsupported token authentication method');
        this.db.clients[client.client_id] = client; this.store.save(); return client;
      }
    };
  }
  allowedRedirect(uri) {
    if (this.allowedRedirects.includes(uri)) return true;
    try { const u = new URL(uri); return u.origin === 'https://chatgpt.com' && !u.hash && !u.search && (u.pathname === '/connector_platform_oauth_redirect' || /^\/connector\/oauth\/[a-zA-Z0-9_-]+$/.test(u.pathname)); } catch { return false; }
  }
  prune() {
    for (const name of ['codes','access','refresh']) for (const [key,v] of Object.entries(this.db[name])) if (v.expires <= this.now()) delete this.db[name][key];
    for (const [key,v] of this.pending) if (v.expires <= this.now()) this.pending.delete(key);
  }
  async authorize(client, params, res) {
    this.prune();
    if (params.resource?.href !== this.resource) throw new InvalidRequestError('Incorrect or missing execution resource');
    if (!params.scopes?.length || params.scopes.some(s => s !== SCOPE)) throw new InvalidRequestError('Request butterfly:execute scope');
    if (!this.allowedRedirect(params.redirectUri) || !client.redirect_uris.includes(params.redirectUri)) throw new InvalidRequestError('Redirect not allowed');
    if (this.pending.size >= 100) throw new InvalidRequestError('Too many pending authorizations');
    const requestId = secret(), cookie = secret();
    this.pending.set(requestId, { clientId: client.client_id, ...params, resource: this.resource, cookieHash:hash(cookie), expires: this.now()+300000 });
    res.setHeader('Set-Cookie', `__Host-dhan-consent=${cookie}; Path=/; Secure; HttpOnly; SameSite=Lax; Max-Age=300`);
    res.setHeader('Content-Security-Policy', "default-src 'none'; form-action 'self'; frame-ancestors 'none'; base-uri 'none'");
    res.setHeader('X-Frame-Options','DENY'); res.setHeader('Referrer-Policy','no-referrer'); res.setHeader('Cache-Control','no-store');
    res.type('html').send(`<!doctype html><html lang="en"><meta charset="utf-8"><title>Authorize Dhan butterfly executor</title><h1>Connect your butterfly executor</h1><p>This permits the client to submit real limit orders when live execution is enabled. Each trade still requires its own approved preview.</p><p>Client: ${esc(client.client_name || client.client_id)}<br>Callback: ${esc(params.redirectUri)}</p><form method="post" action="/execution/consent"><input type="hidden" name="requestId" value="${requestId}"><label>Local executor passphrase (not your Dhan token) <input type="password" name="passphrase" autocomplete="off" required></label><button type="submit" name="decision" value="approve">Authorize this client</button><button type="submit" name="decision" value="deny" formnovalidate>Cancel</button></form></html>`);
  }
  consent(req, res) {
    res.setHeader('Cache-Control','no-store');
    const p = this.pending.get(req.body?.requestId);
    const cookie = /(?:^|;\s*)__Host-dhan-consent=([^;]+)/.exec(req.headers.cookie || '')?.[1];
    if (!p || p.expires <= this.now() || !cookie || hash(cookie) !== p.cookieHash || req.headers.origin !== this.issuer.origin) return res.status(403).json({error:'Invalid or expired consent request'});
    const redirect = new URL(p.redirectUri);
    if (p.state) redirect.searchParams.set('state',p.state);
    // Issuer included even though SDK metadata does not advertise RFC9207 support.
    redirect.searchParams.set('iss',this.issuer.href);
    if (req.body.decision === 'deny') {this.pending.delete(req.body.requestId);redirect.searchParams.set('error','access_denied');return res.redirect(303,redirect.href);}
    if (req.body.decision !== 'approve' || !bearerAuthorized(`Bearer ${req.body.passphrase || ''}`,this.ownerToken)) return res.status(403).json({error:'Invalid executor passphrase'});
    this.pending.delete(req.body.requestId);
    const code = secret(); this.db.codes[hash(code)] = { clientId:p.clientId,redirectUri:p.redirectUri,challenge:p.codeChallenge,resource:p.resource,scopes:p.scopes,expires:this.now()+60000 };
    this.store.save();redirect.searchParams.set('code',code);res.redirect(303,redirect.href);
  }
  code(client, code) {
    const c = this.db.codes[hash(code)];
    if (!c || c.clientId !== client.client_id || c.expires <= this.now()) throw new InvalidGrantError('Invalid or expired code');
    return c;
  }
  async challengeForAuthorizationCode(client, code) { return this.code(client,code).challenge; }
  async exchangeAuthorizationCode(client, code, _verifier, redirectUri, resource) {
    const c = this.code(client,code);
    if (redirectUri !== c.redirectUri || (resource && resource.href !== c.resource)) throw new InvalidGrantError('Redirect/resource mismatch');
    delete this.db.codes[hash(code)];return this.issue(client.client_id,c.scopes);
  }
  issue(clientId, scopes) {
    this.prune();
    const access_token = secret(), refresh_token = secret();
    const common = { clientId,scopes,resource:this.resource };
    this.db.access[hash(access_token)] = { ...common,expires:this.now()+3600000 };
    this.db.refresh[hash(refresh_token)] = { ...common,accessHash:hash(access_token),expires:this.now()+7*86400000 };
    this.store.save();return { access_token,refresh_token,token_type:'Bearer',expires_in:3600,scope:scopes.join(' ') };
  }
  async exchangeRefreshToken(client, token, scopes, resource) {
    const r = this.db.refresh[hash(token)];
    if (!r || r.expires <= this.now() || r.clientId !== client.client_id || (resource && resource.href !== r.resource) || (scopes && scopes.some(s=>!r.scopes.includes(s)))) throw new InvalidGrantError('Invalid refresh token/resource/scope');
    delete this.db.refresh[hash(token)];delete this.db.access[r.accessHash];return this.issue(client.client_id,scopes || r.scopes);
  }
  async verifyAccessToken(token) {
    const a = this.db.access[hash(token)];
    if (!a || a.expires <= this.now() || a.resource !== this.resource || !a.scopes.includes(SCOPE)) throw new InvalidTokenError('Invalid or expired execution token');
    return { token,clientId:a.clientId,scopes:a.scopes,expiresAt:Math.floor(a.expires/1000),resource:new URL(a.resource) };
  }
  async revokeToken(client, request) {
    const h=hash(request.token),r=this.db.refresh[h],a=this.db.access[h];
    if(r?.clientId===client.client_id){delete this.db.refresh[h];delete this.db.access[r.accessHash];}
    if(a?.clientId===client.client_id){delete this.db.access[h];for(const [k,v] of Object.entries(this.db.refresh))if(v.accessHash===h)delete this.db.refresh[k];}
    this.store.save();
  }
}
export function installExecutionOAuth(app, { issuer, ownerToken, dir, allowedRedirects = [] }) {
  const provider = new ExecutionOAuthProvider({issuer,ownerToken,store:new ExecutionStore(dir),allowedRedirects});
  app.use(mcpAuthRouter({provider,issuerUrl:provider.issuer,resourceServerUrl:new URL(provider.resource),scopesSupported:[SCOPE],resourceName:'Dhan butterfly executor',clientRegistrationOptions:{clientSecretExpirySeconds:0}}));
  app.post('/execution/consent',rateLimit({windowMs:900000,max:10,standardHeaders:true,legacyHeaders:false}),express.urlencoded({extended:false,limit:'4kb'}),(req,res)=>provider.consent(req,res));
  const guard = requireBearerAuth({verifier:provider,requiredScopes:[SCOPE],resourceMetadataUrl:getOAuthProtectedResourceMetadataUrl(new URL(provider.resource))});
  return {provider,guard};
}
