import { escapeHtml as e } from './presentation.js';
import { icon } from './icons.js';

const REPOSITORY='https://github.com/Atharvabagul84/edgeops';
const brandMark='<svg viewBox="0 0 32 32" fill="none" aria-hidden="true"><path d="m6 10 10-5 10 5-10 5ZM6 16l10 5 10-5M6 22l10 5 10-5" stroke="currentColor" stroke-width="2.3" stroke-linejoin="round"/></svg>';
const externalLink=(href,label)=>`<a href="${href}" target="_blank" rel="noopener noreferrer">${label}${icon('external')}<span class="sr-only"> (opens in a new tab)</span></a>`;

// The shell has three views: a neutral boot screen until cloud-config.json is known, the full-screen sign-in, and the dashboard.
export const shellView = (config,session) => !config ? 'boot' : config.mode==='aws' && session?.status!=='authenticated' ? 'signin' : 'app';

// Signed-out visitors learn what the project is and where to explore it. Nothing names the workspace owner or shows fleet data.
const signinAbout = () => `<div class="signin-brand"><span class="brand-mark">${brandMark}</span><span>edge<span class="brand-light">ops</span><small>FLEET RELIABILITY</small></span></div><div class="signin-about"><p class="signin-eyebrow">LIVE AWS DEMO · SYNTHETIC FLEET</p><p class="signin-pitch">When an edge device loses its connection, its telemetry shouldn’t be lost or counted twice.</p><ul class="signin-points"><li>${icon('check')}Durable offline outbox with idempotent replay and duplicate suppression</li><li>${icon('check')}AWS serverless on Terraform: Cognito, API Gateway, Lambda, SQS with a dead-letter queue, DynamoDB</li><li>${icon('check')}Guarded release pipeline with a recorded rollback rehearsal</li></ul><section class="signin-visitor" aria-labelledby="signin-visitor-title"><h2 id="signin-visitor-title">No operator account?</h2><p>Sign-in is limited to accounts the workspace owner creates. You can still explore the project:</p><ul><li>${externalLink(REPOSITORY,'Source code and README on GitHub')}</li><li>${externalLink(`${REPOSITORY}#readme`,'Dashboard screenshots')}</li><li>${externalLink(`${REPOSITORY}/blob/main/docs/guides/local-demo.md`,'Recovery demo walkthrough')}</li></ul><p>Or ${externalLink(`${REPOSITORY}#run-it-locally`,'run it locally in one command')} with Python 3.11+ and no dependencies:</p><code>python3 -m backend.server</code></section><p class="signin-footnote">All devices, readings and incidents are synthetic demonstration data.</p></div>`;

const field = (id,label,input) => `<div class="auth-field"><label for="${id}">${label}</label>${input}</div>`;
const passwordField = (setup) => field('auth-password',setup ? 'New password' : 'Password',`<div class="password-field"><input id="auth-password" type="password" autocomplete="${setup ? 'new-password' : 'current-password'}" required ${setup ? 'minlength="12"' : ''} maxlength="256" aria-describedby="auth-caps${setup ? ' auth-policy' : ''}"><button id="auth-toggle" class="password-toggle" type="button" aria-controls="auth-password" aria-pressed="false" aria-label="Show password">${icon('eye')}</button></div><p id="auth-caps" class="auth-caps" hidden>Caps Lock is on.</p>`);

export const authForm = (session) => {
  const setup=session.status==='new-password-required';
  const fields=setup ? (session.requiredAttributes || []).map((name,index) => field(`auth-attribute-${index}`,name==='email' ? 'Email' : e(name),`<input id="auth-attribute-${index}" data-attribute="${e(name)}" type="${name==='email' ? 'email' : 'text'}" ${name==='email' ? 'autocomplete="email" ' : ''}required maxlength="2048">`)).join('')
    : field('auth-username','Email','<input id="auth-username" type="email" autocomplete="username" autocapitalize="none" spellcheck="false" required maxlength="128">');
  const card=`<div class="auth-card"><div class="auth-icon">${icon('shield')}</div><span class="tag blue-tag">AWS WORKSPACE</span><h1 id="auth-title">${setup ? 'Choose your password' : 'Sign in to your fleet'}</h1><p>${setup ? `Finish setting up ${e(session.username)} with a new password.` : 'Use the email address and password the workspace owner set up for you in Amazon Cognito.'}</p>${session.reason==='expired' ? '<p class="auth-notice">Your session expired. Sign in again to continue.</p>' : ''}<form id="auth-form" aria-labelledby="auth-title">${fields}${passwordField(setup)}${setup ? '<p id="auth-policy" class="auth-hint">Use at least 12 characters, including uppercase, lowercase, a number, and a symbol.</p>' : ''}<p id="auth-error" class="auth-error" role="alert" hidden></p><button class="button primary" type="submit">${setup ? 'Set password and continue' : 'Sign in'}</button>${setup ? '<button id="auth-cancel" class="text-button" type="button">Back to sign in</button>' : ''}</form>${setup ? '' : '<div class="auth-help"><strong>Forgot your password, or did it expire?</strong><p>Accounts are created by the workspace owner and there is no self-service reset. Ask the workspace owner to set a temporary password (it expires after 1 day).</p></div>'}<p class="auth-hint">Sessions stay in this tab’s memory. Reloading requires sign-in.</p></div>`;
  return `${signinAbout()}<main class="signin-main">${card}</main>`;
};

