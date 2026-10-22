"""DevOps: what Odysseus is doing, how fast the models write, which coder does best.

The numbers come from the core (GET /api/mods/v1/stats?scope=devops, the
stats.read permission, src/devops_stats.py there): this mod is the page,
the home card, the agent tool and the settings. It keeps no data of its own
besides its settings, and does nothing while nobody has the tab open (it is
a lazy mod that stops after 5 idle minutes).

Run it without Odysseus:   python -m odysseus_mod.devcore
"""
from __future__ import annotations

import html as _html
import json
import os
import re
import threading
import time
from typing import Any, Dict, Optional

from odysseus_mod import CoreError, ModApp, Response, html, json_response, redirect

MOD_ID = "devops"
WINDOWS = {1: "Last hour", 24: "Last 24 hours", 168: "Last 7 days", 720: "Last 30 days"}
SECTIONS = ("live", "chat", "coders")
DEFAULTS: Dict[str, Any] = {"hours": 24, "refresh_s": 5, "sections": list(SECTIONS)}
EXPORT_KIND = "odysseus-devops-export"
_RUN_ID_RE = re.compile(r"^[0-9a-f]{8}$")
WEB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")
STATIC = {"devops.js": "text/javascript; charset=utf-8", "devops.css": "text/css; charset=utf-8"}
ENGINE_NAMES = {"claude": "Claude Code", "opencode": "OpenCode", "antigravity": "Antigravity", "codex": "Codex"}

app = ModApp(mod_id=MOD_ID)
_cache: Dict[str, Any] = {}
_cache_lock = threading.Lock()
CACHE_S = 2.0           # several open tabs and the card share one core call


# ── Settings ────────────────────────────────────────────────────────────────

def clean_settings(raw: Any) -> Dict[str, Any]:
    """Settings with defaults filled in; anything unknown or out of range is dropped."""
    out = dict(DEFAULTS)
    if not isinstance(raw, dict):
        return out
    try:
        h = int(float(raw.get("hours", out["hours"])))
        if h in WINDOWS:
            out["hours"] = h
    except (TypeError, ValueError):
        pass
    try:
        out["refresh_s"] = max(2, min(int(float(raw.get("refresh_s", out["refresh_s"]))), 300))
    except (TypeError, ValueError):
        pass
    secs = raw.get("sections")
    if isinstance(secs, list):
        picked = [s for s in SECTIONS if s in secs]
        out["sections"] = picked or list(SECTIONS)
    return out


def settings() -> Dict[str, Any]:
    try:
        return clean_settings(app.core.settings())
    except CoreError:
        return dict(DEFAULTS)


def save_settings(values: Dict[str, Any]) -> Dict[str, Any]:
    s = clean_settings(values)
    app.core.save_settings(s)
    return s


# ── Stats from the core ─────────────────────────────────────────────────────

class StatsUnavailable(Exception):
    pass


def snapshot(hours: int) -> Dict[str, Any]:
    if app.core.standalone:
        raise StatsUnavailable("DevOps reads Odysseus's own activity, so it only works installed in Odysseus.")
    hours = hours if hours in WINDOWS else 24
    with _cache_lock:
        hit = _cache.get(hours)
        if hit and time.time() - hit[0] < CACHE_S:
            return hit[1]
    try:
        data = app.core.stats("devops", hours)
    except CoreError as e:
        if e.status == 403:
            raise StatsUnavailable(f"Odysseus refused the stats: {e.detail}")
        raise StatsUnavailable(f"Odysseus did not answer ({e.status}: {e.detail})")
    except OSError as e:
        raise StatsUnavailable(f"Odysseus did not answer ({type(e).__name__})")
    with _cache_lock:
        _cache[hours] = (time.time(), data)
    return data


