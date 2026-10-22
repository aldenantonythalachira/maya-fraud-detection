import {decisionExplorer} from '/assets/explorer.js';
const $ = selector => document.querySelector(selector);
const app = $('#app');
const escape = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const money = paise => new Intl.NumberFormat('en-IN', {style:'currency', currency:'INR', maximumFractionDigits:paise % 100 ? 2 : 0}).format(paise / 100);
const clock = epoch => new Date(epoch * 1000).toLocaleString('en-IN', {day:'numeric', month:'short', hour:'2-digit', minute:'2-digit', timeZone:'Asia/Kolkata'});
const randomSeed = () => crypto.getRandomValues(new Uint32Array(1))[0];
let world, payment, review, previousReview, transfer, stream, events = [], screen = 'home', busy = false, query = '', recipient = 1;
let noticeTimer, observerTimer, lastScreen;
const observeToken = location.pathname === '/recipient' ? (new URLSearchParams(location.hash.slice(1)).get('access') || sessionStorage.getItem('maya-observer')) : new URLSearchParams(location.hash.slice(1)).get('observe');
if (observeToken && location.pathname === '/recipient') sessionStorage.setItem('maya-observer', observeToken);
if (location.hash) history.replaceState(null, '', location.pathname);

async function api(path, data, method = 'POST') {
  const response = await fetch('/api/' + path, data === undefined ? {headers:observeToken ? {'X-Maya-Access':observeToken} : {}} : {method, headers:{'Content-Type':'application/json'}, body:JSON.stringify(data)});
  const body = await response.json();
  if (!response.ok) throw new Error(typeof body.detail === 'string' ? body.detail : 'Check the payment details and try again.');
  return body;
}
const path = suffix => `worlds/${world.id}/${suffix}`;
const account = id => world.accounts.find(a => a.id === Number(id));
const initials = name => name.split(/[ ·]+/).slice(0,2).map(s => s[0]).join('').toUpperCase();
const avatar = id => `<span class="avatar tone-${id % 4}" aria-hidden="true">${escape(initials(account(id)?.name || 'Demo'))}</span>`;
const button = (action, label, cls = 'primary full', extra = '') => `<button type="button" class="${cls}" data-action="${action}" ${extra}>${label}</button>`;
const header = (title, step = '') => `<div class="step-header">${button('home','←','back','aria-label="Back to wallet"')}<div>${step ? `<span class="eyebrow">${step}</span>` : ''}<h1>${title}</h1></div></div>`;
const recipientHeader = () => `<div class="recipient-header">${avatar(recipient)}<div><h2>${escape(account(recipient).name)}</h2><p>${escape(account(recipient).vpa)}</p></div></div>`;

function notify(message, error = false) {
  $('#notice').textContent = message;
  $('#notice').className = 'visible' + (error ? ' error' : '');
  clearTimeout(noticeTimer);
  noticeTimer = setTimeout(() => { $('#notice').className = ''; }, error ? 12000 : 6000);
}

function save() {
  if (!world || observeToken) return;
  localStorage.setItem('maya-world', world.id);
  sessionStorage.setItem('maya-payment', JSON.stringify({world:world.id, payment:payment?.id, review:review?.id}));
}

function render() {
  if (!world) return;
  app.setAttribute('aria-busy', String(screen === 'processing'));
  if (observeToken) return renderObserver();
  if (screen === 'home') home();
  if (screen === 'recipients') recipients();
  if (screen === 'amount') amount();
  if (screen === 'processing') app.innerHTML = header('Reviewing your payment') + `<div class="card loading-card" role="status"><span class="spinner"></span><h2>MAYA is checking the details.</h2></div>`;
  if (screen === 'review') reviewScreen();
  if (screen === 'authorize') authorize();
  if (screen === 'receipt') receipt();
  inspect();
  save();
  if(lastScreen!==screen) { lastScreen=screen; app.focus({preventScroll:true}); }
}

