const $ = s => document.querySelector(s), $$ = s => [...document.querySelectorAll(s)];
// Label table cells for the stacked mobile layout
$$("table.stack").forEach(t => { const h = [...t.querySelectorAll("th")].map(x => x.textContent); t.querySelectorAll("tr").forEach(r => [...r.children].forEach((c, i) => { if (c.tagName === "TD") c.dataset.label = h[i] || ""; })); });
// Tabs
$$(".tab").forEach(t => t.onclick = () => {
  $$(".tab").forEach(x => x.classList.toggle("active", x === t));
  $$(".panel").forEach(p => p.hidden = p.id !== t.dataset.tab);
});
$$("[data-close]").forEach(b => b.onclick = () => b.closest("dialog").close());

// Add / edit event dialog
const dlg = $("#eventDlg"), f = dlg.querySelector("form");
$("#addEvent").onclick = () => { f.reset(); f.id.value = ""; $("#dlgTitle").textContent = "Add event"; $("#keepNote").hidden = true; dlg.showModal(); };
$$(".edit").forEach(b => b.onclick = () => {
  const e = JSON.parse(b.dataset.event); f.reset();
  f.id.value = e.id;
  ["name", "event_date", "start_time", "end_time", "location", "description", "status"].forEach(k => f[k].value = e[k] || "");
  $("#dlgTitle").textContent = "Edit event"; $("#keepNote").hidden = false; dlg.showModal();
});

// Registration filter + CSV link
$("#regFilter").onchange = e => {
  const id = e.target.value;
  $$("#t-regs tr[data-event]").forEach(r => r.hidden = id && r.dataset.event !== id);
  $("#csv").href = $("#csv").dataset.base + (id ? "?event_id=" + id : "");
};

// Check-in
const result = $("#result"), REGS = window.REGS || [], sugg = $("#sugg"), mRoll = $("#mRoll"), mEvent = $("#mEvent");
// Roll number suggestions for manual check-in (matches any part of roll number or name)
function renderSugg() {
  const q = mRoll.value.trim().toLowerCase(), ev = mEvent.value;
  const list = REGS.filter(r => (!ev || String(r.event_id) === ev) && (!q || r.rollno.toLowerCase().includes(q) || r.name.toLowerCase().includes(q)))
    .sort((a, b) => a.checked - b.checked || a.rollno.localeCompare(b.rollno)).slice(0, 8);
  sugg.replaceChildren();
  if (!list.length) {
    sugg.hidden = !q;
    if (q) { const li = document.createElement("li"); li.className = "none"; li.textContent = "No matching registration numbers."; sugg.append(li); }
    return;
  }
  sugg.hidden = false;
  list.forEach(r => {
    const li = document.createElement("li"), b = document.createElement("button");
    b.type = "button";
    const left = document.createElement("span"); left.textContent = `${r.rollno} · ${r.name}` + (ev ? "" : ` (${r.event})`);
    const right = document.createElement("span"); right.className = "badge " + (r.checked ? "live" : "closed"); right.textContent = r.checked ? "Checked in" : "Not yet";
    b.append(left, right);
    b.onclick = () => { mEvent.value = r.event_id; mRoll.value = r.rollno; sugg.hidden = true; mRoll.focus(); };
    li.append(b); sugg.append(li);
  });
}
mRoll.addEventListener("input", renderSugg); mRoll.addEventListener("focus", renderSugg); mEvent.addEventListener("change", renderSugg);
document.addEventListener("click", e => { if (!e.target.closest("#manual")) sugg.hidden = true; });
function show(d) {
  if (d.status === "ok" || d.status === "already") { const r = REGS.find(x => x.event_id === d.event_id && x.rollno === d.rollno); if (r) r.checked = true; }
  result.hidden = false; result.className = "alert " + d.status;
  result.textContent = d.name ? `${d.message} ${d.name} (${d.rollno}) · ${d.event}` : d.message;
}
async function checkin(payload) {
  try {
    const r = await fetch("/admin/api/checkin", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(payload)});
    show(await r.json());
  } catch { show({status: "error", message: "Network error. Try again."}); }
}
let scanner = null, busy = false;
$("#scanToggle").onclick = async function () {
  if (scanner) { await scanner.stop().catch(() => {}); scanner = null; this.textContent = "Start camera"; return; }
  scanner = new Html5Qrcode("reader");
  try {
    await scanner.start({facingMode: "environment"}, {fps: 10, qrbox: w => { const m = Math.floor(Math.min(w.width, w.height) * 0.8); return {width: m, height: m}; }}, async text => {
      if (busy) return; busy = true; await checkin({token: text}); setTimeout(() => busy = false, 2500);
    });
    this.textContent = "Stop camera";
  } catch { scanner = null; show({status: "error", message: "Could not open the camera. Allow camera access or use manual check-in."}); }
};
$("#manual").onsubmit = e => { e.preventDefault(); checkin({rollno: $("#mRoll").value, event_id: $("#mEvent").value}); $("#mRoll").value = ""; sugg.hidden = true; };

// Email: EmailJS when configured, else mailto fallback
const mdlg = $("#mailDlg"), cfg = window.EMAILJS || {};
const ready = cfg.EMAILJS_SERVICE_ID && cfg.EMAILJS_TEMPLATE_ID && cfg.EMAILJS_PUBLIC_KEY && window.emailjs;
$$(".mail").forEach(b => b.onclick = () => {
  $("#mTo").value = b.dataset.to; $("#mEv").value = b.dataset.event;
  $("#mSub").value = "Update: " + b.dataset.event; $("#mBody").value = "";
  $("#mailNote").textContent = ready ? "Sends through EmailJS." : "EmailJS is not configured, so this opens your email app.";
  mdlg.showModal();
});
$("#mailForm").onsubmit = async e => {
  e.preventDefault();
  const to = $("#mTo").value, sub = $("#mSub").value, body = $("#mBody").value;
  if (ready) {
    try {
      emailjs.init({publicKey: cfg.EMAILJS_PUBLIC_KEY});
      await emailjs.send(cfg.EMAILJS_SERVICE_ID, cfg.EMAILJS_TEMPLATE_ID, {to_email: to, subject: sub, message: body, event_name: $("#mEv").value, reply_to: window.CONTACT});
      $("#mailNote").textContent = "Email sent."; return;
    } catch { $("#mailNote").textContent = "EmailJS failed. Opening your email app instead."; }
  }
  location.href = `mailto:${to}?subject=${encodeURIComponent(sub)}&body=${encodeURIComponent(body)}`;
  mdlg.close();
};
