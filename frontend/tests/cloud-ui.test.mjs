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
      '#auth-password':{value:'',focus(){}},'#auth-username':{value:''},
      '#auth-error':{textContent:'',hidden:true},'[type="submit"]':{disabled:false},
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