function home() {
  const pending = world.intents.filter(p => p.state === 'pending');
  app.innerHTML = `<div class="greeting"><div><span class="eyebrow">WALLET</span><h1>Your wallet</h1></div><span class="profile">Y</span></div>
    <section class="wallet-card" aria-label="Dummy wallet balance"><span class="eyebrow">AVAILABLE BALANCE</span><div class="balance">${money(account(0).balance_paise)}</div><div class="wallet-bottom"><span><span class="mini-shield">✓</span> MAYA Demo Bank ·· 2048</span><span>SIMULATED</span></div></section>
    <div class="pay-cta">${button('pay','<span aria-hidden="true">↗</span> Pay someone')}${button('observer','Receive ↙','secondary')}</div>
    <div class="section-title"><h2>People you can pay</h2>${button('pay','View all','link-button')}</div><div class="people">${[1,2,3,4].map(id => `<button class="person" data-recipient="${id}">${avatar(id)}<span>${escape(account(id).name.split(' ·')[0])}</span></button>`).join('')}</div>
    <div class="section-title"><h2>History</h2><span class="eyebrow"></span></div><div class="activity">${world.transfers.length ? world.transfers.slice(0,8).map(t => `<button class="activity-row full" data-transfer="${t.id}">${avatar(t.recipient)}<span class="activity-copy"><strong>${escape(account(t.recipient).name)}</strong><small>${clock(t.timestamp)}</small></span><span class="activity-amount">− ${money(t.amount_paise)}<small>Completed</small></span></button>`).join('') : `<div class="empty">No payments yet</div>`}</div>
    <label class="checkbox-label"><input type="checkbox" id="contact-consent" ${world.contact_consent?'checked':''}><span>Share held-payment alerts with my demo trusted contact</span></label>${pending.length ? `<div class="section-title bottom-space"><h2>Saved payments</h2><span class="micro">Not sent</span></div><div class="activity">${pending.slice(0,5).map(p => `<button class="activity-row full" data-resume="${p.id}">${avatar(p.recipient)}<span class="activity-copy"><strong>${escape(account(p.recipient).name)}</strong><small>Pending · revision ${p.revision}</small></span><span class="activity-amount">${money(p.amount_paise)} →</span></button>`).join('')}</div>` : ''}
`;
}

function recipients() {
  app.innerHTML = header('Who are you paying?', 'STEP 1 OF 3') + `<section class="card"><label for="recipient-search">Name or demo UPI ID</label><input class="field" id="recipient-search" placeholder="Search Amma, rent, traders…" autocomplete="off" value="${escape(query)}"><div id="recipient-list" class="selection-list"></div></section>`;
  recipientList();
}

function recipientList() {
  const matches = world.accounts.filter(a => a.id !== 0 && `${a.name} ${a.vpa}`.toLowerCase().includes(query.toLowerCase())).slice(0,20);
  $('#recipient-list').innerHTML = matches.map(a => `<button class="selection-item" data-recipient="${a.id}">${avatar(a.id)}<span><strong>${escape(a.name)}</strong><small>${escape(a.vpa)}</small></span><span class="chevron">→</span></button>`).join('') || '<p class="empty">No matching recipient</p>';
}

function amount() {
  const editing = payment && payment.state === 'pending';
  const paise = editing ? payment.amount_paise : world.default_amount_paise;
  app.innerHTML = header(editing ? 'Update your payment' : 'Enter an amount', 'STEP 2 OF 3') + `<form id="payment-form" class="card">${recipientHeader()}<p class="amount-label">You are sending</p><div class="amount-entry"><span>₹</span><input id="amount" name="amount" type="text" inputmode="decimal" autocomplete="off" aria-label="Amount in rupees" required value="${paise / 100}"></div><p class="available">Available: ${money(account(0).balance_paise)}</p><details ${editing && payment.consent || world.default_message ? 'open' : ''}><summary>Add a message <span class="micro">· optional</span></summary><label for="message">A message you want MAYA to compare</label><textarea class="field" id="message" maxlength="2000" placeholder="For example: Approve to receive your refund">${escape(editing ? payment.text : world.default_message)}</textarea><label class="checkbox-label"><input type="checkbox" id="consent" ${editing && payment.consent ? 'checked' : ''}><span>Share this synthetic message with the local server for review.</span></label></details><div class="divider"></div><button class="primary full" type="submit">Review payment <span aria-hidden="true">→</span></button></form>`;
}

