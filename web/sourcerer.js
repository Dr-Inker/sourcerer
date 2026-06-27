const REPO_URL = "https://github.com/Dr-Inker/sourcerer";
const DEMO_BASE = "demo";
const STAGE_ORDER = ["discover", "research", "synthesize"];
const STAGE_LABEL = { discover: "Discover", research: "Research", synthesize: "Synthesize" };

function esc(s) {
  const d = document.createElement("div");
  d.textContent = s == null ? "" : String(s);
  return d.innerHTML;
}
function sleep(ms) { return new Promise((r) => setTimeout(r, ms)); }

async function loadManifest() {
  try {
    const r = await fetch(`${DEMO_BASE}/manifest.json`, { cache: "no-store" });
    if (!r.ok) throw new Error();
    return (await r.json()).presets || [];
  } catch {
    return [];
  }
}

function renderPresets(presets) {
  const nav = document.getElementById("presets");
  nav.innerHTML = "";
  if (!presets.length) {
    nav.innerHTML = '<p class="muted">No sample runs generated yet.</p>';
    return;
  }
  presets.forEach((p) => {
    const b = document.createElement("button");
    b.className = "preset";
    b.textContent = p.label;
    b.onclick = () => runPreset(p);
    nav.appendChild(b);
  });
}

async function runPreset(preset) {
  const out = document.getElementById("result");
  const stageBox = document.getElementById("stages");
  out.innerHTML = "";
  stageBox.innerHTML = "";
  let data;
  try {
    const r = await fetch(`${DEMO_BASE}/${preset.slug}.json`, { cache: "no-store" });
    if (!r.ok) throw new Error();
    data = await r.json();
  } catch {
    stageBox.innerHTML = `<p class="muted">Sample run for "${esc(preset.label)}" hasn't been generated yet.</p>`;
    return;
  }
  await playStages(stageBox, data.spans || []);
  renderResult(out, data);
}

async function playStages(box, spans) {
  const byName = Object.fromEntries(spans.map((s) => [s.name, s]));
  for (const name of STAGE_ORDER) {
    const row = document.createElement("div");
    row.className = "stage running";
    row.innerHTML = `<span class="spin"></span> ${STAGE_LABEL[name] || name}&hellip;`;
    box.appendChild(row);
    const rec = byName[name];
    const ms = rec ? Math.min(1200, Math.max(300, rec.ms * 8)) : 500;
    await sleep(ms);
    const ok = rec ? rec.ok : true;
    row.className = "stage done" + (ok ? "" : " err");
    row.innerHTML = `${ok ? "✓" : "✗"} ${STAGE_LABEL[name] || name}`;
  }
}

function renderResult(out, d) {
  const c = d.candidate || {};
  const claims = (d.claims || [])
    .map((cl) => `<li>${esc(cl.text)} <a class="cite" href="${esc(cl.citation)}" target="_blank" rel="noopener">source &#8599;</a></li>`)
    .join("");
  const unverified = (d.unverified || []).map((u) => `<li>${esc(u)}</li>`).join("");
  const sources = (d.evidence || [])
    .map((e) => `<li><span class="kind">${esc(e.kind)}</span> <a href="${esc(e.source_url)}" target="_blank" rel="noopener">${esc(e.source_url)}</a></li>`)
    .join("");
  out.innerHTML = `
    <div class="cand">
      <h3>${esc(c.name || c.login)} <a href="${esc(c.profile_url)}" target="_blank" rel="noopener">@${esc(c.login)} &#8599;</a></h3>
      <div class="scores">
        <span class="score">fit <b>${(d.fit_score ?? 0).toFixed(2)}</b></span>
        <span class="score grounded">grounding <b>${(d.grounding_score ?? 0).toFixed(2)}</b></span>
      </div>
    </div>
    <h4>Grounded claims <span class="muted">(each cites real evidence)</span></h4>
    <ul class="claims">${claims || '<li class="muted">none</li>'}</ul>
    ${unverified ? `<h4>Unverified <span class="muted">&mdash; stated, but the agent refused to assert it</span></h4><ul class="unverified">${unverified}</ul>` : ""}
    <h4>Outreach draft</h4>
    <pre class="outreach">${esc(d.outreach_draft)}</pre>
    <details class="sources"><summary>Evidence (${(d.evidence || []).length})</summary><ul>${sources}</ul></details>
    <p class="stamp muted">Cached sample run &middot; model ${esc(d.model)} &middot; generated ${esc(d.generated_at)} &middot; <a href="${REPO_URL}" target="_blank" rel="noopener">run it yourself &#8599;</a></p>
  `;
}

(async function () {
  renderPresets(await loadManifest());
})();
