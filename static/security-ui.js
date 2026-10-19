export function createSecurityUI({esc,openModal,refresh,getState,getCurrent}) {
  let csrf='', user=null;
  async function request(path,data) {
    const res=await fetch('/api'+path,data===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':csrf},body:JSON.stringify(data)});
    const result=await res.json();
    if(!res.ok)throw Error(result.error || 'Request failed.');
    return result;
  }
  async function start() {
    const status=await request('/auth/status');
    try {const me=await request('/auth/me');csrf=me.csrf;user=me.user;await refresh();}
    catch(error) {login(status.setup_required);}
  }
  function login(setup=false) {
    user=null;csrf='';
    document.querySelector('#app').innerHTML=`<main class="setup-screen"><img class="setup-logo" src="/logo.png?v=transparent" alt="Solution ATLAS" width="2172" height="724"><h1>${setup?'Create the first administrator':'Sign in'}</h1><section class="panel"><div class="panel-body"><form id="security-login"><input type="hidden" name="setup" value="${setup}">${setup?'<label>Local setup token<input name="token" type="password" required autocomplete="off"></label><p class="hint">Read data/bootstrap-token.txt in the project folder. This single-use token protects initial setup.</p><label>Your name<input name="name" required maxlength="150" autocomplete="name"></label>':''}<label>Username<input name="username" required autocomplete="username"></label><label>Password<input name="password" type="password" required minlength="12" maxlength="256" autocomplete="${setup?'new-password':'current-password'}"></label><p class="inline-error" id="security-error"></p><button class="btn primary" type="submit">${setup?'Create account':'Sign in'}</button></form></div></section></main>`;
  }
  function bar() {return `<div class="action-row"><small>${esc(user?.roles.join(', ') || '')}</small><button class="btn small" data-security="account">Account</button>${user?.roles.includes('Administrator')?'<button class="btn small" data-security="admin">Users & audit</button>':''}<button class="btn small" data-security="logout">Sign out</button></div>`;}
  function panel(record,kind) {
    const s=record.security || {},reviewer=user?.roles.includes('Reviewer');
    return `<section class="panel mt"><div class="panel-body"><h3>Security & AI permission</h3><p>${esc(s.status || 'Pending review')} · ${esc(s.classification || 'Restricted')} · External AI ${s.external_ai?'allowed for reviewed content':'blocked'}</p>${s.reviewer?`<p class="hint">Reviewed by ${esc(s.reviewer)} · ${esc(s.at)}</p>`:''}${s.findings?.length?`<p class="inline-error">${s.findings.map(esc).join(' · ')}</p>`:''}<p class="hint">New or changed content requires independent review. Confidential and Restricted content remains local.</p><div class="action-row">${reviewer?`<button class="btn" data-security="review" data-kind="${kind}" data-id="${esc(record.id)}">Review security</button>`:''}${user?.roles.includes('Consultant')?`<button class="btn" data-security="redact" data-kind="${kind}" data-id="${esc(record.id)}">Review / redact text</button>`:''}</div></div></section>`;
  }
  function applyPermissions(root=document) {
    const roles=user?.roles || [];
    if(!roles.includes('Consultant'))root.querySelectorAll('[data-action="new"],[data-action="knowledge-new"],[data-action="analyze"],[data-action="reindex"],[data-action="check-ai"],[data-action="advance-lifecycle"],[data-action="close-rejected"],[data-action="promote"],[data-decision],[data-history],#note-form button,#outcome-form button,.solutioning-form button,#history-search-form button').forEach(el=>{el.disabled=true;el.title='Consultant role required';});
    if(!roles.includes('Reviewer'))root.querySelectorAll('[data-action="review-source"]').forEach(el=>{el.disabled=true;el.title='Reviewer role required';});
    if(!roles.includes('Approver'))root.querySelectorAll('[data-action="approval"]').forEach(el=>{el.disabled=true;el.title='Approver role required';});
  }
  function showError(message) {
    const error=document.querySelector('#modal[open] #form-error') || document.querySelector('#security-error');
    if(error){error.textContent=message;error.classList.remove('hidden');error.scrollIntoView({block:'nearest'});}
    else {const notice=document.createElement('p');notice.className='inline-error';notice.setAttribute('role','alert');notice.textContent=message;document.querySelector('#app').prepend(notice);}
  }
  function syncDisclosure(form) {
    if(!form)return;
    const classification=form.elements.classification.value, decision=form.elements.status.value;
    const screened=form.dataset.screeningBlocked==='true', checkbox=form.elements.external_ai;
    checkbox.disabled=classification!=='Internal'||decision!=='Approved'||screened;
    if(checkbox.disabled)checkbox.checked=false;
    form.querySelector('#security-ai-hint').textContent=screened
      ? 'External AI is blocked by the screening findings above. Redact the flagged content and reopen this review.'
      : classification!=='Internal'
      ? 'Confidential and Restricted content stays local. Choose Internal only if the content meets your company policy for external AI processing.'
      : decision!=='Approved'
      ? 'Rejected content cannot be sent to Gemini. External AI permission requires an Approved decision.'
      : 'You may explicitly allow this reviewed Internal content to be sent to Gemini. Leaving this unchecked keeps external AI blocked.';
  }
  async function action(el) {
    const action=el.dataset.security;
    if(action==='logout'){await request('/auth/logout',{});location.reload();}
    if(action==='account')openModal('Change password',`<form id="security-password"><label>Current password<input name="current_password" type="password" autocomplete="current-password" required></label><label>New password<input name="password" type="password" autocomplete="new-password" minlength="12" maxlength="256" required></label><p class="hint">All your sessions will end after changing your password.</p><button class="btn primary mt">Change password</button></form>`);
    if(action==='admin') {
      const [users,audit]=await Promise.all([request('/admin/users'),request('/admin/audit')]);
      openModal('Users and security audit',`<h3>Accounts</h3>${users.users.map(u=>`<p>${esc(u.name)} · ${esc(u.username)} · ${esc(u.roles.join(', '))} · ${esc(u.customers.join(', '))} · ${u.active?'Active':'Disabled'} ${u.active&&u.id!==user.id?`<button class="btn small" data-security="disable" data-id="${u.id}">Disable</button>`:''}</p>`).join('')}<form id="security-user"><h3 class="mt">Create account</h3><label>Name<input name="name" required maxlength="150"></label><label>Username<input name="username" required autocomplete="off"></label><label>Initial password<input name="password" type="password" required minlength="12" maxlength="256" autocomplete="new-password"></label><label>Customer scopes (one per line)<textarea name="customers" required>${esc(getState().customer)}</textarea></label><p>Roles</p>${['Viewer','Consultant','Reviewer','Approver','Administrator'].map(r=>`<label class="check"><input name="roles" type="checkbox" value="${r}">${r}</label>`).join('')}<button class="btn primary mt">Create user</button></form><details class="mt"><summary>Latest 200 security events</summary>${audit.events.map(e=>`<p>${esc(e.at)} · ${esc(e.actor_id)} · ${esc(e.action)} · ${esc(e.record_id)} · ${esc(e.result)}</p>`).join('')}</details>`);
    }
    if(action==='disable'){await request(`/admin/users/${el.dataset.id}/disable`,{});await actionAdmin();}
    if(action==='review'||action==='redact') {
      const kind=el.dataset.kind, record=(kind==='sources'?getState().sources:getState().investigations).find(r=>r.id===el.dataset.id);
      const content=kind==='sources'?record.content:record.description;
      const screening=await request('/security/screen',{record_kind:kind,record_id:record.id,revision:record.revision});
      const hidden=`<input type="hidden" name="kind" value="${kind}"><input type="hidden" name="record_id" value="${esc(record.id)}"><input type="hidden" name="revision" value="${record.revision}">`;
      if(action==='redact')openModal('Review and redact text',`<form id="security-redact">${hidden}<p>Screening: ${esc(screening.findings.join(', ') || 'No patterns detected; manual review is still required.')}</p><label>Title<input name="title" required maxlength="200" value="${esc(record.title)}"></label><label>Content<textarea name="content" rows="14" required maxlength="120000">${esc(content)}</textarea></label><label>Reason<textarea name="notes" required minlength="5" maxlength="4000"></textarea></label><p class="hint">Changes invalidate security approval and AI results. Source indexes are removed. Existing history and backups may retain earlier content; this is not a complete erasure operation.</p><button class="btn primary">Save revised text</button></form>`);
      else {
        const policy=record.security || {};
        openModal('Review security and AI disclosure',`<form id="security-review" data-screening-blocked="${screening.findings.length>0}">${hidden}<h3>${esc(record.title)}</h3><p>Screening: ${esc(screening.findings.join(', ') || 'No patterns detected; manual review is still required.')}</p><details><summary>Inspect record text and metadata</summary><pre class="source-content">${esc(JSON.stringify(record,(key,value)=>['analysis','security_history'].includes(key)?undefined:value,2))}</pre></details><label>Classification<select name="classification">${['Restricted','Confidential','Internal'].map(value=>`<option ${value===(policy.classification || 'Restricted')?'selected':''}>${value}</option>`).join('')}</select></label><label>Decision<select name="status"><option ${policy.status!=='Rejected'?'selected':''}>Approved</option><option ${policy.status==='Rejected'?'selected':''}>Rejected</option></select></label><label class="check"><input type="checkbox" name="external_ai" aria-describedby="security-ai-hint" ${policy.external_ai===true?'checked':''}> Allow this reviewed Internal content to be sent to Google Gemini</label><p class="hint" id="security-ai-hint" role="status"></p><label>Review notes<textarea name="notes" required minlength="5" maxlength="4000">${esc(policy.notes || '')}</textarea></label><p class="hint">Review applies to this content version. An independent reviewer is required.</p><button class="btn primary">Record security decision</button></form>`);
        syncDisclosure(document.querySelector('#security-review'));
      }
    }
  }
  async function actionAdmin(){return action({dataset:{security:'admin'}});}
  async function submit(form) {
    const fd=new FormData(form),data=Object.fromEntries(fd);
    if(form.id==='security-login'){
      if(data.setup==='true')await request('/auth/bootstrap',data);
      const me=await request('/auth/login',data);csrf=me.csrf;user=me.user;await refresh();return;
    }
    if(form.id==='security-password'){await request('/auth/password',data);location.reload();return;}
    if(form.id==='security-user'){await request('/admin/users',{...data,roles:fd.getAll('roles'),customers:data.customers.split('\n').map(s=>s.trim()).filter(Boolean)});await actionAdmin();return;}
    if(form.id==='security-review')await request(`/${data.kind}/${data.record_id}/security-review`,{...data,revision:Number(data.revision),external_ai:fd.has('external_ai')});
    if(form.id==='security-redact')await request(`/${data.kind}/${data.record_id}/redact`,{...data,revision:Number(data.revision)});
    document.querySelector('#modal').close();await refresh();
  }
  document.addEventListener('click',async event=>{
    const el=event.target.closest('[data-security]');if(!el)return;
    el.disabled=true;try{await action(el);}catch(e){showError(e.message);}finally{el.disabled=false;}
  });
  document.addEventListener('change',event=>{
    if(event.target.matches('#security-review select[name=classification],#security-review select[name=status]'))syncDisclosure(event.target.form);
  });
  document.addEventListener('submit',async event=>{
    const form=event.target;if(!form.id.startsWith('security-'))return;
    event.preventDefault();const button=form.querySelector('button[type="submit"],button:not([type])');if(button)button.disabled=true;
    try{await submit(form);}catch(e){showError(e.message);}finally{if(button)button.disabled=false;}
  });
  return {start,bar,panel,applyPermissions,csrf:()=>csrf,user:()=>user};
}
