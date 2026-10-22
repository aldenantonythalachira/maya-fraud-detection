const $ = selector => document.querySelector(selector);
const app = $('#app');
const escape = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const money = paise => new Intl.NumberFormat('en-IN', {style:'currency', currency:'INR', maximumFractionDigits:paise % 100 ? 2 : 0}).format(paise / 100);
const clock = epoch => new Date(epoch * 1000).toLocaleString('en-IN', {day:'numeric', month:'short', hour:'2-digit', minute:'2-digit', timeZone:'Asia/Kolkata'});
const randomSeed = () => crypto.getRandomValues(new Uint32Array(1))[0];
let world, payment, review, previousReview, transfer, stream, events = [], screen = 'home', busy = false, query = '', recipient = 1;
let noticeTimer, observerTimer;
const observeToken = new URLSearchParams(location.search).get('observe');

async function api(path, data, method = 'POST') {
  const response = await fetch('/api/' + path, data === undefined ? {} : {method, headers:{'Content-Type':'application/json'}, body:JSON.stringify(data)});
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
const recipientHeader = () => `<div class="recipient-header">${avatar(recipient)}<div><h2>${escape(account(recipient).name)}</h2><p>${escape(account(recipient).vpa)}</p><span class="verified">✓ Synthetic identity resolved</span></div></div>`;

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
  if (observeToken) return renderObserver();
  if (screen === 'home') home();
  if (screen === 'recipients') recipients();
  if (screen === 'amount') amount();
  if (screen === 'processing') app.innerHTML = header('Reviewing your payment') + `<div class="card loading-card" role="status"><span class="spinner"></span><h2>MAYA is checking the details.</h2><p>Reading the available history, evaluating the model, and saving your review.</p><p class="micro">Follow actual backend stages in “How it works”.</p></div>`;
  if (screen === 'review') reviewScreen();
  if (screen === 'authorize') authorize();
  if (screen === 'receipt') receipt();
  inspect();
  save();
}

function home() {
  const pending = world.intents.filter(p => p.state === 'pending');
  app.innerHTML = `<div class="greeting"><div><span class="eyebrow">YOUR EVERYDAY WALLET</span><h1>A little more peace of mind.</h1></div><span class="profile">Y</span></div>
    <section class="wallet-card" aria-label="Dummy wallet balance"><span class="eyebrow">AVAILABLE DEMO BALANCE</span><div class="balance">${money(account(0).balance_paise)}</div><div class="wallet-bottom"><span><span class="mini-shield">✓</span> MAYA Demo Bank ·· 2048</span><span>SIMULATED</span></div></section>
    <div class="pay-cta">${button('pay','<span aria-hidden="true">↗</span> Pay someone')}${button('observer','Receive ↙','secondary')}</div>
    <div class="section-title"><h2>People you can pay</h2>${button('pay','View all','link-button')}</div><div class="people">${[1,2,3,4].map(id => `<button class="person" data-recipient="${id}">${avatar(id)}<span>${escape(account(id).name.split(' ·')[0])}</span></button>`).join('')}</div>
    <div class="section-title"><h2>Recent activity</h2><span class="eyebrow">THIS WORLD</span></div><div class="activity">${world.transfers.length ? world.transfers.slice(0,8).map(t => `<button class="activity-row full" data-transfer="${t.id}">${avatar(t.recipient)}<span class="activity-copy"><strong>${escape(account(t.recipient).name)}</strong><small>${clock(t.timestamp)}</small></span><span class="activity-amount">− ${money(t.amount_paise)}<small>Completed</small></span></button>`).join('') : `<div class="empty">Your next payment starts here.<br>Send a dummy transfer to see the balances change.</div>`}</div>
    ${pending.length ? `<div class="section-title bottom-space"><h2>Saved payments</h2><span class="micro">Not sent</span></div><div class="activity">${pending.slice(0,5).map(p => `<button class="activity-row full" data-resume="${p.id}">${avatar(p.recipient)}<span class="activity-copy"><strong>${escape(account(p.recipient).name)}</strong><small>Pending · revision ${p.revision}</small></span><span class="activity-amount">${money(p.amount_paise)} →</span></button>`).join('')}</div>` : ''}
    <p class="quiet-note"><span class="mini-shield">✓</span><span>A moment of clarity before you pay. MAYA checks the journey and explains when something needs a second look.</span></p>`;
}

