import { request, loadConfig, configureApi, FRONTEND_RELEASE } from './api.js';
import { createAuthSession } from './auth.js';
import { renderAuth, downloadDiagnostics, shellView } from './cloud-ui.js';
import { icon } from './icons.js';
import { escapeHtml, time, releasePresentation } from './presentation.js';
import { metrics, telemetryPanel, deviceInspector, fleetTable } from './fleet.js';
import { incidentPanel, activityPanel, pipelinePanel, architectureView } from './operations.js';

const $ = (selector) => document.querySelector(selector);
const views = {
  overview:{name:'Overview',title:'Fleet overview',description:'Every device. Every signal. One clear picture.',icon:'grid'},
  devices:{name:'Devices',title:'Your device fleet',description:'Inspect signals, simulate failures, and recover confidently.',icon:'device'},
  incidents:{name:'Incidents',title:'Incident center',description:'Understand what happened. Know when it recovered.',icon:'incident'},
  activity:{name:'Activity',title:'Fleet activity',description:'A traceable timeline from the device to the dashboard.',icon:'activity'},
  architecture:{name:'Architecture',title:'Under the hood',description:'A dependable local foundation with a clear path to AWS.',icon:'architecture'},
};
let state, selectedId='edge-001', view='overview', running=false, busy=false, mutating=false, demoRunning=false;
let deviceFilter='all', incidentFilter='all', search='', toastTimer;
let config, auth;
let releaseView=releasePresentation(FRONTEND_RELEASE);
const cloud = () => config?.mode==='aws';
const canAccess = () => config && (!cloud() || auth?.getSession().status==='authenticated');
const setShell = (shell) => {
  const from=document.body.dataset.view;
  document.body.dataset.view=shell;
  document.title=shell==='signin' ? 'Sign in · EdgeOps' : 'EdgeOps — Fleet reliability';
  if(from==='signin' && shell==='app') $('#main-content').focus({preventScroll:true});
};

const updateRelease=(phase,release=null)=>{
  releaseView=releasePresentation(FRONTEND_RELEASE,{phase,release});
  $('#release-badge').dataset.releaseStatus=releaseView.state;
  if($('#release-summary').textContent!==releaseView.summary) $('#release-summary').textContent=releaseView.summary;
  if($('#release-note').textContent!==releaseView.detail) $('#release-note').textContent=releaseView.detail;
  if(phase==='unavailable') $('#sync-status').textContent='Connection unverified · displayed readings may be stale';
};

const toast = (message, error=false) => {
  $('#toast').innerHTML = `${icon(error ? 'incident' : 'check')}<span>${escapeHtml(message)}</span>`;
  $('#toast').classList.toggle('toast-error',error);
  $('#toast').hidden=false;
  clearTimeout(toastTimer);
  toastTimer=setTimeout(() => { $('#toast').hidden=true; }, 5000);
};

const renderNavigation = () => {
  const focusedNav=document.activeElement?.closest('#navigation a')?.getAttribute('href');
  $('#navigation').innerHTML = Object.entries(views).map(([key,item]) => `<a href="#${key}" aria-label="${item.name}" class="nav-item ${view === key ? 'active' : ''}" ${view===key ? 'aria-current="page"' : ''}>${icon(item.icon)}<span>${item.name}</span>${key==='incidents' && state?.stats.activeIncidents ? `<span class="nav-count">${state.stats.activeIncidents}</span>` : ''}</a>`).join('');
  $('#page-title').textContent=views[view].title;
  $('#page-description').textContent=views[view].description;
  $('#breadcrumb-current').textContent=views[view].name;
  $('.eyebrow').textContent=view==='overview' ? 'YOUR FLEET, AT A GLANCE' : 'FLEET RELIABILITY WORKSPACE';
  if (focusedNav) document.querySelector(`#navigation a[href="${CSS.escape(focusedNav)}"]`)?.focus({preventScroll:true});
};