def summary_text(d: Dict[str, Any]) -> str:
    """The agent tool's answer: what is running and the window's numbers."""
    lines = []
    live = d.get("live") or {}
    if live.get("error"):
        lines.append(f"Running now: unknown ({live['error']}).")
    else:
        lines.append(f"Running now: {len(live.get('replies') or [])} replies being written, "
                     f"{len(live.get('coders') or [])} coder runs, {len(live.get('shell_jobs') or [])} shell jobs, "
                     f"{live.get('queued_messages', 0)} queued messages.")
        for c in (live.get("coders") or [])[:5]:
            lines.append(f"- {c.get('name') or c.get('engine')} {c.get('action') or ''}"
                         f"{' (' + c['model'] + ')' if c.get('model') else ''} in "
                         f"{c.get('chat') or 'a chat'}, {int(c.get('seconds') or 0)}s so far")
    window = WINDOWS.get(int(d.get("hours") or 24), f"{d.get('hours')}h").lower()
    chat = d.get("chat") or {}
    if chat.get("error"):
        lines.append(f"Model speed: unknown ({chat['error']}).")
    else:
        lines.append(f"Model speed, {window}: {chat.get('replies', 0)} replies, "
                     f"{chat.get('tokens_per_s') or '?'} tok/s on average, "
                     f"{chat.get('tokens_per_hour') or 0} tokens per hour, first token after "
                     f"{chat.get('first_token_s') if chat.get('first_token_s') is not None else '?'}s.")
        if chat.get("fastest_model"):
            lines.append(f"Fastest model: {chat['fastest_model']}.")
        for m in (chat.get("models") or [])[:6]:
            lines.append(f"- {m.get('model')}: {m.get('replies')} replies, {m.get('tokens_per_s') or '?'} tok/s, "
                         f"{m.get('output_tokens')} tokens")
    k = d.get("coders") or {}
    if k.get("error"):
        lines.append(f"Coders: unknown ({k['error']}).")
    else:
        fav, best = k.get("favorite"), k.get("most_reliable")
        lines.append(f"Coder runs, {window}: {k.get('runs', 0)}."
                     + (f" Most picked: {fav.get('name')}{' ' + fav['model'] if fav.get('model') else ''}"
                        f" ({fav.get('runs')} runs)." if fav else "")
                     + (f" Most reliable: {best.get('name')} ({round((best.get('success_rate') or 0) * 100)}% "
                        "finished OK)." if best else ""))
    lines.append(f"DevOps tab: {app.core.link(MOD_ID, 'devops')}")
    return "\n".join(lines)


# ── Pages ───────────────────────────────────────────────────────────────────

def _read(name: str) -> str:
    with open(os.path.join(WEB, name), "r", encoding="utf-8") as f:
        return f.read()


@app.get("/")
def page(req):
    s = settings()
    boot = json.dumps({"settings": s, "windows": WINDOWS, "standalone": app.core.standalone})
    return html(_read("index.html").replace("__BOOT__", _html.escape(boot, quote=True)))


@app.get("/static/{name}")
def static(req):
    name = req.params["name"]
    if name not in STATIC:
        return json_response({"error": "not found"}, 404)
    return Response(_read(name), 200, STATIC[name], headers=[("X-Content-Type-Options", "nosniff")])


@app.get("/api/stats")
def api_stats(req):
    try:
        hours = int(float(req.query.get("hours") or settings()["hours"]))
    except ValueError:
        hours = 24
    try:
        return json_response(snapshot(hours))
    except StatsUnavailable as e:
        return json_response({"error": str(e)}, 503)


@app.get("/api/transcript/{run_id}")
def api_transcript(req):
    run_id = req.params["run_id"]
    if not _RUN_ID_RE.match(run_id):
        return json_response({"error": "not a run id"}, 400)
    if app.core.standalone:
        return json_response({"error": "Transcripts are read from Odysseus."}, 503)
    try:
        return json_response(app.core.stats_transcript(run_id))
    except CoreError as e:
        return json_response({"error": e.detail}, e.status if e.status in (403, 404) else 502)


@app.get("/cards/now")
def card(req):
    try:
        d = snapshot(settings()["hours"])
    except StatsUnavailable as e:
        body = f"<div class=m>{_html.escape(str(e))}</div>"
    else:
        live = d.get("live") or {}
        chat = d.get("chat") or {}
        busy = len(live.get("replies") or []) + len(live.get("coders") or []) + len(live.get("shell_jobs") or [])
        body = (f"<div class=n>{busy}</div><div class=l>running now</div>"
                f"<div class=m>{_html.escape(str(chat.get('tokens_per_s') or '–'))} tok/s · "
                f"{len(live.get('coders') or [])} coder runs · {live.get('queued_messages', 0)} queued</div>")
    return html("<!doctype html><meta charset=utf-8><meta http-equiv=refresh content=30>"
                "<style>body{font:13px system-ui,sans-serif;color:#ddd;background:transparent;margin:10px}"
                ".n{font-size:26px;font-weight:600}.l{color:#999}.m{margin-top:6px;color:#bbb}</style>"
                f"<body>{body}</body>")


SETTINGS_PAGE = """<!doctype html><html><head><meta charset="utf-8"><title>DevOps settings</title>
<link rel="stylesheet" href="static/devops.css"></head><body class="dv-settings">
<h1>DevOps settings</h1>
<form method="post" action="settings">
<label>Window the tab opens with <select name="hours">{windows}</select></label>
<label>Refresh every <input name="refresh_s" type="number" min="2" max="300" value="{refresh}"> seconds
 (only while the tab is open and visible)</label>
<fieldset><legend>Sections</legend>{sections}</fieldset>
<button type="submit">Save</button> <span class="dv-meta">{saved}</span>
</form>
<h2>Export and import</h2>
<p class="dv-meta">This mod keeps only these settings; the numbers live in Odysseus. An export can also hold a
snapshot of the numbers for the window above, to keep or compare later.</p>
<p><a class="dv-btn" href="export" download="devops-settings.json">Export settings</a>
 <a class="dv-btn" href="export?stats=1" download="devops-export.json">Export with a stats snapshot</a></p>
<form id="imp"><label>Import a DevOps export <input type="file" name="f" accept="application/json,.json"></label>
<button type="submit">Import</button> <span id="impmsg" class="dv-meta"></span></form>
<script>
document.getElementById('imp').addEventListener('submit', async (ev) => {{
  ev.preventDefault();
  const f = ev.target.f.files[0]; const msg = document.getElementById('impmsg');
  if (!f) {{ msg.textContent = 'Pick a file first.'; return; }}
  const r = await fetch('import', {{ method: 'POST', headers: {{ 'Content-Type': 'application/json' }}, body: await f.text() }});
  const d = await r.json().catch(() => ({{}}));
  msg.textContent = r.ok ? 'Imported. Reloading…' : (d.error || 'Import failed');
  if (r.ok) setTimeout(() => location.reload(), 600);
}});
</script></body></html>"""


