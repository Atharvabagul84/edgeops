import test from 'node:test';
import assert from 'node:assert/strict';

const config={mode:'aws',region:'ap-south-1',userPoolId:'ap-south-1_Example123',clientId:'exampleclient123',apiBaseUrl:'https://abc123.execute-api.ap-south-1.amazonaws.com'};
const response=(data,status=200)=>({ok:status>=200&&status<300,status,json:async()=>data});
const mockFetch=(t,implementation)=>{const original=globalThis.fetch;globalThis.fetch=implementation;t.after(()=>{globalThis.fetch=original;});};
const authenticated=(overrides={})=>({AuthenticationResult:{IdToken:'identity-token',RefreshToken:'refresh-token',ExpiresIn:3600,...overrides}});

test('config falls back to local only for404 or explicit local mode',async t=>{
  const {loadConfig}=await import('../api.js');
  mockFetch(t,async()=>response({},404));
  assert.deepEqual(await loadConfig(),{mode:'local'});
  globalThis.fetch=async()=>response({mode:'local'});
  assert.deepEqual(await loadConfig(),{mode:'local'});
});

test('config rejects network errors, invalid JSON, and unsafe token destinations',async t=>{
  const {loadConfig}=await import('../api.js');
  mockFetch(t,async()=>{throw new Error('offline');});
  await assert.rejects(loadConfig(),/configuration/i);
  globalThis.fetch=async()=>({ok:true,status:200,json:async()=>{throw new Error('html');}});
  await assert.rejects(loadConfig(),/configuration/i);
  for(const bad of [{...config,apiBaseUrl:'https://example.com'},{...config,mode:undefined},{...config,userPoolId:'us-east-1_Different'},{...config,apiBaseUrl:config.apiBaseUrl+'?secret=1'},{...config,apiBaseUrl:config.apiBaseUrl.replace('https:','http:')}]){
    globalThis.fetch=async()=>response(bad);
    await assert.rejects(loadConfig(),/configuration/i);
  }
  globalThis.fetch=async()=>response({},403);
  await assert.rejects(loadConfig(),/configuration/i);
});

test('API sends Cognito tokens only to configured AWS endpoint; local calls stay same-origin',async t=>{
  const {configureApi,request}=await import('../api.js');
  const calls=[];
  mockFetch(t,async(url,options)=>{calls.push({url,options});return response({mode:'aws'});});
  t.after(()=>configureApi({mode:'local'}));
  configureApi({...config,apiBaseUrl:config.apiBaseUrl+'/demo/'},async()=>'memory-token');
  await request('/api/tick',{steps:1});
  assert.equal(calls[0].url,config.apiBaseUrl+'/demo/api/tick');
  assert.equal(calls[0].options.headers.Authorization,'Bearer memory-token');
  assert.equal(calls[0].options.credentials,'omit');
  await assert.rejects(request('https://evil.example/api/state'),/API path/);
  assert.equal(calls.length,1);
  configureApi({mode:'local'});
  await request('/api/state');
  assert.equal(calls[1].url,'/api/state');
  assert.equal(calls[1].options.headers.Authorization,undefined);
});

test('API requires authentication before fetch and preserves401 for the UI',async t=>{
  const {configureApi,request}=await import('../api.js');
  let calls=0;
  mockFetch(t,async()=>{calls++;return response({message:'Unauthorized'},401);});
  t.after(()=>configureApi({mode:'local'}));
  configureApi(config,async()=>null);
  await assert.rejects(request('/api/state'),error=>error.status===401);
  assert.equal(calls,0);
  configureApi(config,async()=>'expired-token');
  await assert.rejects(request('/api/state'),error=>error.status===401 && /sign in/i.test(error.message));
});