const preserveFocus = (render) => {
  const active=document.activeElement;
  const focusId=active?.id;
  const selection=active instanceof HTMLInputElement ? [active.selectionStart,active.selectionEnd] : null;
  const device=active?.dataset.device;
  const action=active?.dataset.deviceAction;
  const selectDevice=active?.dataset.selectDevice;
  render();
  let target=focusId ? document.getElementById(focusId) : null;
  if (!target && device && action) target=$(`[data-device="${CSS.escape(device)}"][data-device-action="${CSS.escape(action)}"]`);
  if (!target && selectDevice) target=$(`[data-select-device="${CSS.escape(selectDevice)}"]`);
  target?.focus({preventScroll:true});
  if (target instanceof HTMLInputElement && selection) target.setSelectionRange(...selection);
};

const renderContent = () => {
  if (!state) return;
  const selected=state.devices.find(d => d.id===selectedId) || state.devices[0];
  if (!selected && view!=='architecture') {
    $('#content').innerHTML='<div class="panel empty">No devices have been registered. Reset the demo to initialize your fleet.</div>';
    return;
  }
  selectedId=selected?.id || selectedId;
  let body='';
  if (view==='overview') body=`${metrics(state)}<div class="telemetry-layout">${telemetryPanel(state,selected)}${deviceInspector(selected,state.now)}</div>${fleetTable(state,selectedId,deviceFilter,search)}<div class="operations-layout">${incidentPanel(state)}${activityPanel(state)}</div>`;
  if (view==='devices') body=`${metrics(state)}${fleetTable(state,selectedId,deviceFilter,search)}<div class="telemetry-layout">${telemetryPanel(state,selected)}${deviceInspector(selected,state.now)}</div>`;
  if (view==='incidents') body=`${metrics(state)}${incidentPanel(state,true,incidentFilter)}`;
  if (view==='activity') body=`${pipelinePanel(state)}${activityPanel(state,true)}`;
  if (view==='architecture') body=architectureView(config?.mode);
  preserveFocus(() => { $('#content').innerHTML=body; });
  $('#content').setAttribute('aria-busy','false');
  $('#sync-status').textContent=releaseView.phase==='received' ? `${cloud() ? 'AWS API' : 'Local backend'} connected · Updated ${time(state.now)}` : 'Connection unverified · showing cached readings';
  renderNavigation();
  updateControls();
};

const updateControls = () => {
  $('#simulation-btn').innerHTML=`${icon(running ? 'pause' : 'play')}${cloud() ? 'Generate one reading' : running ? 'Pause simulation' : 'Start simulation'}`;
  $('#simulation-btn').disabled=demoRunning || !state;
  $('#simulation-btn').setAttribute('aria-pressed',String(running));
  $('#demo-btn').disabled=demoRunning || mutating || !state;
  $('#reset-btn').disabled=demoRunning || mutating || !state;
  $('#signout-btn').disabled=demoRunning || mutating;
  document.querySelectorAll('[data-device-action]').forEach(button => {
    button.disabled=mutating || demoRunning || (button.dataset.deviceAction==='replay' && (!state.devices.find(d=>d.id===button.dataset.device)?.connected || !state.devices.find(d=>d.id===button.dataset.device)?.received));
  });
};

const setState = (data) => {
  if (!canAccess()) return;
  state=data;
  updateRelease('received',data.release);
  $('#connection-banner').hidden=true;
  renderContent();
};

const connectionError = (error) => {
  if (cloud() && !canAccess()) return;
  if (cloud() && error.status===401) { auth.signOut('expired'); return; }
  updateRelease('unavailable');
  $('#connection-banner').textContent=`Cannot reach the ${cloud() ? 'AWS API' : 'local service'}: ${error.message}. ${cloud() ? 'Check the deployment and retry.' : 'Start the backend and reconnect.'}`;
  $('#connection-banner').hidden=false;
  $('#sync-status').textContent='Service unavailable · displayed readings may be stale';
  if (!state) $('#content').innerHTML='<div class="panel empty"><strong>Waiting for telemetry</strong><p>Check the service connection, then retry.</p><button class="button primary" id="retry-btn">Reconnect</button></div>';
};