@app.get("/settings")
def settings_page(req):
    s = settings()
    windows = "".join(f"<option value='{h}'{' selected' if h == s['hours'] else ''}>{_html.escape(n)}</option>"
                      for h, n in WINDOWS.items())
    names = {"live": "Happening now", "chat": "Model speed", "coders": "Coders"}
    sections = "".join(f"<label><input type=checkbox name=sections value={k}"
                       f"{' checked' if k in s['sections'] else ''}> {names[k]}</label>" for k in SECTIONS)
    return html(SETTINGS_PAGE.format(windows=windows, refresh=s["refresh_s"], sections=sections,
                                     saved="Saved." if req.query.get("saved") else ""))


@app.post("/settings")
def settings_save(req):
    from urllib.parse import parse_qs
    form = parse_qs(req.body.decode("utf-8", "replace"))
    save_settings({"hours": (form.get("hours") or ["24"])[0], "refresh_s": (form.get("refresh_s") or ["5"])[0],
                   "sections": form.get("sections") or []})
    return redirect("settings?saved=1")


@app.post("/api/settings")
def settings_api(req):
    body = req.json()
    cur = settings()
    if isinstance(body, dict):
        cur.update({k: v for k, v in body.items() if k in DEFAULTS})
    return json_response(save_settings(cur))


# ── Export and import ───────────────────────────────────────────────────────

def export_data(with_stats: bool = False) -> Dict[str, Any]:
    s = settings()
    out: Dict[str, Any] = {"kind": EXPORT_KIND, "version": 1, "exported_at": int(time.time()), "settings": s}
    if with_stats:
        try:
            out["stats"] = snapshot(s["hours"])
        except StatsUnavailable as e:
            out["stats_error"] = str(e)
    return out


def import_data(data: Any) -> Dict[str, Any]:
    if not isinstance(data, dict) or data.get("kind") != EXPORT_KIND:
        raise ValueError("Not a DevOps export (its \"kind\" must be odysseus-devops-export)")
    if int(data.get("version") or 0) != 1:
        raise ValueError("This export is from a newer DevOps; update the mod first")
    if not isinstance(data.get("settings"), dict):
        raise ValueError("The export has no settings")
    return save_settings(data["settings"])


@app.get("/export")
def export_route(req):
    body = json.dumps(export_data(req.query.get("stats") == "1"), indent=1, default=str)
    name = "devops-export.json" if req.query.get("stats") == "1" else "devops-settings.json"
    return Response(body, 200, "application/json",
                    headers=[("Content-Disposition", f'attachment; filename="{name}"')])


@app.post("/import")
def import_route(req):
    if len(req.body) > 5_000_000:
        return json_response({"error": "That file is too big for a DevOps export"}, 413)
    try:
        data = json.loads(req.body or b"null")
    except ValueError:
        return json_response({"error": "That file is not JSON"}, 400)
    try:
        return json_response({"ok": True, "settings": import_data(data)})
    except ValueError as e:
        return json_response({"error": str(e)}, 400)


# ── The agent tool ──────────────────────────────────────────────────────────

@app.tool("devops_summary",
          "What Odysseus is doing right now (replies being written, coder runs, shell jobs, queued messages) "
          "and, for a time window, each model's speed in tokens per second and which coder finishes its "
          "runs. Read-only. Use for 'what is running', 'how fast is my model', 'which coder is most reliable'.",
          {"hours": {"type": "integer", "enum": list(WINDOWS),
                     "description": "The window: 1, 24 (default), 168 (7 days) or 720 (30 days)."}},
          keywords=["devops", "tokens per second", "tok/s", "model speed", "coder", "running"], read_only=True)
def devops_summary(req, args):
    try:
        hours = int(args.get("hours") or settings()["hours"])
    except (TypeError, ValueError):
        hours = 24
    try:
        d = snapshot(hours)
    except StatsUnavailable as e:
        return {"error": str(e)}
    return {"output": summary_text(d), "data": {"hours": d.get("hours"), "live": d.get("live")}}


def main():
    app.run()
