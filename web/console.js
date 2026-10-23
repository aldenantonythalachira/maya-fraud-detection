const $ = s => document.querySelector(s);
const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const money = p => new Intl.NumberFormat('en-IN',{style:'currency',currency:'INR'}).format(p/100);
let credential = '', kind = 'controller', selected = '', roleData, timer, busy = false;
const fragment = new URLSearchParams(location.hash.slice(1));
if (fragment.has('access')) { credential = fragment.get('access'); kind = 'role'; }
history.replaceState(null, '', location.pathname);
const notice = e => { $('#notice').textContent = e.message || e; $('#notice').className = 'visible'; };
async function api(path, data) {
  const headers = {[kind === 'controller' ? 'X-Maya-Controller' : 'X-Maya-Access']:credential};
  if (data !== undefined) headers['Content-Type']='application/json';
  const response = await fetch('/api/' + path,{method:data === undefined ? 'GET' : 'POST', headers, body:data === undefined ? undefined : JSON.stringify(data)});
  const body = await response.json();
  if (!response.ok) throw new Error(typeof body.detail === 'string' ? body.detail : 'Check the request.');
  return body;
}
async function guarded(task) { if(busy) return; busy=true; try { await task(); } catch(e) { notice(e); } finally { busy=false; } }
async function load() {
  if (kind === 'controller') {
    const worlds = await api('controller/worlds');
    if (!worlds.some(w=>w.id===selected)) selected=worlds[0]?.id || '';
    $('#content').innerHTML = `<section class="panel"><label for="world">Wallet</label><select class="field" id="world">${worlds.map(w=>`<option value="${esc(w.id)}" ${w.id===selected?'selected':''}>${esc(w.preset)} · ${w.seed} · ${esc(w.id.slice(0,8))}</option>`).join('')}</select><button data-action="refresh" class="secondary bottom-space">Refresh</button></section>${selected ? `<section class="panel"><h2>Simulator controls</h2><div class="button-stack"><button class="secondary" data-action="advance">Advance virtual time 1 hour</button><label for="report-account">Reported account ID</label><input id="report-account" class="field" type="number" min="0" value="4"><button class="secondary" data-action="report">Add synthetic report</button><label for="review-id">Original review ID</label><input id="review-id" class="field"><button class="secondary" data-action="counterfactual">Evaluate delayed reports separately</button><label for="provider">Synthetic provider</label><select id="provider" class="field"><option>FRI</option><option>MuleHunter</option><option>NCRP</option></select><label for="provider-state">Availability</label><select id="provider-state" class="field"><option>unavailable</option><option>available</option><option>delayed</option><option>error</option></select><button class="secondary" data-action="provider">Set provider state</button></div></section><section class="panel"><h2>Independent role access</h2><p class="muted">Expires after 30 minutes. Contact access also requires payer consent.</p><div class="button-stack"><button class="secondary" data-action="analyst">Issue analyst access</button><button class="secondary" data-action="contact">Issue trusted-contact access</button><button class="secondary" data-action="revoke">Revoke all independent access</button></div><div id="grant-result"></div></section>` : '<p>No wallets yet. Create one in the payer view.</p>'}`;
    $('#world').addEventListener('change', e=>{selected=e.target.value;});
  } else {
    roleData=await api('access/view');
    $('#role-title').textContent=roleData.role==='analyst'?'Analyst console':'Trusted-contact inbox';
    if (roleData.role==='contact') {
      $('#content').innerHTML=`<section class="panel"><h2>Held-payment alerts</h2>${roleData.alerts.map(a=>`<div class="case-row"><strong>${esc(a.message)}</strong><p class="micro">Payment ${esc(a.payment_id.slice(0,8))} · event ${a.sequence}</p></div>`).join('') || '<p>No unread alerts</p>'}<button class="secondary" data-action="acknowledge">Acknowledge alerts</button></section>`;
    } else if(roleData.role==='analyst') {
      $('#content').innerHTML=roleData.cases.map(c=>`<section class="panel"><h2>${money(c.payment.amount_paise)}</h2><p>Payment ${esc(c.payment.id.slice(0,8))} · revision ${c.payment.revision}</p><p>Virtual hold: ${Math.max(0,Math.ceil((c.payment.hold_until-roleData.now)/60))} min</p><ul>${c.review?.decision.reasons.map(r=>`<li>${esc(r)}</li>`).join('') || ''}</ul><p class="micro">Review ${esc(c.review?.id)} · ${c.payment.analyst_review===c.review?.id?'Approved for this review':'Not approved for this review'}</p><details><summary>Evidence and versions</summary><pre>${esc(JSON.stringify(c.review,null,2))}</pre></details><div class="button-stack bottom-space"><button class="secondary" data-approve="${esc(c.payment.id)}" data-review="${esc(c.review?.id)}">Approve this review</button><button class="secondary" data-cancel="${esc(c.payment.id)}" data-review="${esc(c.review?.id)}">Cancel payment</button><button class="secondary" data-file="${esc(c.payment.id)}" data-review="${esc(c.review?.id)}">File synthetic NCRP case</button></div></section>`).join('') || '<section class="panel">No pending analyst cases</section>';
    } else throw new Error('This role is read-only. Use the recipient link in the wallet.');
    $('#content').insertAdjacentHTML('afterbegin','<button class="secondary" data-action="refresh">Refresh</button>');
  }
  $('#login').hidden=true; $('#logout').hidden=false;
}
$('#login').addEventListener('submit',e=>{e.preventDefault(); credential=$('#access-key').value; $('#access-key').value=''; kind=$('#role-type').value; guarded(load);});
$('#logout').addEventListener('click',()=>{credential=''; clearTimeout(timer); $('#content').innerHTML=''; $('#login').hidden=false; $('#logout').hidden=true;});
$('#content').addEventListener('click',e=>guarded(async()=>{
  const b=e.target.closest('button'); if(!b) return;
  const action=b.dataset.action;
  if(action==='refresh') return load();
  if(action==='analyst' || action==='contact') {
    const grant=await api(`controller/worlds/${selected}/grants`,{role:action});
    $('#grant-result').innerHTML=`<a class="secondary grant-link" target="_blank" rel="noopener" href="/console#access=${encodeURIComponent(grant.token)}">Open ${esc(action)} view ↗</a>`;
    return;
  }
  if(action==='advance' || action==='report' || action==='provider' || action==='revoke') {
    await api(`controller/worlds/${selected}/control`,{operation:action,seconds:action==='advance'?3600:0,account:action==='report'?Number($('#report-account').value):null, provider:action==='provider'?$('#provider').value:null, provider_state:action==='provider'?$('#provider-state').value:null});
    notice('Control recorded. Refresh the payer review.'); return;
  }
  if(action==='counterfactual') {
    const result=await api(`controller/worlds/${selected}/counterfactual`,{parent:$('#review-id').value.trim()});
    $('#grant-result').innerHTML=`<a class="secondary grant-link" target="_blank" rel="noopener" href="/?world=${esc(result.world)}">Open separate wallet ↗</a><p>Original: ${esc(result.original_action)} → separate evaluation: ${esc(result.review.decision.action)}</p><pre>${esc(JSON.stringify(result,null,2))}</pre>`;
    return;
  }
  if(action==='acknowledge') await api('access/action',{operation:'acknowledge'});
  if(b.dataset.approve || b.dataset.cancel || b.dataset.file) await api('access/action',{operation:b.dataset.approve?'approve':b.dataset.file?'file_report':'cancel',payment_id:b.dataset.approve || b.dataset.cancel || b.dataset.file,review_id:b.dataset.review});
  await load();
}));
if(credential) guarded(load);