function recipients() {
  app.innerHTML = header('Who are you paying?', 'STEP 1 OF 3') + `<section class="card"><label for="recipient-search">Name or demo UPI ID</label><input class="field" id="recipient-search" placeholder="Search Amma, rent, traders…" autocomplete="off" value="${escape(query)}"><p class="search-count">Synthetic contacts only · no real UPI lookup</p><div id="recipient-list" class="selection-list"></div></section>`;
  recipientList();
}

function recipientList() {
  const matches = world.accounts.filter(a => a.id !== 0 && `${a.name} ${a.vpa}`.toLowerCase().includes(query.toLowerCase())).slice(0,20);
  $('#recipient-list').innerHTML = matches.map(a => `<button class="selection-item" data-recipient="${a.id}">${avatar(a.id)}<span><strong>${escape(a.name)}</strong><small>${escape(a.vpa)}</small></span><span class="chevron">→</span></button>`).join('') || '<p class="empty">No synthetic recipient found. Try a name from this world.</p>';
}

function amount() {
  const editing = payment && payment.state === 'pending';
  const paise = editing ? payment.amount_paise : world.default_amount_paise;
  app.innerHTML = header(editing ? 'Update your payment' : 'Enter an amount', 'STEP 2 OF 3') + `<form id="payment-form" class="card">${recipientHeader()}<p class="amount-label">You are sending</p><div class="amount-entry"><span>₹</span><input id="amount" name="amount" type="text" inputmode="decimal" autocomplete="off" aria-label="Amount in rupees" required value="${paise / 100}"></div><p class="available">Available dummy balance: ${money(account(0).balance_paise)}</p><details ${editing && payment.consent || world.default_message ? 'open' : ''}><summary>Add context for MAYA <span class="micro">· optional</span></summary><label for="message">A message you want MAYA to compare</label><textarea class="field" id="message" maxlength="2000" placeholder="For example: Approve to receive your refund">${escape(editing ? payment.text : world.default_message)}</textarea><label class="checkbox-label"><input type="checkbox" id="consent" ${editing && payment.consent ? 'checked' : ''}><span>Use and save this synthetic message locally for this review.</span></label><p class="micro">Narrow English grammar with abstention. No screenshot, PIN, call audio or contacts are collected.</p></details><div class="divider"></div><button class="primary full" type="submit">Review payment <span aria-hidden="true">→</span></button><p class="micro center">No money moves until you authorize a demo payment.</p></form>`;
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
  const title = state === 'hold' ? 'Let’s pause this payment.' : state === 'nudge' ? 'Take a moment to check.' : 'Your payment is ready.';
  app.innerHTML = header('Review your payment', 'STEP 3 OF 3') + `<section class="card">${recipientHeader()}<div class="review-amount">${money(payment.amount_paise)}</div><p class="review-caption">From your demo account → ${escape(account(recipient).name)}</p><div class="verdict ${state}"><span class="eyebrow">MAYA PAYMENT CHECK</span><h2>${title}</h2><p>${state === 'hold' ? 'No money has left your account. This is a reversible hold.' : state === 'nudge' ? 'The current model and policy ask for an extra check. Continue only after reviewing the recipient and amount.' : 'The current policy allows you to continue. This is not a guarantee that a recipient is safe.'}</p>${d.reasons.length ? `<ul>${d.reasons.map(r => `<li>${escape(r)}</li>`).join('')}</ul>` : ''}${held ? `<div class="hold-time">${Math.floor(remaining / 60)}m ${remaining % 60}s</div><p class="micro">Remaining on the paused simulation clock. Advance time in “How it works”. Expiry never sends money automatically.</p>` : ''}${analyst ? '<p><strong>Simulated analyst approval is also required for this revision.</strong></p>' : ''}</div>
    ${stale ? `<p class="muted bottom-space" role="status">${escape(stale)}</p>${button('rereview','Get a fresh review','primary full bottom-space')}` : held || analyst ? `<div class="bottom-space">${button('cancel','Cancel payment','primary full')}</div>` : `<div class="bottom-space">${state === 'nudge' || p.hold_until ? '<label class="checkbox-label"><input type="checkbox" id="confirm-warning"><span>I reviewed the warning, recipient and amount. Continue with this dummy payment.</span></label>' : ''}${button('continue','Continue to demo authorization')}</div>`}
    <div class="button-stack bottom-space">${button('inspect','See how MAYA decided ↗','secondary full')}${button('edit','Edit payment details','link-button')}${!held && !analyst ? button('cancel','Cancel payment','link-button') : ''}</div><p class="micro center">Reasons above are evidence templates. Model contributions are shown separately in the inspector.</p></section>`;
}

