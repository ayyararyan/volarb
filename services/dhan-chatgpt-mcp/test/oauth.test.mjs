import test from 'node:test';
import assert from 'node:assert/strict';
import express from 'express';
import { once } from 'node:events';
import { createHash } from 'node:crypto';
import { mkdtempSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { installExecutionOAuth } from '../src/execution-oauth.mjs';
const OWNER='test-owner-'.repeat(8);
async function appFixture(t) {
 const app=express();app.use(express.json());
 const auth=installExecutionOAuth(app,{issuer:'https://executor.example',ownerToken:OWNER,dir:mkdtempSync(join(tmpdir(),'dhan-oauth-test-'))});
 app.post('/execution/mcp',auth.guard,(_req,res)=>res.json({ok:true}));
 const server=app.listen(0,'127.0.0.1');await once(server,'listening');t.after(()=>server.close());
 const base=`http://127.0.0.1:${server.address().port}`;
 const call=(path,opts={})=>fetch(base+path,opts);
 return {auth,call};
}
const post=(data)=>({method:'POST',headers:{'Content-Type':'application/x-www-form-urlencoded'},body:new URLSearchParams(data),redirect:'manual'});
async function authorize(call) {
 const r=await call('/register',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({client_name:'ChatGPT test',redirect_uris:['https://chatgpt.com/connector_platform_oauth_redirect'],token_endpoint_auth_method:'none',grant_types:['authorization_code','refresh_token'],response_types:['code']})});
 assert.equal(r.status,201);const client=await r.json();
 const verifier='x'.repeat(64),challenge=createHash('sha256').update(verifier).digest('base64url');
 const params={client_id:client.client_id,response_type:'code',redirect_uri:client.redirect_uris[0],code_challenge:challenge,code_challenge_method:'S256',scope:'butterfly:execute',resource:'https://executor.example/execution/mcp',state:'state-check'};
 const page=await call('/authorize?'+new URLSearchParams(params));assert.equal(page.status,200);
 const html=await page.text(),requestId=/name="requestId" value="([^"]+)"/.exec(html)[1],cookie=page.headers.get('set-cookie').split(';')[0];
 return {client,verifier,requestId,cookie,params,html};
}
async function consent(call,a,password=OWNER,origin='https://executor.example') {
 const opts=post({requestId:a.requestId,passphrase:password,decision:'approve'});opts.headers.Origin=origin;opts.headers.Cookie=a.cookie;
 return call('/execution/consent',opts);
}
async function getToken(call,a) {
 const approved=await consent(call,a);assert.equal(approved.status,303);
 const u=new URL(approved.headers.get('location'));assert.equal(u.searchParams.get('state'),'state-check');
 const code=u.searchParams.get('code');
 const request={grant_type:'authorization_code',client_id:a.client.client_id,code,code_verifier:a.verifier,redirect_uri:a.client.redirect_uris[0],resource:a.params.resource};
 const r=await call('/token',post(request));assert.equal(r.status,200);return {tokens:await r.json(),request};
}

test('OAuth discovery, owner consent, S256 exchange and guarded endpoint work end-to-end',async t=>{
 const {call}=await appFixture(t);
 const unauth=await call('/execution/mcp',{method:'POST'});assert.equal(unauth.status,401);assert.match(unauth.headers.get('www-authenticate'),/resource_metadata/);
 const prm=await (await call('/.well-known/oauth-protected-resource/execution/mcp')).json();assert.equal(prm.resource,'https://executor.example/execution/mcp');
 const metadata=await(await call('/.well-known/oauth-authorization-server')).json();assert.ok(metadata.code_challenge_methods_supported.includes('S256'));
 const a=await authorize(call);assert.ok(!a.html.includes(OWNER));
 const {tokens,request}=await getToken(call,a);
 const allowed=await call('/execution/mcp',{method:'POST',headers:{Authorization:`Bearer ${tokens.access_token}`}});assert.equal(allowed.status,200);
 const reused=await call('/token',post(request));assert.equal(reused.status,400);
});
test('OAuth rejects wrong password, cross-origin consent and bad PKCE without granting access',async t=>{
 const {call}=await appFixture(t);const a=await authorize(call);
 assert.equal((await consent(call,a,'wrong')).status,403);
 assert.equal((await consent(call,a,OWNER,'https://evil.example')).status,403);
 const approved=await consent(call,a);const code=new URL(approved.headers.get('location')).searchParams.get('code');
 const r=await call('/token',post({grant_type:'authorization_code',client_id:a.client.client_id,code,code_verifier:'wrong'.repeat(15),redirect_uri:a.client.redirect_uris[0],resource:a.params.resource}));
 assert.equal(r.status,400);assert.equal((await r.json()).error,'invalid_grant');
});
test('OAuth rejects unapproved callbacks, changed resource and unauthorized bearer',async t=>{
 const {call}=await appFixture(t);
 const bad=await call('/register',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({redirect_uris:['https://evil.example/callback'],token_endpoint_auth_method:'none'})});assert.equal(bad.status,400);
 const a=await authorize(call);
 const r=await call('/authorize?'+new URLSearchParams({...a.params,resource:'https://evil.example'}),{redirect:'manual'});assert.equal(r.status,302);assert.match(r.headers.get('location'),/invalid_request/);
 assert.equal((await call('/execution/mcp',{method:'POST',headers:{Authorization:'Bearer bad'}})).status,401);
});
test('OAuth refresh rotates tokens and revocation prevents reuse',async t=>{
 const {call}=await appFixture(t);const a=await authorize(call);const {tokens}=await getToken(call,a);
 const data={grant_type:'refresh_token',client_id:a.client.client_id,refresh_token:tokens.refresh_token,resource:a.params.resource};
 const refresh=await call('/token',post(data));assert.equal(refresh.status,200);const rotated=await refresh.json();
 assert.equal((await call('/token',post(data))).status,400);
 assert.equal((await call('/execution/mcp',{method:'POST',headers:{Authorization:`Bearer ${tokens.access_token}`}})).status,401);
 const revoked=await call('/revoke',post({client_id:a.client.client_id,token:rotated.refresh_token}));assert.equal(revoked.status,200);
 assert.equal((await call('/execution/mcp',{method:'POST',headers:{Authorization:`Bearer ${rotated.access_token}`}})).status,401);
});
