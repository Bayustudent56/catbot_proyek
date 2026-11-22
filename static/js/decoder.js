(() => {
  const cfg = JSON.parse(document.getElementById('decoder-config').textContent);
  const csrf = document.querySelector('meta[name="csrf-token"]').content;
  const svg = document.getElementById('catSvg');
  const $ = (id) => document.getElementById(id);

  const DEFAULTS = { tail: 'up', ears: 'normal', sound: 'idle' };
  const PREVIEW_TITLE = { tail: 'Bahasa ekor', ears: 'Bahasa telinga', sound: 'Suara / aksi' };
  const selected = { tail: null, ears: null, sound: null };
  let activeCat = 'tail';
  let requestId = 0;

  const el = (tag, cls, text) => {
    const n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text !== undefined) n.textContent = text;
    return n;
  };

  // ---- Preview gambar dinamis ------------------------------------------------
  function setSvg(cat, value) {
    svg.querySelectorAll(`[data-cat="${cat}"]`).forEach(n => n.classList.toggle('on', n.dataset.v === value));
  }
  function applySelection() {
    Object.keys(DEFAULTS).forEach(cat => setSvg(cat, selected[cat] || DEFAULTS[cat]));
  }

  // ---- UI --------------------------------------------------------------------
  function renderTabs() {
    document.querySelectorAll('[data-tab]').forEach(btn => {
      btn.classList.toggle('on', btn.dataset.tab === activeCat);
      btn.classList.toggle('done', !!selected[btn.dataset.tab]);
    });
    $('previewLabel').textContent = PREVIEW_TITLE[activeCat];
  }

  function renderOptions() {
    const list = $('optionList');
    list.replaceChildren();
    cfg[activeCat].options.forEach((opt, i) => {
      const btn = el('button', 'opt' + (selected[activeCat] === opt.id ? ' on' : ''));
      btn.type = 'button';
      btn.setAttribute('role', 'option');
      btn.setAttribute('aria-selected', String(selected[activeCat] === opt.id));
      const num = el('span', 'opt-num', String(i + 1).padStart(2, '0'));
      const text = el('span', 'opt-text');
      text.append(el('strong', '', opt.label), el('small', '', opt.hint));
      btn.append(num, text);
      if (selected[activeCat] === opt.id) btn.append(el('i', 'bi bi-check2 ms-auto'));

      const preview = () => setSvg(activeCat, opt.id);
      const restore = () => setSvg(activeCat, selected[activeCat] || DEFAULTS[activeCat]);
      btn.addEventListener('mouseenter', preview);
      btn.addEventListener('focus', preview);
      btn.addEventListener('mouseleave', restore);
      btn.addEventListener('blur', restore);
      btn.addEventListener('click', () => {
        selected[activeCat] = selected[activeCat] === opt.id ? null : opt.id;
        renderAll();
        analyze();
      });
      list.appendChild(btn);
    });
  }

  function renderChosen() {
    const row = $('chosenRow');
    row.replaceChildren();
    Object.keys(selected).forEach(cat => {
      if (!selected[cat]) return;
      const opt = cfg[cat].options.find(o => o.id === selected[cat]);
      row.appendChild(el('span', 'pill-soft', `${cfg[cat].label}: ${opt.label}`));
    });
  }

  function renderAll() {
    renderTabs();
    renderOptions();
    renderChosen();
    applySelection();
  }

  // ---- Analisis (server-side di /api/decoder) ----------------------------------
  async function analyze() {
    const hasAny = Object.values(selected).some(Boolean);
    $('resultEmpty').classList.toggle('d-none', hasAny);
    $('resultBody').classList.toggle('d-none', !hasAny);
    if (!hasAny) return;

    const myId = ++requestId;
    try {
      const res = await fetch('/api/decoder', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf },
        body: JSON.stringify(selected),
      });
      const data = await res.json();
      if (myId !== requestId) return; // abaikan respons usang
      if (!res.ok || !data.ok) throw new Error(data.error || 'Gagal menganalisis.');
      renderResult(data);
    } catch (err) {
      $('rQuote').textContent = '⚠️ ' + err.message;
    }
  }

  function renderResult(d) {
    $('resultHead').className = `result-head tone-${d.tone}`;
    $('rBadge').textContent = d.badge;
    $('rQuote').textContent = `“${d.quote}”`;
    $('rSummary').textContent = d.summary;
    $('rInsight').textContent = d.insight;

    const sig = $('rSignals');
    sig.replaceChildren();
    d.signals.forEach(s => {
      const row = el('div', 'signal');
      row.append(el('strong', '', `${s.category}: ${s.label}`), el('small', '', s.reading));
      sig.appendChild(row);
    });

    const conf = $('rConf');
    conf.replaceChildren(el('span', `conf-badge conf-${d.confidence.label.toLowerCase()}`, `Keyakinan ${d.confidence.label}`),
      el('small', 'muted', d.confidence.note));

    const bars = $('rScores');
    bars.replaceChildren();
    d.scores.forEach(s => {
      const row = el('div', 'bar-row');
      const track = el('div', 'bar-track');
      const fill = el('div', 'bar-fill');
      fill.style.width = `${s.pct}%`;
      track.appendChild(fill);
      row.append(el('span', 'bar-label', s.mood), track, el('span', 'bar-pct', `${s.pct}%`));
      bars.appendChild(row);
    });

    const rule = $('rRule');
    rule.classList.toggle('d-none', !d.rule);
    if (d.rule) rule.textContent = `Aturan ${d.rule.id}: ${d.rule.note}`;

    const tips = $('rTips');
    tips.replaceChildren();
    d.tips.forEach(t => { const li = el('li'); li.append(el('i', 'bi bi-check2-circle'), el('span', '', t)); tips.appendChild(li); });

    const vet = $('rVet');
    vet.classList.toggle('d-none', !d.vet_warning);
    if (d.vet_warning) vet.querySelector('span').textContent = d.vet_warning;

    const refs = $('rRefs');
    refs.replaceChildren();
    d.references.forEach(r => refs.appendChild(el('li', '', r)));
  }

  // ---- Event ------------------------------------------------------------------
  document.querySelectorAll('[data-tab]').forEach(btn => btn.addEventListener('click', () => {
    activeCat = btn.dataset.tab;
    renderTabs();
    renderOptions();
    applySelection();
  }));
  $('resetBtn').addEventListener('click', () => {
    Object.keys(selected).forEach(k => { selected[k] = null; });
    renderAll();
    analyze();
  });

  renderAll();
})();
