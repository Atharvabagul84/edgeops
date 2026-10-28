import { escapeHtml as e } from './presentation.js';

export const authForm = (session) => {
  const setup=session.status==='new-password-required';
  const fields=setup ? (session.requiredAttributes || []).map((name,index) => `<label for="auth-attribute-${index}">${e(name)}<input id="auth-attribute-${index}" data-attribute="${e(name)}" type="${name==='email' ? 'email' : 'text'}" required maxlength="2048"></label>`).join('') : '<label for="auth-username">Operator username<input id="auth-username" autocomplete="username" required maxlength="128"></label>';
  return `<div class="auth-icon">↗</div><span class="tag blue-tag">AWS WORKSPACE</span><h2>${setup ? 'Choose your password' : 'Sign in to your fleet'}</h2><p>${setup ? `Finish setting up ${e(session.username)} with a new password.` : 'Use the operator account created in Amazon Cognito.'}</p>${session.reason==='expired' ? '<p class="auth-notice">Your session expired. Sign in again to continue.</p>' : ''}<form id="auth-form">${fields}<label for="auth-password">${setup ? 'New password' : 'Password'}<input id="auth-password" type="password" autocomplete="${setup ? 'new-password' : 'current-password'}" required ${setup ? 'minlength="12"' : ''} maxlength="256"></label>${setup ? '<p class="auth-hint">Use at least 12 characters, including uppercase, lowercase, a number, and a symbol.</p>' : ''}<p id="auth-error" class="auth-error" role="alert" hidden></p><button class="button primary" type="submit">${setup ? 'Set password and continue' : 'Sign in'}</button>${setup ? '<button id="auth-cancel" class="text-button" type="button">Back to sign in</button>' : ''}</form><p class="auth-hint">Sessions stay in this tab’s memory. Reloading requires sign-in.</p>`;
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
  form.querySelectorAll('input').forEach(input=>{input.disabled=ui.pending;});
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
  container.querySelector('#auth-cancel')?.addEventListener('click',() => auth.signOut());
  container.querySelector('#auth-form').addEventListener('submit',async event => {
    event.preventDefault();
    if(ui.pending) return;
    const form=event.currentTarget;
    const password=form.querySelector('#auth-password');
    const secret=password.value;
    password.value='';
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
