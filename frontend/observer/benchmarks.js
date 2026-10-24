const esc = (s) =>
  String(s ?? "").replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        c
      ],
  );
const pct = (n) => (100 * n).toFixed(1) + "%";
(async () => {
  const r = await fetch("/v1/observe/benchmarks");
  if (!r.ok)
    throw Error("Pair this browser with the customer as a judge first.");
  const b = await r.json();
  let html = "";
  const p = b.reports.paysim;
  if (p) {
    html += `<section class="benchmark"><span class="pill">PUBLIC SYNTHETIC MOBILE-MONEY DATA</span><h2>PaySim · ${Number(p.actual_rows).toLocaleString()} rows</h2><p>Held-out test: ${p.splits.test.rows.toLocaleString()} transactions, ${p.splits.test.positives} fraud labels.</p><table class="feature-table"><thead><tr><th>Model</th><th>PR-AUC</th><th>Recall</th><th>Benign intervention</th></tr></thead><tbody>${Object.entries(
      p.candidates,
    )
      .map(
        ([n, m]) =>
          `<tr><td>${esc(n)}</td><td>${m.pr_auc.toFixed(3)}</td><td>${pct(m.recall)}</td><td>${pct(m.benign_intervention_rate)}</td></tr>`,
      )
      .join(
        "",
      )}</tbody></table><p class="muted">Chronological prefix; complete hours. No UPI coercion labels. MLP remains a challenger.</p></section>`;
  }
  const l = b.reports.load;
  if (l) {
    html += `<section class="benchmark"><h2>Complete review-service load</h2><p>${esc(l.workload)}</p><table class="feature-table"><thead><tr><th>Offered/s</th><th>Success/s</th><th>p95</th><th>Errors</th></tr></thead><tbody>${l.runs.map((x) => `<tr><td>${x.offered_rps}</td><td>${x.achieved_success_rps.toFixed(1)}</td><td>${x.p95_ms.toFixed(1)} ms</td><td>${Object.values(x.errors).reduce((a, b) => a + b, 0)}</td></tr>`).join("")}</tbody></table><p class="muted">${l.seconds_per_level}s per level on one local machine. Overload rejections are included. Not national-UPI capacity.</p></section>`;
  }
  const v = b.reports.validation;
  if (v) {
    html += `<section class="benchmark"><h2>Authored event-level kit</h2><table class="feature-table"><thead><tr><th>Case</th><th>Count</th><th>Release</th><th>Warn</th><th>Hold</th></tr></thead><tbody>${Object.entries(
      v.groups,
    )
      .map(
        ([n, g]) =>
          `<tr><td>${esc(n)}</td><td>${g.n}</td><td>${g.release}</td><td>${g.nudge}</td><td>${g.hold}</td></tr>`,
      )
      .join(
        "",
      )}</tbody></table><p class="muted">Small authored scenarios; not an unbiased fraud accuracy estimate. A fresh recipient cannot be held without independent evidence.</p></section>`;
  }
  document.querySelector("#results").innerHTML =
    html || "<p>No recorded reports are available in this deployment.</p>";
})().catch((e) => {
  document.querySelector("#results").textContent = e.message;
});