function currentPayment() {
  return world.intents.find(p => p.id === payment?.id) || payment;
}

function staleReason() {
  const p = currentPayment();
  if (!review || !p) return 'Get a fresh review before continuing.';
  if (p.state !== 'pending') return `This payment is ${p.state}.`;
  if (p.revision !== review.payment.revision) return 'Payment details changed. Get a fresh review.';
  if (world.revision !== review.world_revision) return 'Available evidence changed. Get a fresh review.';
  if (world.now >= review.expires_at) return 'This review expired. Get a fresh review.';
  return '';
}

function reviewScreen() {
  const p = currentPayment();
  const d = review.decision;
  const held = p.hold_revision === p.revision && world.now < p.hold_until;
  const analyst = p.hold_revision === p.revision && p.analyst_required && !p.analyst_approved;
  const state = held || analyst ? 'hold' : d.action;
  const stale = staleReason();
  const remaining = Math.max(0, (p.hold_until || 0) - world.now);
  const title = state === 'hold' ? 'Payment on hold' : state === 'nudge' ? 'Check before paying' : 'Ready to pay';
  app.innerHTML = header('Review your payment', 'STEP 3 OF 3') + `<section class="card">${recipientHeader()}<div class="review-amount">${money(payment.amount_paise)}</div><p class="review-caption">From your demo account → ${escape(account(recipient).name)}</p><div class="verdict ${state}"><span class="eyebrow">MAYA PAYMENT CHECK</span><h2>${title}</h2>${d.reasons.length ? `<ul>${d.reasons.map(r => `<li>${escape(r)}</li>`).join('')}</ul>` : ''}${held ? `<div class="hold-time">${Math.floor(remaining / 60)}m ${remaining % 60}s</div><p class="micro">Simulated time · no automatic payment</p>` : ''}${analyst ? '<p><strong>Analyst approval required</strong></p>' : ''}</div>
    ${stale ? `<p class="muted bottom-space" role="status">${escape(stale)}</p>${button('rereview','Get a fresh review','primary full bottom-space')}` : held || analyst ? `<div class="bottom-space">${button('cancel','Cancel payment','primary full')}</div>` : `<div class="bottom-space">${state === 'nudge' || p.hold_until ? '<label class="checkbox-label"><input type="checkbox" id="confirm-warning"><span>I checked the warning and payment details.</span></label>' : ''}${button('continue','Continue')}</div>`}
    <div class="button-stack bottom-space">${button('inspect','View decision ↗','secondary full')}${button('edit','Edit payment details','link-button')}${!held && !analyst ? button('cancel','Cancel payment','link-button') : ''}</div></section>`;
}

let warningConfirmed = false;
function authorize() {
  app.innerHTML = header('Confirm payment', 'DEMO') + `<section class="card">${recipientHeader()}<div class="review-amount">${money(payment.amount_paise)}</div><p class="review-caption">Dummy transfer · MAYA Demo Bank ·· 2048</p><div class="bottom-space">${button('send','Confirm demo payment →')}</div>${button('review-back','Back to review','link-button full bottom-space')}</section>`;
}

function receipt() {
  const a = account(transfer.recipient);
  app.innerHTML = header('Payment details') + `<section class="card center"><div class="status-icon" aria-hidden="true">✓</div><h1 class="success-title">Payment completed.</h1><div class="review-amount">${money(transfer.amount_paise)}</div><p class="review-caption">Paid to ${escape(a.name)}</p><span class="badge">Completed · Demo</span><div class="receipt"><div class="receipt-row"><span>Paid to</span><strong>${escape(a.vpa)}</strong></div><div class="receipt-row"><span>Time · IST</span><strong>${clock(transfer.timestamp)}</strong></div><div class="receipt-row"><span>Your balance</span><strong>${money(account(0).balance_paise)}</strong></div><div class="receipt-row code"><span>Transfer ID</span><strong>${escape(transfer.id)}</strong></div><div id="ledger-proof" class="transfer-proof"></div></div><div class="button-stack">${button('home','Done')}${button('inspect','View decision ↗','secondary full')}${button('observer','Open recipient view ↗','link-button')}</div></section>`;

}

