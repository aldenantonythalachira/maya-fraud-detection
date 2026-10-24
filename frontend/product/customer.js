const $ = (s) => document.querySelector(s);
const esc = (s) =>
  String(s ?? "").replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        c
      ],
  );
let lang = localStorage.getItem("maya-v4-language") || "en",
  world = null,
  payment = null,
  review = null,
  receipt = null,
  camera = null;
const words = {
  en: {
    home: "Home",
    activity: "Activity",
    settings: "Settings",
    title: "A little clarity.\nBefore you pay.",
    scan: "Scan a QR",
    check: "Check a message",
    sandbox: "Try a payment",
    demo: "Sandbox · Dummy money",
    start: "Start a fresh session",
    review: "Review payment",
    recipient: "Recipient",
    amount: "Amount",
    context: "Optional payment context",
    none: "No shared context",
    refund: "Message promises a refund",
    withdrawal: "Payment unlocks a withdrawal",
    rent: "Rent payment",
    merchant_refund: "Refund to a customer",
    pay: "Check payment",
    continue: "Send dummy payment",
    confirm: "I understand. Send dummy payment",
    cancel: "Cancel payment",
    edit: "Edit details",
    back: "Back",
    sent: "Dummy payment completed",
    checking: "Checking your payment",
    held: "Payment held",
    warning: "Check before you continue",
    ready: "Ready to continue",
    pair: "Connect judge device",
    pairRecipient: "Connect recipient device",
    revoke: "Revoke device access",
    new: "New payment",
    help: "Create evidence draft",
    private: "This message stays on this device.",
    paste: "Message or UPI link",
    analyse: "Check intent",
    limited: "Limited information",
    retry: "Try again",
    delete: "Delete this session",
    consent: "Data & access",
    empty: "No completed payments yet.",
    camera: "Open camera",
    upload: "Upload QR image",
    cameraUnsupported:
      "QR reading is unavailable in this browser. Paste the UPI link instead.",
    copied: "Pairing code copied",
    checkTitle: "Understand this payment",
    invalid: "Use a valid upi://pay link with recipient and a positive amount.",
    noRaw: "Only derived intent is sent. Raw messages are not retained.",
    withdrawalRisk: "A payment cannot verify a promised investment withdrawal.",
    mismatch: "This sends money. The message describes incoming money.",
    limitedReason:
      "Bank history and verified recipient information are unavailable for this check.",
    error: "Unable to complete this action. No payment has been confirmed.",
    save: "Download draft",
    draft: "Evidence draft · Not submitted",
    status: "Status",
    refresh: "Refresh",
    restricted: "Payment checks do not prove the recipient is legitimate.",
  },
  hi: {
    home: "होम",
    activity: "गतिविधि",
    settings: "सेटिंग",
    title: "भुगतान से पहले\nस्पष्ट जानकारी।",
    scan: "QR स्कैन करें",
    check: "संदेश जाँचें",
    sandbox: "भुगतान आज़माएँ",
    demo: "सैंडबॉक्स · नकली पैसे",
    start: "नया सत्र शुरू करें",
    review: "भुगतान की जाँच",
    recipient: "प्राप्तकर्ता",
    amount: "राशि",
    context: "भुगतान का संदर्भ",
    none: "कोई संदर्भ नहीं",
    refund: "संदेश में रिफंड का वादा",
    withdrawal: "निकासी खोलने के लिए भुगतान",
    rent: "किराया",
    merchant_refund: "ग्राहक को रिफंड",
    pay: "भुगतान जाँचें",
    continue: "नकली भुगतान भेजें",
    confirm: "समझ गया। नकली भुगतान भेजें",
    cancel: "भुगतान रद्द करें",
    edit: "विवरण बदलें",
    back: "वापस",
    sent: "नकली भुगतान पूरा हुआ",
    checking: "भुगतान की जाँच जारी है",
    held: "भुगतान रोका गया",
    warning: "आगे बढ़ने से पहले जाँचें",
    ready: "आगे बढ़ सकते हैं",
    pair: "जज का डिवाइस जोड़ें",
    pairRecipient: "प्राप्तकर्ता का डिवाइस जोड़ें",
    revoke: "डिवाइस की पहुँच हटाएँ",
    new: "नया भुगतान",
    help: "साक्ष्य का मसौदा बनाएँ",
    private: "यह संदेश इसी डिवाइस पर रहता है।",
    paste: "संदेश या UPI लिंक",
    analyse: "इरादा जाँचें",
    limited: "सीमित जानकारी",
    retry: "फिर कोशिश करें",
    delete: "यह सत्र हटाएँ",
    consent: "डेटा और पहुँच",
    empty: "अभी कोई भुगतान पूरा नहीं हुआ।",
    camera: "कैमरा खोलें",
    upload: "QR चित्र अपलोड करें",
    cameraUnsupported:
      "इस ब्राउज़र में QR पढ़ना उपलब्ध नहीं है। UPI लिंक पेस्ट करें।",
    copied: "कोड कॉपी हो गया",
    checkTitle: "इस भुगतान को समझें",
    invalid: "प्राप्तकर्ता और सही राशि वाला upi://pay लिंक डालें।",
    noRaw: "केवल निकाला गया इरादा भेजा जाता है। संदेश सहेजा नहीं जाता।",
    withdrawalRisk: "भुगतान से निवेश की निकासी की पुष्टि नहीं होती।",
    mismatch: "इससे पैसे भेजे जाएँगे। संदेश में पैसे मिलने की बात है।",
    limitedReason:
      "बैंक का इतिहास और प्राप्तकर्ता की सत्यापित जानकारी उपलब्ध नहीं है।",
    error: "यह काम पूरा नहीं हुआ। भुगतान की पुष्टि नहीं हुई है।",
    save: "मसौदा डाउनलोड करें",
    draft: "साक्ष्य का मसौदा · भेजा नहीं गया",
    status: "स्थिति",
    refresh: "ताज़ा करें",
    restricted: "जाँच से प्राप्तकर्ता के सही होने का प्रमाण नहीं मिलता।",
  },
};
const t = (k) => words[lang][k] || words.en[k] || k;
const money = (p) =>
  new Intl.NumberFormat(lang === "hi" ? "hi-IN" : "en-IN", {
    style: "currency",
    currency: "INR",
  }).format(p / 100);