test('Cognito sign-in handles required attributes and completes a new-password challenge',async t=>{
  const {createAuthSession}=await import('../auth.js');
  const calls=[];
  mockFetch(t,async(url,options)=>{calls.push({url,options,body:JSON.parse(options.body)});return calls.length===1?response({ChallengeName:'NEW_PASSWORD_REQUIRED',Session:'challenge-session',ChallengeParameters:{USER_ID_FOR_SRP:'canonical-user',requiredAttributes:'["userAttributes.email"]'}}):response(authenticated());});
  const snapshots=[];
  const auth=createAuthSession(config,{onChange:snapshot=>snapshots.push(snapshot)});
  const challenge=await auth.signIn('user@example.com','temporary-password');
  assert.equal(challenge.status,'new-password-required');
  assert.deepEqual(challenge.requiredAttributes,['email']);
  assert.equal(calls[0].url,'https://cognito-idp.ap-south-1.amazonaws.com/');
  assert.equal(calls[0].body.AuthFlow,'USER_PASSWORD_AUTH');
  assert.equal(calls[0].options.headers['X-Amz-Target'],'AWSCognitoIdentityProviderService.InitiateAuth');
  await assert.rejects(auth.completeNewPassword('A-new-password'),/email/i);
  assert.equal(calls.length,1);
  const signedIn=await auth.completeNewPassword('A-new-password',{email:'user@example.com'});
  assert.equal(signedIn.status,'authenticated');
  assert.deepEqual(calls[1].body.ChallengeResponses,{USERNAME:'canonical-user',NEW_PASSWORD:'A-new-password','userAttributes.email':'user@example.com'});
  assert.equal(calls[1].body.Session,'challenge-session');
  assert.equal(await auth.getToken(),'identity-token');
  assert.doesNotMatch(JSON.stringify(snapshots),/identity-token|refresh-token|temporary-password|A-new-password/);
  auth.signOut();
  assert.equal(auth.getSession().status,'signed-out');
  await assert.rejects(auth.getToken(),error=>error.status===401);
});

test('expired tokens refresh once in memory even with concurrent API requests',async t=>{
  const {createAuthSession}=await import('../auth.js');
  let now=1000000;
  const calls=[];
  mockFetch(t,async(url,options)=>{calls.push(JSON.parse(options.body));return response(authenticated(calls.length===1?{ExpiresIn:60}:{IdToken:'refreshed-identity',RefreshToken:undefined}));});
  const auth=createAuthSession(config,{now:()=>now});
  await auth.signIn('user','password');
  now+=61000;
  assert.deepEqual(await Promise.all([auth.getToken(),auth.getToken()]),['refreshed-identity','refreshed-identity']);
  assert.equal(calls.length,2);
  assert.equal(calls[1].AuthFlow,'REFRESH_TOKEN_AUTH');
  assert.deepEqual(calls[1].AuthParameters,{REFRESH_TOKEN:'refresh-token'});
});

test('failed refresh clears tokens and requires a new sign-in',async t=>{
  const {createAuthSession}=await import('../auth.js');
  let now=1000000,calls=0;
  mockFetch(t,async()=>++calls===1?response(authenticated({ExpiresIn:60})):response({__type:'NotAuthorizedException'},400));
  const auth=createAuthSession(config,{now:()=>now});
  await auth.signIn('user','password');
  now+=61000;
  await assert.rejects(auth.getToken(),error=>error.status===401 && error.code==='SESSION_EXPIRED');
  assert.equal(auth.getSession().status,'signed-out');
  assert.equal(auth.getSession().reason,'expired');
});

test('sign-out invalidates an in-flight sign-in response',async t=>{
  const {createAuthSession}=await import('../auth.js');
  let resolve;
  mockFetch(t,()=>new Promise(done=>{resolve=done;}));
  const auth=createAuthSession(config);
  const pending=auth.signIn('user','password');
  auth.signOut();
  resolve(response(authenticated()));
  await assert.rejects(pending,/cancelled/i);
  assert.equal(auth.getSession().status,'signed-out');
});

test('explicit expired sign-out keeps a safe reason for the sign-in notice',async()=>{
  const {createAuthSession}=await import('../auth.js');
  const auth=createAuthSession(config);
  auth.signOut('expired');
  assert.equal(auth.getSession().reason,'expired');
  auth.signOut('arbitrary-untrusted-reason');
  assert.equal(auth.getSession().reason,'signed-out');
});