function inspect() {
  if (!world || observeToken) return;
  $('#world-meta').textContent = `Seed ${world.seed} · ${world.event_count} events · ${world.id}`;
  const relevant=payment ? events.filter(e=>e.payment_id===payment.id) : [];
  const evaluation=screen==='processing' ? relevant.filter(e=>e.evaluation_id).at(-1)?.evaluation_id : review?.id;
  const selected=relevant.filter(e=>!e.evaluation_id || e.evaluation_id===evaluation).slice(-14);
  $('#trace').innerHTML=selected.map(e=>`<li class="${e.status==='failed'?'trace-failed':''}">${escape(e.stage.replaceAll('_',' '))}${e.failed_stage?' · '+escape(e.failed_stage):''}<small>#${e.sequence}${e.duration_ms!==undefined?' · '+e.duration_ms.toFixed(2)+' ms':''}</small></li>`).join('') || '<li>No execution events</li>';
  if(!review) { $('#decision-inspector').innerHTML=''; $('#decision-inspector').dataset.review=''; return; }
  const f=review.feature_snapshot;
  const graphEvents=f.evidence.filter(e=>e.kind==='payment' && Math.max(e.event_at,e.available_at)<f.graph_cutoff);
  const pairs=[...new Map(graphEvents.map(e=>[`${e.sender}-${e.receiver}`,e])).values()];
  // Avoid rebuilding open details on every SSE heartbeat/notification.
  if ($('#decision-inspector').dataset.review!==review.id) {
    $('#decision-inspector').innerHTML=decisionExplorer(review,drawGraph(pairs,f),previousReview);
    if(transfer && transfer.review_id===review.id) {
      $('#decision-inspector').insertAdjacentHTML('afterbegin','<section class="panel"><h3>Ledger reconciliation</h3><div id="explorer-ledger">Loading…</div></section>');
      api(path(`ledger/${transfer.id}`)).then(rows=>{const el=$('#explorer-ledger'); if(el) el.textContent=rows.map(r=>`${r.account}: ${money(r.delta)}`).join(' / ')+` · net ${money(rows.reduce((sum,r)=>sum+r.delta,0))}`;}).catch(e=>notify(e.message,true));
    }
    $('#decision-inspector').dataset.review=review.id;
    $('#decision-inspector').querySelectorAll('details').forEach(d=>{
      const key=d.querySelector('summary')?.textContent.trim().split(' ')[0];
      if (key && f.values.hasOwnProperty(key)) d.id='feature-'+key;
    });
  }
}

function drawGraph(edges, snapshot) {
  const reports=new Set(snapshot.evidence.filter(e => e.kind==='report' && e.event_at<snapshot.graph_cutoff && e.available_at<snapshot.graph_cutoff).map(e => e.account));
  const focus=new Set([0,review.payment.recipient,...reports]);
  const nearby=edges.filter(e => focus.has(e.sender) || focus.has(e.receiver));
  const ids=[...new Set([...focus,...nearby.flatMap(e => [e.sender,e.receiver])])].slice(0,8);
  const points=new Map(ids.map((id,i) => { const a=2*Math.PI*i/ids.length-Math.PI/2; return [id,{x:170+118*Math.cos(a),y:155+112*Math.sin(a)}]; }));
  const lines=nearby.filter(e => points.has(e.sender) && points.has(e.receiver));
  return `<svg viewBox="0 0 340 315" role="img" aria-label="Generated payment graph with ${ids.length} accounts and ${lines.length} evidence-backed directed edges"><defs><marker id="edge-arrow" viewBox="0 0 10 10" refX="25" refY="5" markerWidth="5" markerHeight="5" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z" fill="#9ab4a4"/></marker></defs>${lines.map(e => {const s=points.get(e.sender),t=points.get(e.receiver); return `<line x1="${s.x}" y1="${s.y}" x2="${t.x}" y2="${t.y}" stroke="#b7c9be" stroke-width="1.5" marker-end="url(#edge-arrow)"><title>${escape(e.id)}</title></line>`;}).join('')}${ids.map(id => {const p=points.get(id);return `<g><circle cx="${p.x}" cy="${p.y}" r="20" fill="${id===0 ? '#193b34' : '#edf3ef'}" stroke="${reports.has(id) ? '#bb6e5c' : '#ccdcd1'}" stroke-width="2"/><text x="${p.x}" y="${p.y+4}" text-anchor="middle" font-size="10" fill="${id===0 ? '#fff' : '#365644'}">${escape(initials(account(id).name))}</text><text x="${p.x}" y="${p.y+35}" text-anchor="middle" font-size="9" fill="#677c6e">${escape(account(id).name.slice(0,18))}</text></g>`;}).join('')}</svg>`;
}