const button = (id, label, cls = "full") =>
  `<button id="${id}" class="${cls}" type="button">${esc(t(label))}</button>`;
function announce(s) {
  $("#announcement").textContent = s;
}
function show(html) {
  stopCamera();
  $("#main").innerHTML = html;
  $("#main").focus({ preventScroll: true });
  document.documentElement.lang = lang;
}
function error(e) {
  announce(e.message);
  const box = document.createElement("p");
  box.className = "error";
  box.setAttribute("role", "alert");
  box.textContent = e.message || t("error");
  $("#main").prepend(box);
}
async function api(path, body, method) {
  const r = await fetch(path, {
    method: method || (body === undefined ? "GET" : "POST"),
    headers: {
      "Content-Type": "application/json",
      "Idempotency-Key": crypto.randomUUID(),
    },
    body: body === undefined ? undefined : JSON.stringify(body),
    signal: AbortSignal.timeout(20000),
  });
  const data = await r.json();
  if (!r.ok) {
    const e = new Error(data.detail || t("error"));
    e.status = r.status;
    throw e;
  }
  return data;
}
const base = () => `/v1/sandbox/worlds/${world.id}`;
async function reloadWorld() {
  if (world) world = await api(base());
}
function home() {
  show(
    `<section class="hero"><p class="eyebrow">PAYMENT SAFETY</p><h1>${esc(t("title")).replace("\n", "<br>")}</h1></section><div class="tiles"><button id="scan" class="tile"><span class="icon" aria-hidden="true">▦</span>${esc(t("scan"))}</button><button id="check" class="tile"><span class="icon" aria-hidden="true">↗</span>${esc(t("check"))}</button></div><section class="card soft"><span class="pill sandbox">${esc(t("demo"))}</span><h2>${esc(t("sandbox"))}</h2>${world ? `<p class="muted">${esc(money(world.accounts[0].balance_paise))}</p>` : ""}${button("sandbox", "sandbox")}</section>`,
  );
  $("#scan").onclick = () => companion(true);
  $("#check").onclick = () => companion(false);
  $("#sandbox").onclick = async () => {
    try {
      if (!world) {
        world = await api("/v1/sandbox/worlds", {});
        localStorage.setItem("maya-v4-world", world.id);
      }
      edit();
    } catch (e) {
      error(e);
    }
  };
}
function edit() {
  receipt = null;
  show(
    `<button id="back" class="quiet">← ${esc(t("back"))}</button><section class="section"><span class="pill sandbox">${esc(t("demo"))}</span><h1>${esc(t("review"))}</h1><form id="payment-form"><label for="recipient">${esc(t("recipient"))}</label><select id="recipient">${world.accounts
      .filter((a) => a.id > 0)
      .slice(0, 12)
      .map(
        (a) =>
          `<option value="${a.id}" ${a.id === (payment?.recipient ?? world.default_recipient) ? "selected" : ""}>${esc(a.name)} · ${esc(a.vpa)}</option>`,
      )
      .join(
        "",
      )}</select><label for="amount">${esc(t("amount"))} · INR</label><input id="amount" class="money" type="text" inputmode="decimal" value="${((payment?.amount_paise ?? world.default_amount_paise) / 100).toFixed(2)}" required autocomplete="off"><label for="context">${esc(t("context"))}</label><select id="context">${["none", "refund", "withdrawal", "rent", "merchant_refund"].map((k) => `<option value="${k}">${esc(t(k))}</option>`).join("")}</select><div class="section"><button class="full" type="submit">${esc(t("pay"))}</button></div></form><div class="row">${button("pair", "pair", "quiet")}${button("recipient-pair", "pairRecipient", "quiet")}</div></section>`,
  );
  $("#back").onclick = home;
  $("#pair").onclick = () => pair("judge");
  $("#recipient-pair").onclick = () => pair("recipient");
  $("#payment-form").onsubmit = async (e) => {
    e.preventDefault();
    const value = $("#amount").value.trim();
    if (!/^\d{1,7}(\.\d{1,2})?$/.test(value) || Number(value) <= 0)
      return error(new Error(t("invalid")));
    const body = {
      recipient: Number($("#recipient").value),
      amount_paise: Math.round(Number(value) * 100),
      context: $("#context").value,
    };
    const old = payment;
    show(
      `<div class="empty"><div class="spinner"></div><h2>${esc(t("checking"))}</h2></div>`,
    );
    try {
      payment = await api(
        base() +
          "/intents" +
          (old && old.state === "pending" ? "/" + old.id : ""),
        body,
        old && old.state === "pending" ? "PUT" : "POST",
      );
      review = await api(base() + `/intents/${payment.id}/review`, {});
      outcome();
    } catch (e) {
      payment = old;
      edit();
      error(e);
    }
  };
}
function outcome() {
  const action = review.decision.action;
  const label =
    action === "hold" ? "held" : action === "nudge" ? "warning" : "ready";
  const reasons = review.decision.reasons.slice(0, 2);
  const localReason = (s) =>
    lang === "hi"
      ? s.includes("message says")
        ? t("mismatch")
        : s.includes("withdrawal")
          ? t("withdrawalRisk")
          : s.includes("reported")
            ? "पिछले दिन का भुगतान मार्ग रिपोर्ट किए खाते से जुड़ा है।"
            : s.includes("history")
              ? "यह भुगतान उपलब्ध इतिहास से अलग है।"
              : s.includes("uncertain")
                ? "मॉडल निश्चित नहीं है। आगे बढ़ने से पहले प्राप्तकर्ता और राशि जाँचें।"
                : s
      : s;
  show(
    `<span class="pill sandbox">${esc(t("demo"))}</span><div class="result-icon ${action}" aria-hidden="true">${action === "release" ? "✓" : action === "hold" ? "‖" : "!"}</div><h1>${esc(t(label))}</h1><p class="amount">${esc(money(payment.amount_paise))}</p><p>${esc(world.accounts.find((a) => a.id === payment.recipient)?.name)}</p><ul class="reasons">${reasons.map((s) => `<li>${esc(localReason(s))}</li>`).join("")}</ul><div class="stack">${action !== "hold" ? button("send", action === "nudge" ? "confirm" : "continue") : button("draft", "help", "quiet")}${button("edit", "edit", "quiet")}${button("cancel", "cancel", "danger")}</div>`,
  );
  announce(t(label));
  if ($("#send"))
    $("#send").onclick = async () => {
      const b = $("#send");
      b.disabled = true;
      try {
        receipt = await api(base() + `/intents/${payment.id}/execute`, {
          review_id: review.id,
          confirmed: action === "nudge",
          authorization: "DEMO",
        });
        payment = null;
        await reloadWorld();
        showReceipt();
      } catch (e) {
        b.disabled = false;
        error(e);
      }
    };
  if ($("#draft")) $("#draft").onclick = draft;
  $("#edit").onclick = edit;
  $("#cancel").onclick = async () => {
    try {
      await api(base() + `/intents/${payment.id}/cancel`, {});
      payment = null;
      home();
    } catch (e) {
      error(e);
    }
  };
}
function showReceipt() {
  show(
    `<span class="pill sandbox">${esc(t("demo"))}</span><div class="result-icon release" aria-hidden="true">✓</div><h1>${esc(t("sent"))}</h1><p class="amount">${esc(money(receipt.amount_paise))}</p><p>${esc(world.accounts.find((a) => a.id === receipt.recipient)?.name)}</p><div class="card"><p class="muted">${esc(t("status"))}: ${esc(receipt.state)}</p><p class="muted number">${esc(receipt.id)}</p></div>${button("new", "new")}`,
  );
  announce(t("sent"));
  $("#new").onclick = edit;
}
async function pair(role) {
  try {
    const grant = await api(base() + "/pair", {
      role,
      account: Number($("#recipient")?.value || world.default_recipient),
    });
    $("#pair-code").textContent = grant.code;
    $("#pair-help").textContent = `${location.origin}${grant.url} · 5 min`;
    $("#pair-dialog").showModal();
    $("#copy-code").onclick = () =>
      navigator.clipboard
        .writeText(grant.code)
        .then(() => announce(t("copied")))
        .catch(error);
  } catch (e) {
    error(e);
  }
}
$("#close-dialog").onclick = () => $("#pair-dialog").close();
async function draft() {
  try {
    const d = await api(base() + "/cases", { review_id: review.id });
    const blob = new Blob([JSON.stringify(d, null, 2)], {
      type: "application/json",
    });
    const u = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = u;
    a.download = `maya-case-${d.id}.json`;
    a.click();
    URL.revokeObjectURL(u);
    announce(t("draft"));
  } catch (e) {
    error(e);
  }
}
async function activity() {
  try {
    await reloadWorld();
    show(
      `<h1>${esc(t("activity"))}</h1>${world?.transfers.length ? world.transfers.map((r) => `<div class="activity-item row"><div><p>${esc(world.accounts.find((a) => a.id === r.recipient)?.name)}</p><small>${esc(r.state)} · ${esc(r.id.slice(0, 8))}</small></div><strong>${esc(money(r.amount_paise))}</strong></div>`).join("") : `<p class="empty">${esc(t("empty"))}</p>`}${button("refresh", "refresh", "quiet")}`,
    );
    $("#refresh").onclick = activity;
  } catch (e) {
    error(e);
  }
}
function settings() {
  show(
    `<h1>${esc(t("settings"))}</h1><div class="card"><h2>${esc(t("consent"))}</h2><p>${esc(t("noRaw"))}</p><p class="muted">${esc(t("restricted"))}</p></div><div class="stack">${button("revoke", "revoke", "quiet")}${button("delete", "delete", "danger")}${button("fresh", "start", "quiet")}</div>`,
  );
  $("#revoke").onclick = async () => {
    try {
      if (world) await api(base() + "/revoke", {});
      announce(t("revoke"));
    } catch (e) {
      error(e);
    }
  };
  $("#delete").onclick = async () => {
    try {
      if (world) await api(base(), undefined, "DELETE");
      world = null;
      payment = null;
      localStorage.removeItem("maya-v4-world");
      home();
    } catch (e) {
      error(e);
    }
  };
  $("#fresh").onclick = async () => {
    try {
      world = await api("/v1/sandbox/worlds", {});
      payment = null;
      localStorage.setItem("maya-v4-world", world.id);
      edit();
    } catch (e) {
      error(e);
    }
  };
}
function stopCamera() {
  camera?.getTracks().forEach((t) => t.stop());
  camera = null;
}
function parseUPI(s) {
  const u = new URL(s);
  if (
    u.protocol !== "upi:" ||
    u.hostname !== "pay" ||
    (u.pathname && u.pathname !== "/")
  )
    throw new Error(t("invalid"));
  for (const k of ["pa", "am", "pn", "cu"])
    if (u.searchParams.getAll(k).length > 1) throw new Error(t("invalid"));
  const pa = u.searchParams.get("pa") || "",
    am = u.searchParams.get("am") || "";
  if (
    !/^[\w.\-]{1,128}@[\w.\-]{1,64}$/.test(pa) ||
    !/^\d{1,7}(\.\d{1,2})?$/.test(am) ||
    Number(am) <= 0 ||
    !["INR", null].includes(u.searchParams.get("cu"))
  )
    throw new Error(t("invalid"));
  return { recipient: pa, amount: Math.round(Number(am) * 100) };
}
function companion(scan) {
  show(
    `<button id="back" class="quiet">← ${esc(t("back"))}</button><section class="section"><h1>${esc(t("checkTitle"))}</h1><label for="message">${esc(t("paste"))}</label><textarea id="message" maxlength="2000"></textarea><p class="muted">${esc(t("private"))}</p><div class="stack">${button("analyse", "analyse")}${scan ? button("camera", "camera", "quiet") + `<label for="image">${esc(t("upload"))}</label><input type="file" id="image" accept="image/*"><video id="camera-view" muted playsinline hidden></video>` : ""}</div><div id="check-result" class="section" aria-live="polite"></div></section>`,
  );
  $("#back").onclick = home;
  $("#analyse").onclick = async () => {
    const raw = $("#message").value.trim();
    if (!raw) return;
    let parsed = null;
    if (raw.toLowerCase().startsWith("upi:")) {
      try {
        parsed = parseUPI(raw);
      } catch (e) {
        return error(e);
      }
    }
    const lower = raw.toLowerCase();
    const body = {
      direction: /^approve to receive (?:a |your )?refund[.!]?$/.test(lower)
        ? "incoming"
        : "unknown",
      purpose:
        /^pay (?:₹|rs\.?\s*)?[\d,]+ to release your investment withdrawal[.!]?$/.test(
          lower,
        )
          ? "withdrawal"
          : "unknown",
      operation: "transfer",
    };
    try {
      const r = await api("/v1/checks", body);
      const reason =
        r.action === "nudge"
          ? body.direction === "incoming"
            ? t("mismatch")
            : t("withdrawalRisk")
          : t("limitedReason");
      $("#check-result").innerHTML =
        `<div class="card"><span class="pill">${esc(t("limited"))}</span>${parsed ? `<h2>${esc(money(parsed.amount))}</h2><p>${esc(parsed.recipient)}</p>` : ""}<p>${esc(reason)}</p><small>${esc(t("restricted"))}</small></div>`;
      await api("/v1/checks/" + r.id, undefined, "DELETE");
    } catch (e) {
      error(e);
    }
  };
  if (scan) {
    $("#image").onchange = async (e) => {
      try {
        if (!("BarcodeDetector" in window))
          throw new Error(t("cameraUnsupported"));
        const bitmap = await createImageBitmap(e.target.files[0]);
        let codes;
        try {
          codes = await new BarcodeDetector({ formats: ["qr_code"] }).detect(
            bitmap,
          );
        } finally {
          bitmap.close();
        }
        if (!codes.length) throw new Error(t("invalid"));
        $("#message").value = codes[0].rawValue;
        $("#analyse").click();
      } catch (e) {
        error(e);
      }
    };
    $("#camera").onclick = async () => {
      try {
        if (!("BarcodeDetector" in window))
          throw new Error(t("cameraUnsupported"));
        camera = await navigator.mediaDevices.getUserMedia({
          video: { facingMode: "environment" },
          audio: false,
        });
        const v = $("#camera-view");
        v.srcObject = camera;
        v.hidden = false;
        await v.play();
        const detector = new BarcodeDetector({ formats: ["qr_code"] });
        const tick = async () => {
          if (!camera || !$("#camera-view")) return;
          try {
            const codes = await detector.detect(v);
            if (codes.length) {
              $("#message").value = codes[0].rawValue;
              stopCamera();
              v.hidden = true;
              $("#analyse").click();
              return;
            }
          } catch (e) {
            stopCamera();
            return error(e);
          }
          requestAnimationFrame(tick);
        };
        tick();
      } catch (e) {
        stopCamera();
        error(e);
      }
    };
  }
}
document.querySelectorAll("[data-nav]").forEach(
  (b) =>
    (b.onclick = () => {
      document
        .querySelectorAll("[data-nav]")
        .forEach((x) => x.removeAttribute("aria-current"));
      b.setAttribute("aria-current", "page");
      ({ home, activity, settings })[b.dataset.nav]();
    }),
);
$("#language").onclick = () => {
  lang = lang === "en" ? "hi" : "en";
  localStorage.setItem("maya-v4-language", lang);
  $("#language").textContent = lang === "en" ? "हिंदी" : "English";
  document
    .querySelectorAll("[data-nav]")
    .forEach((b) => (b.textContent = t(b.dataset.nav)));
  home();
};
window.addEventListener("pagehide", stopCamera);
if ("serviceWorker" in navigator)
  navigator.serviceWorker.register("/app/sw.js").catch(() => {});
(async () => {
  const wid = localStorage.getItem("maya-v4-world");
  if (wid) {
    try {
      world = await api("/v1/sandbox/worlds/" + wid);
    } catch (e) {
      if (e.status === 404 || e.status === 409)
        localStorage.removeItem("maya-v4-world");
    }
  }
  home();
})();