let warningConfirmed = false;
function authorize() {
  app.innerHTML = header('Demo authorization', 'NO REAL PIN REQUIRED') + `<section class="card">${recipientHeader()}<div class="review-amount">${money(payment.amount_paise)}</div><p class="review-caption">Dummy transfer · MAYA Demo Bank ·· 2048</p><div class="verdict"><h2>Authorize this demo payment</h2><p>This button confirms a simulated debit and credit. Never enter a real UPI PIN in this demo.</p></div><div class="bottom-space">${button('send','Authorize dummy payment →')}</div><p class="micro center">The backend rechecks your review, hold and balance before settling.</p>${button('review-back','Back to review','link-button full bottom-space')}</section>`;
}

function receipt() {
  const a = account(transfer.recipient);
  app.innerHTML = header('Payment details') + `<section class="card center"><div class="status-icon" aria-hidden="true">✓</div><h1 class="success-title">Payment completed.</h1><p class="muted">A dummy transfer. A real record of what happened.</p><div class="review-amount">${money(transfer.amount_paise)}</div><p class="review-caption">Paid to ${escape(a.name)}</p><span class="badge">✓ Debit and credit committed together</span><div class="receipt"><div class="receipt-row"><span>Paid to</span><strong>${escape(a.vpa)}</strong></div><div class="receipt-row"><span>Time · IST</span><strong>${clock(transfer.timestamp)}</strong></div><div class="receipt-row"><span>Your dummy balance</span><strong>${money(account(0).balance_paise)}</strong></div><div class="receipt-row"><span>Recipient dummy balance</span><strong>${money(a.balance_paise)}</strong></div><div class="receipt-row code"><span>Transfer ID</span><strong>${escape(transfer.id)}</strong></div><div id="ledger-proof" class="transfer-proof"></div></div><div class="button-stack">${button('home','Done')}${button('inspect','See the decision and ledger ↗','secondary full')}${button('observer','Open recipient view ↗','link-button')}</div></section>`;
  api(path(`ledger/${transfer.id}`)).then(rows => {
    if ($('#ledger-proof')) $('#ledger-proof').innerHTML = `<p class="micro">Ledger: ${rows.map(r => `${r.delta > 0 ? '+' : '−'}${money(Math.abs(r.delta))}`).join(' / ')} · net ${money(rows.reduce((s,r) => s + r.delta, 0))}</p>`;
  }).catch(e => notify(e.message, true));
}