function connectStream() {
  stream?.close(); events = [];
  stream = new EventSource('/api/' + path('stream'));
  stream.onopen = () => { $('#stream-status').textContent = '● Connected'; $('#stream-status').className = 'connection live'; };
  stream.onerror = () => { $('#stream-status').textContent = 'Reconnecting…'; $('#stream-status').className = 'connection'; };
  stream.onmessage = async message => {
    const event = JSON.parse(message.data);
    if(event.world_id && event.world_id !== world.id) return;
    if (!events.some(e => e.sequence === event.sequence)) events.push(event);
    inspect();
    if (['settled','cancelled','simulator_advance','simulator_report','analyst_approve','analyst_cancel','contact_consent_changed'].includes(event.stage)) {
      try {
        world = await api(`worlds/${world.id}`);
        if (payment && ['review','authorize'].includes(screen)) render();
        else if (screen === 'home') home();
        inspect();
      } catch(e) { notify(e.message, true); }
    }
  };
}

async function newWorld() {
  const value = Number($('#seed').value);
  if (!Number.isInteger(value) || value < 0 || value > 4294967295) throw new Error('Enter a seed between 0 and 4294967295.');
  world = await api('worlds', {seed:value, preset:$('#preset').value});
  payment = review = transfer = null; recipient = world.default_recipient; screen = 'home';
  save(); connectStream(); render();
}

async function doReview() {
  screen = 'processing'; render();
  try {
    if (review) previousReview=review;
    review = await api(path(`intents/${payment.id}/review`), {});
    world = await api(`worlds/${world.id}`);
    payment = currentPayment(); recipient = payment.recipient;
    warningConfirmed = false; screen = 'review'; render();
  } catch(e) {
    screen = 'amount'; render(); throw e;
  }
}