const setPasswordVisible=(form,visible)=>{
  const input=form.querySelector('#auth-password');
  const toggle=form.querySelector('#auth-toggle');
  if(input) input.type=visible ? 'text' : 'password';
  if(!toggle) return;
  toggle.setAttribute('aria-pressed',String(visible));
  toggle.innerHTML=icon(visible ? 'eyeOff' : 'eye');
};
const capsLock=(form,event)=>{
  const hint=form.querySelector('#auth-caps');
  if(hint && event.target?.id==='auth-password' && typeof event.getModifierState==='function') hint.hidden=!event.getModifierState('CapsLock');
};

const authViews=new WeakMap();
const updateAuthForm=(container,ui)=>{
  const form=container.querySelector('#auth-form');
  if(!form) return;
  const submit=form.querySelector('[type="submit"]');
  const error=form.querySelector('#auth-error');
  const username=form.querySelector('#auth-username');
  if(username && ui.username) username.value=ui.username;
  error.textContent=ui.error;
  error.hidden=!ui.error;
  submit.disabled=ui.pending;
  submit.textContent=ui.pending ? 'Signing in…' : ui.session.status==='new-password-required' ? 'Set password and continue' : 'Sign in';
  form.setAttribute('aria-busy',String(ui.pending));
  form.querySelectorAll('input,.password-toggle').forEach(input=>{input.disabled=ui.pending;});
  const cancel=container.querySelector('#auth-cancel');
  if(cancel) cancel.disabled=ui.pending;
};

export const renderAuth = (container,auth,session) => {
  const ui=authViews.get(container) || {pending:false,error:'',username:'',session};
  ui.session=session;
  authViews.set(container,ui);
  container.hidden=session.status==='authenticated';
  if (container.hidden) { container.replaceChildren(); return; }
  container.innerHTML=authForm(session);
  updateAuthForm(container,ui);
  const setup=session.status==='new-password-required';
  container.querySelector(setup && session.requiredAttributes?.length ? '#auth-attribute-0' : setup || ui.username ? '#auth-password' : '#auth-username')?.focus();
  container.querySelector('#auth-cancel')?.addEventListener('click',() => auth.signOut());
  const liveForm=container.querySelector('#auth-form');
  liveForm.addEventListener('click',event => {
    if(event.target.closest?.('#auth-toggle')) setPasswordVisible(liveForm,liveForm.querySelector('#auth-toggle').getAttribute('aria-pressed')!=='true');
  });
  liveForm.addEventListener('keydown',event => capsLock(liveForm,event));
  liveForm.addEventListener('keyup',event => capsLock(liveForm,event));
  liveForm.addEventListener('submit',async event => {
    event.preventDefault();
    if(ui.pending) return;
    const form=event.currentTarget;
    const password=form.querySelector('#auth-password');
    const secret=password.value;
    password.value='';
    setPasswordVisible(form,false);
    const attributes=Object.fromEntries([...form.querySelectorAll('[data-attribute]')].map(input => [input.dataset.attribute,input.value.trim()]));
    const username=form.querySelector('#auth-username')?.value.trim() || session.username;
    ui.username=username; ui.pending=true; ui.error='';
    updateAuthForm(container,ui);
    try {
      if(session.status==='new-password-required') await auth.completeNewPassword(secret,attributes);
      else await auth.signIn(username,secret);
    } catch(failure) { if(failure.code!=='AUTH_CANCELLED') ui.error=failure.message; }
    finally {
      ui.pending=false;
      updateAuthForm(container,ui);
      container.querySelector('#auth-password')?.focus();
    }
  });
};

export const downloadDiagnostics = (data) => {
  const json=JSON.stringify(data,null,2);
  document.querySelector('#diagnostics-dialog')?.close();
  const dialog=document.createElement('dialog');
  dialog.id='diagnostics-dialog';
  dialog.className='diagnostics-dialog';
  dialog.setAttribute('aria-labelledby','diagnostics-title');
  dialog.innerHTML='<span class="tag blue-tag">FLEET DIAGNOSTICS</span><h2 id="diagnostics-title">Inspect your diagnostic report</h2><p>If download is blocked, select and copy JSON below.</p><label for="diagnostics-json">Diagnostic JSON</label><textarea id="diagnostics-json" readonly spellcheck="false" wrap="off"></textarea><p id="diagnostics-status" role="status" aria-live="polite"></p><div class="dialog-actions"><button id="diagnostics-select" class="button secondary" type="button">Select JSON</button><button id="diagnostics-close" class="button secondary" type="button">Close</button><button id="diagnostics-download" class="button primary" type="button">Download JSON</button></div>';
  dialog.querySelector('#diagnostics-json').value=json;
  let url=null;
  dialog.querySelector('#diagnostics-download').addEventListener('click',()=>{
    if(!url) url=URL.createObjectURL(new Blob([json],{type:'application/json'}));
    const link=document.createElement('a');
    link.href=url; link.download='edgeops-diagnostics.json';
    dialog.append(link); link.click(); link.remove();
    dialog.querySelector('#diagnostics-status').textContent='Download requested. If no file appears, select and copy the JSON.';
  });
  dialog.querySelector('#diagnostics-select').addEventListener('click',()=>{
    const textarea=dialog.querySelector('#diagnostics-json');
    textarea.focus(); textarea.select();
    dialog.querySelector('#diagnostics-status').textContent='JSON selected. Copy it using your keyboard or browser menu.';
  });
  dialog.querySelector('#diagnostics-close').addEventListener('click',()=>dialog.close());
  dialog.addEventListener('close',()=>{if(url) URL.revokeObjectURL(url);dialog.remove();},{once:true});
  document.body.append(dialog);
  dialog.showModal();
};