function inspect() {
  if (!world || observeToken) return;
  $('#world-meta').textContent = `Seed ${world.seed} · ${world.event_count} events · revision ${world.revision} · ${clock(world.now)} IST`;
  const paymentEvents = payment ? events.filter(e => e.payment_id === payment.id) : events.slice(-8);
  const stages = {intent_validated:'Payment intent validated', history_loaded:'Available history loaded', features_computed:'18 features computed', model_scored:'XGBoost inference complete', uncertainty_computed:'Conformal set computed', policy_evaluated:'Independent-group policy evaluated', review_saved:'Immutable review saved', settled:'Debit and credit committed', cancelled:'Payment cancelled', review_failed:'Evaluation failed'};
  $('#trace').innerHTML = paymentEvents.length ? paymentEvents.slice(-12).map(e => `<li>${escape(stages[e.stage] || e.stage.replaceAll('_',' '))}<small>Event #${e.sequence}${e.latency_ms ? ` · ${e.latency_ms.toFixed(1)} ms review processing` : ''}</small></li>`).join('') : '<li>No payment stages yet. Each step appears after backend processing.</li>';
  const alerts = events.filter(e => e.stage === 'trusted_contact_alert');
  $('#contact-inbox').innerHTML = alerts.length ? alerts.map(e => `<p class="muted">${escape(e.message)}<br><span class="micro">Payment ${escape(e.payment_id.slice(0,8))} · synthetic inbox only</span></p>`).join('') : 'No held-payment alerts in this world. No real messages are sent.';
  if (!review) { $('#decision-inspector').innerHTML = ''; return; }
  const f = review.feature_snapshot;
  const contributions = [...review.model.contributions].sort((a,b) => Math.abs(b.value) - Math.abs(a.value));
  const graphEvents = f.evidence.filter(e => e.kind === 'payment' && e.event_at < f.graph_cutoff && e.available_at < f.graph_cutoff);
  const graphPairs = [...new Map(graphEvents.map(e => [`${e.sender}-${e.receiver}`,e])).values()];
  $('#decision-inspector').innerHTML = `<section class="panel"><div class="section-title"><h3>The model and the rule</h3><span class="small-tag">ACTUAL INFERENCE</span></div><div class="model-score">${(review.model.score * 100).toFixed(2)}%</div><p class="micro">Synthetic-model score · ${escape(review.model.uncertainty)} · ${review.latency_ms.toFixed(1)} ms review processing</p><div class="signal-groups">${Object.entries(review.groups).map(([k,v]) => `<span class="signal-group ${v ? 'active' : ''}">${escape(k)}: ${v ? 'present' : 'absent'}</span>`).join('')}</div><p class="muted bottom-space">Selected action: <strong>${escape(review.decision.action)}</strong>. A hold needs history + recipient, or one of those groups + context. Model certainty does not count as a group.</p><p class="micro">Smoke calibration coverage is below the 90% target. This demo does not establish real-world accuracy.</p><details><summary>Feature values, windows and lineage</summary><div class="table-wrap"><table class="data-table"><thead><tr><th>Feature</th><th>Value</th><th>Definition</th></tr></thead><tbody>${Object.entries(f.values).map(([k,v]) => `<tr><td>${escape(k)}</td><td>${v === null ? 'Missing' : Number(v.toFixed(5))}</td><td>${escape(f.lineage.windows[k.replace(/_(snd|rcv)$/,'')])}</td></tr>`).join('')}</tbody></table></div><p class="micro">Computed independently at payer and recipient endpoints. All event and availability times are strictly before evaluation.</p><pre>${escape(JSON.stringify(f.lineage,null,2))}</pre></details><details><summary>Tree SHAP · actual log-odds contributions</summary><table class="data-table"><thead><tr><th>Feature</th><th>Contribution</th></tr></thead><tbody>${contributions.map(c => `<tr><td>${escape(c.feature)}<br>${escape(c.label)}</td><td class="${c.value > 0 ? 'risk-up' : 'risk-down'}">${c.value > 0 ? '+' : ''}${c.value.toFixed(5)}</td></tr>`).join('')}</tbody></table><p class="micro">Positive increases the model score; negative decreases it. Attribution is not proof of fraud. Base margin: ${review.model.base_margin.toFixed(5)}.</p></details><details><summary>Evidence-backed payment graph</summary><p class="micro">${escape(f.graph_convention)}. Only saved eligible payment edges are listed. An edge does not prove fraud.</p><ul class="graph-list">${graphPairs.slice(-80).map(e => `<li><b>${escape(account(e.sender).name)}</b><span class="graph-arrow">→</span><b>${escape(account(e.receiver).name)}</b><br><span class="micro">${escape(e.id)} · ${clock(e.event_at)}</span></li>`).join('')}</ul></details><details><summary>Original events, claims and artifact versions</summary><pre>${escape(JSON.stringify(review,null,2))}</pre></details><div class="button-stack bottom-space">${button('replay','Recompute original snapshot','secondary')}${button('download','Download immutable review','secondary')}${button('stale-test','Try old review after an edit','secondary')}${button('approve','Record simulated analyst approval','secondary')}</div></section>`;
  const graphPanel=document.createElement('section'); graphPanel.className='panel';
  graphPanel.innerHTML=`<h3>Follow the money</h3>${drawGraph(graphPairs, f)}<p class="micro">Subset of saved payment edges around this intent. Arrow direction follows actual dummy payments; red outlines mark synthetic reported accounts. Full eligible edges remain in the evidence table above.</p><div class="button-stack bottom-space">${button('counterfactual','Delay reports · evaluate a separate payment','secondary')}</div><p class="micro">This changes report availability for a new evaluation. The original review and any existing hold stay intact.</p>`;
  $('#decision-inspector').append(graphPanel);
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
    if (!events.some(e => e.sequence === event.sequence)) events.push(event);
    inspect();
    if (['settled','cancelled','simulator_advance','simulator_report','simulator_approve'].includes(event.stage)) {
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
    const original = await api(path(`reviews/${review.id}`));
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
  if (action === 'approve') { await api(path('control'), {operation:'approve', payment_id:payment?.id, review_id:review?.id}); world=await api(`worlds/${world.id}`); render(); notify('Simulated approval saved for the current held revision. The timer still applies.'); return; }
  if (action === 'counterfactual') {
    const original=review;
    world=await api(path('control'),{operation:'delay_reports'});
    payment=await api(path('intents'),{recipient:original.payment.recipient,amount_paise:original.payment.amount_paise,text:original.payment.text,consent:original.payment.consent});
    review=await api(path(`intents/${payment.id}/review`),{parent:original.id});
    previousReview=original; recipient=payment.recipient; world=await api(`worlds/${world.id}`); screen='review'; render();
    notify(`Separate evaluation: ${original.decision.action} → ${review.decision.action}. Original record and original intent are preserved.`); return;
  }
  if (action === 'observer') { location.assign('/?observe=' + encodeURIComponent(world.observer)); return; }
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
$('#decision-inspector').addEventListener('click', event => { const b=event.target.closest('[data-action]'); if(b) guarded(() => perform(b.dataset.action)); });
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
$('#advance').addEventListener('click', () => guarded(async () => { world=await api(path('control'),{operation:'advance',seconds:3600}); render(); notify('Simulation advanced one hour. Obtain a fresh review before sending.'); }));
$('#add-report').addEventListener('click', () => guarded(async () => { world=await api(path('control'),{operation:'report', account:payment?.recipient ?? world.default_recipient}); render(); notify('Synthetic report saved. Prior-day graph semantics apply; review again.'); }));
$('#observer-link').addEventListener('click', () => perform('observer'));

function renderObserver() {
  $('#inspect-toggle').hidden=true;
  const credits = world.transfers;
  app.innerHTML = `<div class="greeting"><div><span class="eyebrow">RECIPIENT VIEW</span><h1>The other side of the payment.</h1></div><span class="profile">↙</span></div><div class="read-only">Read-only observer · dummy data · refreshes from the backend every two seconds</div><div class="card"><h2>Incoming dummy transfers</h2>${credits.length ? credits.map(t => `<div class="activity-row">${avatar(t.recipient)}<span class="activity-copy"><strong>${escape(account(t.recipient).name)}</strong><small>${clock(t.timestamp)} · ${escape(t.id.slice(0,10))}</small></span><span class="activity-amount observer-credit">+ ${money(t.amount_paise)}<small>Credited</small></span></div>`).join('') : '<p class="empty">Waiting for a completed payment.<br>Send a dummy transfer from the payer view.</p>'}<div class="divider"></div><p class="micro">No authorization is needed to receive this credit. Every transfer shares the payer’s backend record.</p></div><p class="micro center">World seed ${world.seed} · checked at ${new Date().toLocaleTimeString('en-IN')}</p>`;
}

async function start() {
  try {
    if (observeToken) {
      const poll=async () => { try { world=await api(`observe/${encodeURIComponent(observeToken)}`); renderObserver(); } catch(e) { notify(e.message,true); } observerTimer=setTimeout(poll,2000); };
      await poll(); return;
    }
    const id=localStorage.getItem('maya-world');
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
