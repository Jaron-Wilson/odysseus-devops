// The DevOps tab: what Odysseus is doing now, how fast the models are, which
// coder does best. The numbers come from the core through this mod
// (api/stats -> GET /api/mods/v1/stats?scope=devops). Relative URLs only:
// the page is served under /mods/devops/~<token>/ in a sandboxed frame.
(function () {
  'use strict';
  const boot = JSON.parse(document.body.dataset.boot || '{}');
  const S = boot.settings || { hours: 24, refresh_s: 5, sections: ['live', 'chat', 'coders'] };
  const WINDOWS = boot.windows || { 1: 'Last hour', 24: 'Last 24 hours', 168: 'Last 7 days', 720: 'Last 30 days' };
  const ENGINE = { claude: 'Claude Code', opencode: 'OpenCode', antigravity: 'Antigravity', codex: 'Codex' };
  let hours = S.hours;
  let timer = null;

  const $ = (sel) => document.querySelector(sel);
  const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => (
    { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const fmtN = (n) => (n == null ? '–' : n >= 1e6 ? `${(n / 1e6).toFixed(1)}M`
    : n >= 1e4 ? `${Math.round(n / 1e3)}k` : n >= 1e3 ? `${(n / 1e3).toFixed(1)}k` : String(Math.round(n)));
  const fmtS = (s) => (s == null ? '–' : s < 60 ? `${Math.round(s)}s`
    : s < 3600 ? `${Math.floor(s / 60)}m ${Math.round(s % 60)}s` : `${Math.floor(s / 3600)}h ${Math.round((s % 3600) / 60)}m`);
  const fmtTps = (v) => (v == null ? '–' : `${v}`);
  const pct = (v) => (v == null ? '–' : `${Math.round(v * 100)}%`);
  const when = (t) => new Date(t * 1000).toLocaleString([], { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' });

  // A chat opens in Odysseus in a new tab (a mod frame cannot move the page it is in).
  const chatLink = (sid, name) => (sid
    ? `<a href="/#${encodeURIComponent(sid)}" target="_blank" rel="noopener">${esc(name || 'a chat')}</a>` : esc(name || ''));
  const tile = (label, value, sub = '') => `<div class="dv-tile"><div class="dv-tile-v">${value}</div>
    <div class="dv-tile-l">${esc(label)}</div>${sub ? `<div class="dv-tile-s">${sub}</div>` : ''}</div>`;

  function paintLive(l) {
    if (!l || l.error) return `<div class="dv-empty">Could not read what is running: ${esc((l || {}).error || '')}</div>`;
    const rows = [
      ...(l.replies || []).map((r) => `<div class="dv-live"><span class="dot running"></span><b>Reply</b> in ${chatLink(r.session_id, r.chat)}
        <span class="dv-meta">${fmtS(r.seconds)}${r.watchers ? ` · ${r.watchers} watching` : ''}</span></div>`),
      ...(l.coders || []).map((c) => `<div class="dv-live"><span class="dot running"></span><b>${esc(c.name)}</b> ${esc(c.action)}
        ${c.model ? `<span class="dv-chip">${esc(c.model)}</span>` : ''} in ${chatLink(c.session_id, c.chat)}
        <span class="dv-meta">${fmtS(c.seconds)}</span>${c.status ? `<div class="dv-sub">${esc(c.status)}</div>` : ''}</div>`),
      ...(l.shell_jobs || []).map((j) => `<div class="dv-live"><span class="dot running"></span><b>Shell</b> <code>${esc(j.command)}</code>
        in ${chatLink(j.session_id, j.chat)} <span class="dv-meta">${fmtS(j.seconds)}</span></div>`),
    ];
    return `<div class="dv-tiles">${tile('Replies writing', (l.replies || []).length)}${tile('Coder runs', (l.coders || []).length)}
      ${tile('Shell jobs', (l.shell_jobs || []).length)}${tile('Queued messages', l.queued_messages || 0)}</div>
      ${rows.length ? rows.join('') : '<div class="dv-empty">Nothing running right now.</div>'}`;
  }

  function chart(c) {
    const s = c.series || [];
    if (!s.length) return '';
    const max = Math.max(1, ...s.map((b) => b.output_tokens));
    const W = 100 / s.length;
    const label = (t) => new Date(t * 1000).toLocaleString([], c.bucket_s >= 86400 ? { month: 'short', day: 'numeric' } : { hour: 'numeric' });
    const bars = s.map((b, i) => {
      const h = (b.output_tokens / max) * 100;
      return `<rect x="${i * W + W * 0.12}" y="${100 - h}" width="${W * 0.76}" height="${h}" rx="0.6">
        <title>${esc(label(b.t))}: ${fmtN(b.output_tokens)} tokens, ${b.replies} replies${b.tokens_per_s ? `, ${b.tokens_per_s} tok/s` : ''}</title></rect>`;
    }).join('');
    const ticks = [0, Math.floor(s.length / 2), s.length - 1].filter((v, i, a) => a.indexOf(v) === i)
      .map((i) => `<span style="left:${(i + 0.5) * W}%">${esc(label(s[i].t))}</span>`).join('');
    return `<div class="dv-chart"><div class="dv-chart-top">${fmtN(max)} tokens</div>
      <svg viewBox="0 0 100 100" preserveAspectRatio="none" aria-label="Output tokens over time">${bars}</svg>
      <div class="dv-ticks">${ticks}</div></div>`;
  }

  function paintChat(c) {
    if (!c || c.error) return `<div class="dv-empty">Could not read the replies: ${esc((c || {}).error || '')}</div>`;
    const models = (c.models || []).map((m) => `<tr><td>${esc(m.model)}${m.model === c.fastest_model ? ' <span class="dv-chip dv-good">fastest</span>' : ''}</td>
      <td>${m.replies}</td><td>${fmtN(m.output_tokens)}</td><td><b>${fmtTps(m.tokens_per_s)}</b></td><td>${fmtTps(m.median_tokens_per_s)}</td>
      <td>${fmtS(m.first_token_s)}</td><td>${fmtS(m.reply_s)}</td></tr>`).join('');
    return `<div class="dv-tiles">
        ${tile('Average speed', `${fmtTps(c.tokens_per_s)}<small> tok/s</small>`, 'all tokens / time writing them')}
        ${tile('Tokens per hour', fmtN(c.tokens_per_hour), `average over ${esc(String(WINDOWS[c.hours] || `${c.hours}h`).toLowerCase())}`)}
        ${tile('Last hour', fmtN(c.tokens_last_hour), 'tokens written')}
        ${tile('Replies', c.replies || 0, `${fmtN(c.output_tokens)} out · ${fmtN(c.input_tokens)} in`)}
        ${tile('First token', fmtS(c.first_token_s), 'average wait')}
        ${tile('Reply time', fmtS(c.reply_s), 'average, start to end')}
      </div>${chart(c)}
      ${models ? `<table class="dv-table"><thead><tr><th>Model</th><th>Replies</th><th>Tokens</th><th>tok/s</th><th>median</th><th>First token</th><th>Reply</th></tr></thead><tbody>${models}</tbody></table>`
        : '<div class="dv-empty">No replies in this window.</div>'}`;
  }

  function paintCoders(k) {
    if (!k || k.error) return `<div class="dv-empty">Could not read the coder runs: ${esc((k || {}).error || '')}</div>`;
    const name = (c) => `${esc(c.name)}${c.model ? ` <span class="dv-chip">${esc(c.model)}</span>` : ''}`;
    const fav = k.favorite, best = k.most_reliable;
    const rows = (k.coders || []).map((c) => `<tr><td>${name(c)}${c.model ? '' : ' <span class="dv-meta">model not recorded</span>'}</td>
      <td>${c.runs}${c.running ? ` <span class="dv-meta">(${c.running} now)</span>` : ''}</td><td>${pct(c.success_rate)}</td>
      <td>${c.done} / ${c.failed} / ${c.cut_off}</td><td>${c.avg_minutes == null ? '–' : `${c.avg_minutes}m`}</td>
      <td>${fmtN(c.output_tokens)}</td><td>${fmtTps(c.tokens_per_s)}</td><td>${c.cost_usd ? `$${c.cost_usd.toFixed(2)}` : '–'}</td></tr>`).join('');
    const recent = (k.recent || []).map((r) => {
      const ts = r.transcript || {};
      const c = ts.counts || {};
      const bits = [c.messages != null ? `${c.messages} msgs` : '', c.tool_calls != null ? `${c.tool_calls} tools` : '',
        c.thinking_blocks ? `${c.thinking_blocks} thought` : '', c.turns != null ? `${c.turns} turns` : ''].filter(Boolean).join(' · ');
      const dot = r.status === 'running' ? 'running' : r.status === 'done' ? 'ok' : 'bad';
      return `<div class="dv-run"><span class="dot ${dot}"></span><b>${esc(ENGINE[r.engine] || r.engine)}</b> ${esc(r.action)}
        ${r.model ? `<span class="dv-chip">${esc(r.model)}</span>` : ''} <span class="dv-meta">${esc(r.status)} · ${fmtS(r.seconds)} · ${esc(when(r.started))}${r.output_tokens ? ` · ${fmtN(r.output_tokens)} tokens` : ''}${bits ? ` · ${bits}` : ''}</span>
        ${r.chat_session_id ? `<a href="/#${encodeURIComponent(r.chat_session_id)}" target="_blank" rel="noopener">open chat</a>` : ''}
        ${r.has_transcript ? `<button type="button" data-transcript="${esc(r.id)}">view transcript</button>` : ''}
        ${ts.resume_command ? `<button type="button" data-resume="${esc(ts.resume_command)}">copy resume</button>` : ''}</div>`;
    }).join('');
    return `<div class="dv-tiles">
        ${tile('Most picked', fav ? name(fav) : '–', fav ? `${fav.runs} runs` : 'no runs yet')}
        ${tile('Most reliable', best ? name(best) : '–', best ? `${pct(best.success_rate)} finished OK` : 'needs 3 finished runs')}
        ${tile('Coder runs', k.runs || 0)}
      </div>
      ${rows ? `<table class="dv-table"><thead><tr><th>Coder</th><th>Runs</th><th>Finished OK</th><th>OK / failed / cut off</th><th>Avg time</th><th>Tokens</th><th>tok/s</th><th>Cost</th></tr></thead><tbody>${rows}</tbody></table>` : ''}
      ${recent ? `<div class="dv-section">Recent runs</div>${recent}` : '<div class="dv-empty">No coder runs in this window.</div>'}`;
  }

  async function refresh() {
    const body = $('.dv-body');
    let d;
    try {
      const res = await fetch(`api/stats?hours=${hours}`);
      d = await res.json();
      if (!res.ok) throw new Error(d.error || `HTTP ${res.status}`);
    } catch (e) {
      body.innerHTML = `<div class="dv-empty">Could not load: ${esc(e.message)}</div>`;
      return;
    }
    const name = esc(WINDOWS[d.hours] || '');
    const show = new Set(S.sections || ['live', 'chat', 'coders']);
    const top = window.scrollY;
    body.innerHTML = [
      show.has('live') ? `<div class="dv-section">Happening now</div>${paintLive(d.live)}` : '',
      show.has('chat') ? `<div class="dv-section">Model speed · ${name}</div>${paintChat(d.chat)}` : '',
      show.has('coders') ? `<div class="dv-section">Coders · ${name}</div>${paintCoders(d.coders)}` : '',
      `<div class="dv-foot">Updated ${new Date(d.now * 1000).toLocaleTimeString()} · refreshes every ${S.refresh_s}s while this tab is open.
        "Most picked" is the coder chosen most often; there is no like button, so "most reliable" is the one that finishes OK most often.</div>`,
    ].join('');
    window.scrollTo(0, top);
  }

  // ── Transcripts ──────────────────────────────────────────────────────
  function blockHtml(b) {
    if (b.kind === 'thinking') {
      return `<details class="dv-thinking"><summary>View reasoning${b.clipped ? ` · ${b.fullLen || '?'} chars total` : ''}</summary>
        <pre>${esc(b.text)}</pre></details>`;
    }
    if (b.kind === 'text') {
      return `<div class="dv-msg"><pre class="dv-msg-body">${esc(b.text)}</pre>${b.clipped ? '<div class="dv-note">(message clipped for the viewer)</div>' : ''}</div>`;
    }
    if (b.kind === 'tool_call') {
      const n = b.tool_result_count || 0;
      return `<div class="dv-tool${b.error ? ' err' : ''}"><span class="dv-tool-name">${esc(b.name)}</span>
        <span class="dv-meta">${n ? `${n} result${n === 1 ? '' : 's'}` : 'no result yet'}${b.error ? ' · failed' : ''}</span>
        ${b.hint ? `<div><code>${esc(b.hint)}</code></div>` : ''}
        ${b.output ? `<pre class="dv-tool-output${b.error ? ' err' : ''}">${esc(b.output)}</pre>` : ''}</div>`;
    }
    return '';
  }

  async function openTranscript(id) {
    const ov = $('.dv-overlay');
    ov.hidden = false;
    ov.innerHTML = '<div class="dv-transcript"><div class="dv-empty">Loading…</div></div>';
    let d;
    try {
      const res = await fetch(`api/transcript/${encodeURIComponent(id)}`);
      d = await res.json();
      if (!res.ok) throw new Error(d.error || `HTTP ${res.status}`);
    } catch (e) {
      ov.innerHTML = `<div class="dv-transcript"><div class="dv-transcript-head"><span>Could not open the transcript: ${esc(e.message)}</span>
        <span class="dv-grow"></span><button type="button" data-close>Close</button></div></div>`;
      return;
    }
    const c = d.counts || {};
    const bits = [c.messages != null ? `${c.messages} msgs` : '', c.tool_calls != null ? `${c.tool_calls} tools` : '',
      c.thinking_blocks ? `${c.thinking_blocks} thought` : '', c.turns != null ? `${c.turns} turns` : ''].filter(Boolean).join(' · ');
    const resume = d.resume_command ? `<span class="dv-resume-box"><input readonly value="${esc(d.resume_command)}" aria-label="Resume command">
      <button type="button" data-resume="${esc(d.resume_command)}">Copy</button></span>` : '';
    ov.innerHTML = `<div class="dv-transcript" role="dialog" aria-label="Transcript">
      <div class="dv-transcript-head"><b>${esc(ENGINE[d.engine] || d.engine || '')}</b> · ${esc(d.status || '')} · ${esc(d.model || '')}
        <span class="dv-meta">${bits}</span>${resume}<button type="button" data-close>Close</button></div>
      ${d.truncated ? '<div class="dv-note">Showing the last blocks: this run is long.</div>' : ''}
      ${(d.blocks || []).map(blockHtml).join('') || '<div class="dv-empty">No readable blocks in this transcript.</div>'}
      ${d.final_text ? `<div class="dv-section">Final answer</div><pre class="dv-msg-body">${esc(d.final_text)}</pre>` : ''}</div>`;
  }

  // The frame has no clipboard permission of its own; fall back to a
  // selected text field and the copy command, which a click allows.
  async function copy(text, btn) {
    let ok = false;
    try { await navigator.clipboard.writeText(text); ok = true; } catch (_) {
      const t = document.createElement('textarea');
      t.value = text; document.body.appendChild(t); t.select();
      try { ok = document.execCommand('copy'); } catch (_) { ok = false; }
      t.remove();
    }
    const was = btn.textContent;
    btn.textContent = ok ? 'Copied' : 'Select and copy it';
    setTimeout(() => { btn.textContent = was; }, 1500);
  }

  document.addEventListener('click', (ev) => {
    const t = ev.target;
    const tr = t.closest('[data-transcript]');
    if (tr) { openTranscript(tr.dataset.transcript); return; }
    const rs = t.closest('[data-resume]');
    if (rs) { copy(rs.dataset.resume, rs); return; }
    if (t.closest('[data-close]') || t === $('.dv-overlay')) { const ov = $('.dv-overlay'); ov.hidden = true; ov.innerHTML = ''; }
  });
  document.addEventListener('keydown', (ev) => {
    if (ev.key === 'Escape') { const ov = $('.dv-overlay'); if (!ov.hidden) { ov.hidden = true; ov.innerHTML = ''; } }
  });

  const sel = $('.dv-window');
  sel.innerHTML = Object.entries(WINDOWS).map(([h, n]) => `<option value="${h}"${+h === hours ? ' selected' : ''}>${esc(n)}</option>`).join('');
  sel.addEventListener('change', () => {
    hours = parseInt(sel.value, 10) || 24;
    fetch('api/settings', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ hours }) }).catch(() => {});
    refresh();
  });

  refresh();
  timer = setInterval(() => { if (document.visibilityState === 'visible') refresh(); }, Math.max(2, S.refresh_s || 5) * 1000);
  window.addEventListener('pagehide', () => clearInterval(timer));
}());
