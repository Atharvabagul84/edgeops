import test from 'node:test';
import assert from 'node:assert/strict';

test('failed server mutations reject instead of returning a simulated success', async () => {
  const { request } = await import('../api.js');
  const original = globalThis.fetch;
  globalThis.fetch = async () => ({ ok: false, status: 409, json: async () => ({error: 'Device is disconnected'}) });
  try { await assert.rejects(request('/api/actions', {action:'replay'}), /Device is disconnected/); }
  finally { globalThis.fetch = original; }
});

test('unsafe names cannot create HTML in dashboard', async () => {
  const { escapeHtml } = await import('../presentation.js');
  assert.equal(escapeHtml('<img src=x onerror="alert(1)">'), '&lt;img src=x onerror=&quot;alert(1)&quot;&gt;');
});

test('chart is usable with empty and single sample histories', async () => {
  const { temperatureChart } = await import('../chart.js');
  assert.match(temperatureChart([]), /Waiting for telemetry/);
  const svg = temperatureChart([{at:'2026-10-06T12:00:00Z',temperature:24}]);
  assert.match(svg, /<svg/);
  assert.doesNotMatch(svg, /NaN|Infinity/);
});

test('last contact age progresses with real wall clock while the simulator is paused', async () => {
  const { relativeTime } = await import('../presentation.js');
  const captured = new Date(Date.now() - 125000).toISOString();
  assert.equal(relativeTime(captured), '2m ago');
});

test('release badge uses the loaded frontend release and reports a matching API response',async()=>{
  const {FRONTEND_RELEASE}=await import('../api.js');
  const {releasePresentation}=await import('../presentation.js');
  assert.deepEqual(FRONTEND_RELEASE,{version:'0.3.0',id:'edgeops-0.3.0'});
  const badge=releasePresentation(FRONTEND_RELEASE,{phase:'received',release:{...FRONTEND_RELEASE}});
  assert.equal(badge.state,'matched');
  assert.match(badge.summary,/UI v0\.3\.0.*API v0\.3\.0/);
});

test('release badge explicitly distinguishes missing metadata and mismatched release identities',async()=>{
  const {FRONTEND_RELEASE}=await import('../api.js');
  const {releasePresentation}=await import('../presentation.js');
  assert.equal(releasePresentation(FRONTEND_RELEASE,{phase:'received'}).state,'unknown');
  assert.match(releasePresentation(FRONTEND_RELEASE,{phase:'received',release:{version:'0.2.0',id:'edgeops-0.2.0'}}).detail,/mismatch/i);
  const sameVersion=releasePresentation(FRONTEND_RELEASE,{phase:'received',release:{version:'0.3.0',id:'different-build'}});
  assert.equal(sameVersion.state,'mismatch');
  assert.match(sameVersion.detail,/different-build/);
});

test('API failures and logout discard previous matching release claims',async()=>{
  const {FRONTEND_RELEASE}=await import('../api.js');
  const {releasePresentation}=await import('../presentation.js');
  const failed=releasePresentation(FRONTEND_RELEASE,{phase:'unavailable',release:{...FRONTEND_RELEASE}});
  assert.equal(failed.state,'unavailable');
  assert.equal(failed.apiRelease,null);
  assert.doesNotMatch(failed.summary,/API v0\.3\.0/);
  const signedOut=releasePresentation(FRONTEND_RELEASE,{phase:'pending',release:{...FRONTEND_RELEASE}});
  assert.equal(signedOut.state,'pending');
  assert.equal(signedOut.apiRelease,null);
  assert.match(signedOut.summary,/API pending/);
});