const refresh = async () => {
  if (busy || demoRunning || !canAccess()) return;
  busy=true;
  try { setState(await request('/api/state')); }
  catch(error) { connectionError(error); }
  finally { busy=false; updateControls(); }
};

const mutate = async (path, body, successMessage) => {
  if (busy || demoRunning || !canAccess()) return;
  busy=true; mutating=true;
  updateControls();
  try { setState(await request(path,body)); if(successMessage) toast(successMessage); }
  catch(error) { updateRelease('unavailable'); if(error.status===401) connectionError(error); else toast(error.message,true); }
  finally { busy=false; mutating=false; updateControls(); }
};

const demoStep = async (label,path,body) => {
  $('#demo-description').textContent=label;
  setState(await request(path,body));
  await new Promise(resolve => setTimeout(resolve,750));
};

const runDemo = async () => {
  if (busy || demoRunning || !canAccess() || !state) return;
  const resume=running;
  const demoDeviceId='edge-002';
  const duplicatesBefore=state.stats.duplicates;
  running=false; demoRunning=true; selectedId=demoDeviceId;
  location.hash='overview';
  updateControls();
  $('#demo-btn').innerHTML='<span class="spinner"></span>Running recovery demo';
  try {
    if (!state.devices.find(d=>d.id===demoDeviceId)?.connected) await demoStep('Preparing device for the recovery experiment…','/api/actions',{deviceId:demoDeviceId,action:'reconnect'});
    await demoStep('1 / 4 · Device disconnected. Readings will stay in its local buffer.','/api/actions',{deviceId:demoDeviceId,action:'disconnect'});
    await demoStep('2 / 4 · Generating 3 readings while the device is offline.','/api/tick',{steps:3});
    await demoStep('3 / 4 · Reconnecting and processing the buffered readings.','/api/actions',{deviceId:demoDeviceId,action:'reconnect'});
    await demoStep('4 / 4 · Replaying an event to verify duplicate suppression.','/api/actions',{deviceId:demoDeviceId,action:'replay'});
    const recovered=state.devices.find(d=>d.id===demoDeviceId);
    if (!recovered.connected || recovered.buffered!==0 || state.stats.duplicates<=duplicatesBefore) throw new Error('Recovery counters did not confirm a cleared buffer and blocked duplicate.');
    $('#demo-description').textContent='Recovery complete. Buffered readings delivered and a duplicate safely blocked.';
    toast('Recovery verified. Inspect the readings, incident history, and duplicate counter.');
  } catch(error) {
    updateRelease('unavailable');
    if(error.status===401) connectionError(error);
    $('#demo-description').textContent='Demo stopped. Check the device state and try again.';
    toast(`Recovery demo failed: ${error.message}`,true);
  } finally {
    demoRunning=false; running=resume;
    $('#demo-btn').innerHTML=`Run recovery demo ${icon('arrow')}`;
    updateControls();
  }
};

