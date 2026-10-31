import test from 'node:test';
import assert from 'node:assert/strict';

test('password setup renders requested Cognito attributes safely without old password fields', async () => {
  const { authForm } = await import('../cloud-ui.js');
  const html = authForm({status:'new-password-required',username:'<operator>',requiredAttributes:['email','custom:<team>']});
  assert.match(html, /autocomplete="new-password"/);
  assert.match(html, /data-attribute="email"/);
  assert.match(html, /custom:&lt;team&gt;/);
  assert.doesNotMatch(html, /<operator>|<team>|autocomplete="current-password"/);
});

test('signed-out cloud view requests operator credentials and explains expiring sessions', async () => {
  const { authForm } = await import('../cloud-ui.js');
  const html = authForm({status:'signed-out',reason:'expired'});
  assert.match(html, /session expired/i);
  assert.match(html, /autocomplete="username"/);
  assert.match(html, /autocomplete="current-password"/);
  assert.doesNotMatch(html, /value=".*password/);
});

test('sign-in asks for the Cognito email username and explains admin-only password resets', async () => {
  const { authForm } = await import('../cloud-ui.js');
  const html = authForm({status:'signed-out'});
  assert.match(html, /<label for="auth-username">Email<\/label><input id="auth-username" type="email" autocomplete="username"/);
  assert.doesNotMatch(html, /Operator username/);
  assert.equal(html.match(/<h1\b/g).length, 1);
  assert.match(html, /<h1 id="auth-title">Sign in to your fleet<\/h1>/);
  assert.match(html, /Ask the workspace owner to set a temporary password \(it expires after 1 day\)/);
  assert.match(html, /aria-controls="auth-password" aria-pressed="false" aria-label="Show password"/);
  assert.match(html, /id="auth-caps" class="auth-caps" hidden/);
  assert.doesNotMatch(html, /↗/);
});

test('signed-out visitors see project context and links but no workspace identity', async () => {
  const { authForm } = await import('../cloud-ui.js');
  const html = authForm({status:'signed-out'});
  assert.doesNotMatch(html.replace(/href="[^"]*"/g,''), /Atharva|Project owner|workspace-avatar|topbar-avatar|>AB</);
  assert.match(html, /href="https:\/\/github\.com\/Atharvabagul84\/edgeops" target="_blank" rel="noopener noreferrer"/);
  assert.match(html, /run it locally in one command/);
  assert.match(html, /<code>python3 -m backend\.server<\/code>/);
  assert.match(html, /synthetic/);
  for (const link of html.match(/<a [^>]*>/g)) assert.match(link, /target="_blank" rel="noopener noreferrer"/);
});

test('password setup escapes the challenged username and labels the email attribute', async () => {
  const { authForm } = await import('../cloud-ui.js');
  const html = authForm({status:'new-password-required',username:'<img src=x onerror=alert(1)>',requiredAttributes:['email']});
  assert.match(html, /&lt;img src=x onerror=alert\(1\)&gt;/);
  assert.doesNotMatch(html, /<img/);
  assert.match(html, /<label for="auth-attribute-0">Email<\/label><input id="auth-attribute-0" data-attribute="email" type="email" autocomplete="email"/);
  assert.match(html, /aria-describedby="auth-caps auth-policy"/);
  assert.doesNotMatch(html, /temporary password \(it expires/);
});

test('shell stays neutral until config loads, then shows sign-in only for signed-out cloud sessions', async () => {
  const { shellView } = await import('../cloud-ui.js');
  const aws={mode:'aws'};
  assert.equal(shellView(undefined,undefined), 'boot');
  assert.equal(shellView(null,{status:'authenticated'}), 'boot');
  assert.equal(shellView({mode:'local'},undefined), 'app');
  for (const status of ['signed-out','new-password-required']) assert.equal(shellView(aws,{status}), 'signin');
  assert.equal(shellView(aws,{status:'authenticated'}), 'app');
});

test('page boots without dashboard chrome and the sign-in view sits outside the dashboard shell', async () => {
  const { readFile } = await import('node:fs/promises');
  const html = await readFile(new URL('../index.html', import.meta.url), 'utf8');
  const css = await readFile(new URL('../cloud.css', import.meta.url), 'utf8');
  assert.match(html, /<body data-view="boot">/);
  assert.ok(html.indexOf('id="auth-panel"') < html.indexOf('class="workspace-shell"'));
  assert.ok(html.indexOf('id="auth-panel"') < html.indexOf('class="sidebar"'));
  assert.match(css, /body\[data-view=boot\] :is\(\.sidebar,\.workspace-shell,\.skip-link\)/);
  assert.match(css, /body\[data-view=signin\] :is\(\.sidebar,\.workspace-shell,\.skip-link\)/);
});

test('cloud architecture distinguishes SQS ingestion from synchronous demo controls', async () => {
  const { architectureView, pipelinePanel } = await import('../operations.js');
  const html = architectureView('aws');
  assert.match(html, /Cognito/);
  assert.match(html, /SQS/);
  assert.match(html, /synchronous/i);
  assert.doesNotMatch(html, /Running on your machine|LOCAL MVP/);
  const pipeline = pipelinePanel({mode:'aws',pipeline:{accepted:5,processed:5,duplicates:1,deadLetters:0}});
  assert.match(pipeline, /CloudWatch/);
  assert.doesNotMatch(pipeline, /SQLite-backed/);
});

// Minimal DOM adapter exercises replacement of a live form during an auth callback.
const authContainer = () => {
  const container={hidden:false,form:null,replaceChildren(){this.form=null;}};
  container.querySelector=selector=>selector==='#auth-form'?container.form:container.form?.querySelector(selector);
  Object.defineProperty(container,'innerHTML',{set(){
    const fields={
      '#auth-password':{id:'auth-password',type:'password',value:'',focus(){container.focused='#auth-password';}},
      '#auth-username':{value:'',focus(){container.focused='#auth-username';}},
      '#auth-error':{textContent:'',hidden:true},'[type="submit"]':{disabled:false},'#auth-caps':{hidden:true},
      '#auth-toggle':{attributes:{'aria-pressed':'false'},innerHTML:'',
        getAttribute(name){return this.attributes[name];},setAttribute(name,value){this.attributes[name]=value;}},
    };
    container.form={handlers:{},querySelector:selector=>fields[selector],querySelectorAll:()=>[],
      addEventListener(type,handler){this.handlers[type]=handler;},setAttribute(){}};
  }});
  return container;
};

test('sign-in errors and pending state stay on the live form after synchronous auth rerenders',async()=>{
  const {renderAuth}=await import('../cloud-ui.js');
  const container=authContainer();
  const session={status:'signed-out'};
  let rejectSignIn,calls=0;
  const auth={signIn:async()=>{
    calls++;
    renderAuth(container,auth,session);
    return new Promise((resolve,reject)=>{rejectSignIn=reject;});
  }};
  renderAuth(container,auth,session);
  const oldForm=container.form;
  oldForm.querySelector('#auth-username').value='operator';
  oldForm.querySelector('#auth-password').value='wrong-password';
  const pending=oldForm.handlers.submit({preventDefault(){},currentTarget:oldForm});
  assert.notEqual(container.form,oldForm);
  assert.equal(container.form.querySelector('[type="submit"]').disabled,true);
  assert.equal(oldForm.querySelector('#auth-password').value,'');
  await container.form.handlers.submit({preventDefault(){},currentTarget:container.form});
  assert.equal(calls,1);
  rejectSignIn(new Error('The username or password is incorrect.'));
  await pending;
  assert.equal(container.form.querySelector('#auth-error').hidden,false);
  assert.match(container.form.querySelector('#auth-error').textContent,/incorrect/);
  assert.equal(container.form.querySelector('[type="submit"]').disabled,false);
  assert.equal(container.form.querySelector('#auth-username').value,'operator');
  assert.equal(container.form.querySelector('#auth-password').value,'');
});

test('sign-in focuses email, toggles password visibility, flags Caps Lock and re-hides on submit',async()=>{
  const {renderAuth}=await import('../cloud-ui.js');
  const container=authContainer();
  renderAuth(container,{signIn:async()=>{}},{status:'signed-out'});
  assert.equal(container.focused,'#auth-username');
  const form=container.form;
  const password=form.querySelector('#auth-password');
  const toggle=form.querySelector('#auth-toggle');
  form.handlers.click({target:{closest:selector=>selector==='#auth-toggle'?toggle:null}});
  assert.equal(password.type,'text');
  assert.equal(toggle.getAttribute('aria-pressed'),'true');
  form.handlers.keydown({target:password,getModifierState:key=>key==='CapsLock'});
  assert.equal(form.querySelector('#auth-caps').hidden,false);
  form.handlers.keyup({target:password,getModifierState:()=>false});
  assert.equal(form.querySelector('#auth-caps').hidden,true);
  form.querySelector('#auth-username').value='operator@example.test';
  password.value='typed-secret';
  await form.handlers.submit({preventDefault(){},currentTarget:form});
  assert.equal(password.type,'password');
  assert.equal(password.value,'');
  assert.equal(toggle.getAttribute('aria-pressed'),'false');
});

test('diagnostics remain inspectable as text and blob URLs are revoked when the dialog closes',async t=>{
  const {downloadDiagnostics}=await import('../cloud-ui.js');
  const originalDocument=globalThis.document;
  const originalCreate=URL.createObjectURL,originalRevoke=URL.revokeObjectURL;
  let dialog,created=0,revoked='',downloads=0;
  const control=()=>({value:'',handlers:{},addEventListener(event,handler){this.handlers[event]=handler;},focus(){},select(){}});
  const fields={'#diagnostics-json':control(),'#diagnostics-download':control(),'#diagnostics-select':control(),'#diagnostics-close':control(),'#diagnostics-status':control()};
  globalThis.document={querySelector:()=>null,body:{append(){}},createElement(type){
    if(type==='a') return {click(){downloads++;},remove(){}};
    dialog={innerHTML:'',handlers:{},querySelector:selector=>fields[selector],setAttribute(){},append(){},
      addEventListener(event,handler){this.handlers[event]=handler;},showModal(){this.open=true;},
      close(){this.open=false;this.handlers.close();},remove(){this.removed=true;}};
    return dialog;
  }};
  URL.createObjectURL=()=>{created++;return 'blob:test-diagnostics';};
  URL.revokeObjectURL=url=>{revoked=url;};
  t.after(()=>{globalThis.document=originalDocument;URL.createObjectURL=originalCreate;URL.revokeObjectURL=originalRevoke;});
  const data={message:'</textarea><script>alert(1)</script>',stats:{ingested:36}};
  downloadDiagnostics(data);
  assert.equal(dialog.open,true);
  assert.equal(fields['#diagnostics-json'].value,JSON.stringify(data,null,2));
  assert.doesNotMatch(dialog.innerHTML,/<script>/);
  assert.match(dialog.innerHTML,/readonly/);
  assert.equal(created,0);
  fields['#diagnostics-download'].handlers.click();
  assert.equal(downloads,1);
  assert.equal(created,1);
  fields['#diagnostics-close'].handlers.click();
  assert.equal(revoked,'blob:test-diagnostics');
  assert.equal(dialog.removed,true);
});