async function perform(action) {
  if (!world) return;
  if (action === 'inspect') { $('#workspace').classList.add('inspecting'); $('#inspect-toggle').setAttribute('aria-expanded','true'); $('#inspector').scrollIntoView({behavior:'smooth', block:'start'}); return; }
  if (action === 'home') { world = await api(`worlds/${world.id}`); screen='home'; render(); return; }
  if (action === 'pay') { payment = review = null; query=''; screen='recipients'; render(); return; }
  if (action === 'edit') { payment = currentPayment(); screen='amount'; render(); return; }
  if (action === 'rereview') { await doReview(); return; }
  if (action === 'review-back') { screen='review'; render(); return; }
  if (action === 'continue') {
    const needsConfirmation = review.decision.action === 'nudge' || currentPayment().hold_until;
    warningConfirmed = Boolean($('#confirm-warning')?.checked);
    if (needsConfirmation && !warningConfirmed) throw new Error('Confirm that you reviewed the warning before continuing.');
    if (staleReason()) throw new Error(staleReason());
    screen='authorize'; render(); return;
  }
  if (action === 'send') {
    try {
      transfer = await api(path(`intents/${payment.id}/execute`), {review_id:review.id, confirmed:warningConfirmed, authorization:'DEMO'});
    } catch(e) {
      // A disconnected response can follow a committed transfer. Reconcile from server state.
      world = await api(`worlds/${world.id}`);
      transfer = world.transfers.find(t => t.payment_id === payment.id);
      if (!transfer) { screen='review'; render(); throw e; }
    }
    world = await api(`worlds/${world.id}`); screen='receipt'; render(); return;
  }
  if (action === 'cancel') { await api(path(`intents/${payment.id}/cancel`), {}); world=await api(`worlds/${world.id}`); screen='home'; render(); notify('Payment cancelled. No money moved.'); return; }
  if (action === 'replay') { await api(path(`reviews/${review.id}?recompute=true`)); notify('Original model and policy outcome reproduced with matching versions.'); return; }
  if (action === 'download') {
    const original = await api(path(`reviews/${review.id}/bundle`));
    const url = URL.createObjectURL(new Blob([JSON.stringify(original,null,2)], {type:'application/json'}));
    const link = document.createElement('a'); link.href=url; link.download=`maya-review-${review.id}.json`; link.click(); setTimeout(() => URL.revokeObjectURL(url),1000); return;
  }
  if (action === 'stale-test') {
    const current = currentPayment();
    const old = previousReview?.payment.id===payment.id ? previousReview : review;
    if (current.revision === old.payment.revision) throw new Error('Edit the payment and review it again first. This challenge never executes an unchanged intent.');
    try { await api(path(`intents/${payment.id}/execute`), {review_id:old.id, confirmed:true, authorization:'DEMO'}); }
    catch(e) { notify('Old review rejected by the backend: ' + e.message); return; }
    throw new Error('Unexpected acceptance. Check the server trace.');
  }
  if (action === 'counterfactual') { throw new Error('Use the controller console for counterfactuals.'); }
  if (action === 'observer') { const shared=await api(path('sharing'),{account:transfer?.recipient ?? payment?.recipient ?? world.default_recipient}); location.assign('/recipient#access=' + encodeURIComponent(shared.token)); return; }
}

async function guarded(task) {
  if (busy) return;
  busy=true;
  const buttons = [...document.querySelectorAll('#app button, #new-world')];
  buttons.forEach(b => b.disabled=true);
  try { await task(); }
  catch(e) { notify(e.message || 'Connection interrupted. Check the transfer status before retrying.', true); }
  finally { busy=false; document.querySelectorAll('#app button, #new-world').forEach(b => b.disabled=false); }
}

app.addEventListener('click', event => {
  const target = event.target.closest('button'); if (!target) return;
  if (target.dataset.recipient) guarded(async () => { recipient=Number(target.dataset.recipient); payment=null; review=null; screen='amount'; render(); });
  else if (target.dataset.transfer) guarded(async () => { transfer=world.transfers.find(t => t.id === target.dataset.transfer); payment=world.intents.find(p => p.id === transfer.payment_id); review=await api(path(`reviews/${transfer.review_id}`)); recipient=transfer.recipient; screen='receipt'; render(); });
  else if (target.dataset.resume) guarded(async () => { payment=world.intents.find(p => p.id === target.dataset.resume); recipient=payment.recipient; await doReview(); });
  else if (target.dataset.action) guarded(() => perform(target.dataset.action));
});
$('#decision-inspector').addEventListener('click', event => { const link=event.target.closest('[data-feature]'); if(link) { event.preventDefault(); const detail=document.getElementById('feature-'+link.dataset.feature); if(detail) {detail.open=true; detail.scrollIntoView({block:'center',behavior:'smooth'}); detail.querySelector('summary').focus();} } const b=event.target.closest('[data-action]'); if(b) guarded(() => perform(b.dataset.action)); });
app.addEventListener('input', event => { if(event.target.id === 'recipient-search') { query=event.target.value; recipientList(); } });
app.addEventListener('submit', event => {
  if (event.target.id !== 'payment-form') return;
  event.preventDefault();
  guarded(async () => {
    const raw=$('#amount').value.trim();
    if (!/^\d{1,7}(\.\d{1,2})?$/.test(raw)) throw new Error('Enter a positive amount with at most two decimal places.');
    const [whole,fraction=''] = raw.split('.');
    const paise=Number(whole)*100+Number(fraction.padEnd(2,'0'));
    const consent=$('#consent').checked;
    const payload={recipient, amount_paise:paise, text:consent ? $('#message').value : '', consent};
    const editing=payment && payment.state==='pending';
    payment=await api(path(editing ? `intents/${payment.id}` : 'intents'),payload,editing ? 'PUT' : 'POST');
    save(); await doReview();
  });
});
$('#inspect-toggle').addEventListener('click', () => { const on=$('#workspace').classList.toggle('inspecting'); $('#inspect-toggle').setAttribute('aria-expanded',String(on)); });
$('#seed').value=randomSeed();
$('#random-seed').addEventListener('click', () => { $('#seed').value=randomSeed(); });
$('#new-world').addEventListener('click', () => guarded(newWorld));
$('#observer-link').addEventListener('click', () => perform('observer'));