document.addEventListener('click', (event) => {
  const button=event.target.closest('button');
  if (!button) return;
  if (button.dataset.view) location.hash=button.dataset.view;
  if (button.dataset.selectDevice) {
    selectedId=button.dataset.selectDevice;
    if (!['overview','devices'].includes(view)) location.hash='devices';
    renderContent();
  }
  if (button.dataset.deviceAction) mutate('/api/actions',{deviceId:button.dataset.device,action:button.dataset.deviceAction},'Device action completed.');
  if (button.id==='retry-btn') refresh();
});
document.addEventListener('change', (event) => {
  if(event.target.id==='chart-device') selectedId=event.target.value;
  else if(event.target.id==='device-filter') deviceFilter=event.target.value;
  else if(event.target.id==='incident-filter') incidentFilter=event.target.value;
  else return;
  renderContent();
});
document.addEventListener('input', (event) => {
  if(event.target.id!=='device-search') return;
  search=event.target.value;
  renderContent();
});
$('#simulation-btn').addEventListener('click', () => {
  if(cloud()) { mutate('/api/tick',{steps:1},'One synthetic reading generated per device.'); return; }
  running=!running; updateControls(); toast(running ? 'Simulation running. New readings every 4 seconds.' : 'Simulation paused. Device controls remain available.'); if(running) mutate('/api/tick',{steps:1});
});
$('#demo-btn').addEventListener('click',runDemo);
$('#export-btn').innerHTML=`${icon('download')}Export diagnostics`;
$('#export-btn').addEventListener('click',async event => {
  if(!cloud()) { toast('Download requested. Your browser will handle the diagnostics file.'); return; }
  event.preventDefault();
  try { downloadDiagnostics(await request('/api/export')); toast('Your diagnostics are ready to inspect or download.'); }
  catch(error) { updateRelease('unavailable'); if(error.status===401) connectionError(error); else toast(error.message,true); }
});
$('#reset-btn').addEventListener('click',() => $('#reset-dialog').showModal());
$('#cancel-reset').addEventListener('click',() => $('#reset-dialog').close());
$('#confirm-reset').addEventListener('click',() => { $('#reset-dialog').close(); running=false; mutate('/api/reset',{},'Demo data reset. Ready for a new experiment.'); $('#demo-description').textContent='Disconnect a device. Buffer readings. Reconnect without losing a signal.'; });
const route = () => { view=views[location.hash.slice(1)] ? location.hash.slice(1) : 'overview'; renderNavigation(); renderContent(); };
window.addEventListener('hashchange',route);
$('#demo-icon').innerHTML=icon('bolt');
updateRelease('pending');
$('.version-label').textContent=`LOCAL MVP · v${FRONTEND_RELEASE.version}`;
route();
updateControls();
const sessionChanged = session => {
  const signedIn=session.status==='authenticated';
  setShell(shellView(config,session));
  renderAuth($('#auth-panel'),auth,session);
  $('#signout-btn').hidden=!signedIn;
  for(const selector of ['#content','.heading-actions','.demo-banner','.main-footer']) $(selector).hidden=!signedIn;
  $('#connection-banner').hidden=true;
  if(signedIn) refresh();
  else { state=null; running=false; updateRelease('pending'); $('#content').replaceChildren(); renderNavigation(); updateControls(); }
};
$('#signout-btn').addEventListener('click',() => auth?.signOut());

const start = async () => {
  try {
    config=await loadConfig();
    if(cloud()) {
      auth=createAuthSession(config,{onChange:sessionChanged});
      configureApi(config,() => auth.getToken());
      $('#environment-label').innerHTML='<i></i>AWS · synthetic fleet';
      $('.version-label').textContent=`AWS DEMO · v${FRONTEND_RELEASE.version}`;
      $('.workspace small').textContent='Cloud demonstration';
      $('#reset-description').textContent='This clears the shared cloud demo fleet. Stop device agents first: already queued events can repopulate the fleet after reset.';
      views.architecture.description='Authenticated telemetry, buffered delivery, and repeatable AWS infrastructure.';
      sessionChanged(auth.getSession());
    } else { setShell('app'); configureApi(config); await refresh(); }
    setInterval(() => {
      if(document.hidden || !canAccess()) return;
      if(running && !cloud() && !busy && !demoRunning) mutate('/api/tick',{steps:1});
      else if(!busy && !demoRunning) refresh();
    },cloud() ? 30000 : 4000);
  } catch(error) {
    config=null;
    setShell('app');
    updateRelease('unavailable');
    $('#content').innerHTML=`<div class="panel empty"><strong>Configuration unavailable</strong><p>${escapeHtml(error.message)}</p><p>Correct the deployment configuration, then reload this page.</p></div>`;
    $('#sync-status').textContent='Configuration could not be loaded';
  }
};
start();