function renderObserver() {
  $('#inspect-toggle').hidden=true;
  const credits = world.transfers;
  app.innerHTML = `<div class="greeting"><div><span class="eyebrow">RECIPIENT VIEW</span><h1>Incoming payments</h1></div><span class="profile">↙</span></div><div class="read-only">Read-only · Demo</div><div class="card"><h2>Incoming dummy transfers</h2>${credits.length ? credits.map(t => `<div class="activity-row">${avatar(t.recipient)}<span class="activity-copy"><strong>${escape(account(t.recipient).name)}</strong><small>${clock(t.timestamp)} · ${escape(t.id.slice(0,10))}</small></span><span class="activity-amount observer-credit">+ ${money(t.amount_paise)}<small>Credited</small></span></div>`).join('') : '<p class="empty">No incoming payments</p>'}</div><p class="micro center">World seed ${world.seed} · checked at ${new Date().toLocaleTimeString('en-IN')}</p>`;
}

async function start() {
  try {
    if (observeToken) {
      const poll=async () => { try { world=await api('observer'); renderObserver(); } catch(e) { world=null; app.innerHTML='<section class="card"><h1>Recipient access unavailable</h1><p>The link expired or was revoked.</p></section>'; notify(e.message,true); return; } observerTimer=setTimeout(poll,2000); };
      await poll(); return;
    }
    const id=new URLSearchParams(location.search).get('world') || localStorage.getItem('maya-world');
    if (id) {
      try {
        world=await api(`worlds/${id}`);
        $('#seed').value=world.seed; $('#preset').value=world.preset;
        const saved=JSON.parse(sessionStorage.getItem('maya-payment') || '{}');
        if (saved.world===id && saved.payment) {
          payment=world.intents.find(p => p.id===saved.payment);
          if (payment) {
            recipient=payment.recipient;
            if (saved.review) review=await api(path(`reviews/${saved.review}`));
            transfer=world.transfers.find(t => t.payment_id===payment.id);
            screen=transfer ? 'receipt' : payment.state==='pending' && review ? 'review' : 'home';
          }
        }
      } catch { world=null; payment=review=transfer=null; }
    }
    if (!world) await newWorld();
    else { connectStream(); render(); }
  } catch(e) { app.innerHTML='<div class="card"><h1>Wallet unavailable</h1><p>Check that the local server and model artifacts are ready, then reload.</p></div>'; notify(e.message,true); }
}
window.addEventListener('pagehide', () => { stream?.close(); clearTimeout(observerTimer); });
start();

$('#revoke-observer').addEventListener('click', () => guarded(async () => {
  await api(path('sharing/revoke'), {}); world = await api(`worlds/${world.id}`); notify('Previous recipient link revoked.');
}));
$('#delete-world').addEventListener('click', () => guarded(async () => {
  if (!confirm('Delete this synthetic wallet, reviews and ledger? This cannot be undone.')) return;
  await api(`worlds/${world.id}`, {}, 'DELETE'); localStorage.removeItem('maya-world'); sessionStorage.removeItem('maya-payment');
  world = payment = review = transfer = null; await newWorld();
}));

app.addEventListener('change',event=>{
  if(event.target.id==='contact-consent') guarded(async()=>{await api(path('contact-consent'),{enabled:event.target.checked});world=await api(`worlds/${world.id}`); render();});
});
