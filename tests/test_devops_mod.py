"""The DevOps mod under the stand-in core (odysseus_mod.devcore), as Odysseus
runs it: through the proxy with a signed identity, the stats it reads from
the core (stats.read), the transcript viewer, the card, the settings with
export and import, and the agent tool.
Run from the mod folder: python -m pytest -q"""
import json
import os
import sys
import time
import urllib.error
import urllib.request

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from odysseus_mod.devcore import DevCore  # noqa: E402

NOW = time.time()
SNAPSHOT = {
    "now": NOW, "hours": 24, "windows": [1, 24, 168, 720],
    "live": {"replies": [{"session_id": "s1", "chat": "Fix the build", "seconds": 12, "watchers": 1}],
             "coders": [{"id": "0123abcd", "engine": "claude", "name": "Claude Code", "model": "opus",
                         "action": "fix", "session_id": "s1", "chat": "Fix the build", "seconds": 95,
                         "prompt": "fix it", "status": "editing app.py"}],
             "shell_jobs": [], "queued_messages": 2},
    "chat": {"hours": 24, "replies": 40, "output_tokens": 52000, "input_tokens": 900000, "tokens_per_hour": 2167,
             "tokens_last_hour": 3000, "tokens_per_s": 61.5, "first_token_s": 0.8, "reply_s": 14.2,
             "models": [{"model": "qwen3:8b", "replies": 30, "output_tokens": 40000, "tokens_per_s": 72.1,
                         "median_tokens_per_s": 70.0, "first_token_s": 0.5, "reply_s": 9.0},
                        {"model": "opus", "replies": 10, "output_tokens": 12000, "tokens_per_s": 41.0,
                         "median_tokens_per_s": 40.0, "first_token_s": 2.0, "reply_s": 30.0}],
             "fastest_model": "qwen3:8b", "busiest_model": "qwen3:8b", "bucket_s": 3600,
             "series": [{"t": NOW - 3600, "output_tokens": 500, "replies": 2, "tokens_per_s": 60.0}]},
    "coders": {"runs": 5, "coders": [{"engine": "claude", "name": "Claude Code", "model": "opus", "runs": 5,
                                      "running": 1, "done": 3, "failed": 1, "cut_off": 0, "success_rate": 0.75,
                                      "avg_minutes": 6.5, "output_tokens": 9000, "tokens_per_s": 20.0,
                                      "cost_usd": 1.25}],
               "favorite": {"name": "Claude Code", "model": "opus", "runs": 5},
               "most_reliable": {"name": "Claude Code", "model": "opus", "success_rate": 0.75, "runs": 5},
               "recent": [{"id": "0123abcd", "engine": "claude", "model": "opus", "action": "fix", "status": "done",
                           "started": NOW - 600, "finished": NOW - 300, "seconds": 300.0, "output_tokens": 900,
                           "cost_usd": 0.2, "chat_session_id": "s1", "chat_name": "Fix the build",
                           "has_transcript": True,
                           "transcript": {"counts": {"messages": 4}, "preview": "ok",
                                          "resume_command": "claude --resume abc", "truncated": False}}]},
}
TRANSCRIPT = {"id": "0123abcd", "engine": "claude", "model": "opus", "status": "done", "counts": {"messages": 4},
              "blocks": [{"kind": "text", "text": "Fixed <the> build"},
                         {"kind": "tool_call", "name": "Edit", "output": "ok", "tool_result_count": 1}],
              "final_text": "Done.", "resume_command": "claude --resume abc", "truncated": False}


def get(url, method="GET", body=None, headers=None, raw=None):
    data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={"Content-Type": "application/json", **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


@pytest.fixture(scope="module")
def core(tmp_path_factory):
    c = DevCore(ROOT, port=0, user="alice", state_dir=str(tmp_path_factory.mktemp("devcore")))
    c.stats = json.loads(json.dumps(SNAPSHOT))
    c.transcripts["0123abcd"] = TRANSCRIPT
    c.serve()
    c.start_mod()
    yield c
    c.close()


def mod(core, path):
    return f"{core.url}/mods/devops{path}"


def test_manifest_replaces_the_old_page_and_asks_only_for_stats():
    with open(os.path.join(ROOT, "odysseus-mod.json")) as f:
        m = json.load(f)
    tab = m["ui"]["tabs"][0]
    assert (tab["replaces"], tab["section"], tab["icon"]) == ("devops", "build", "devops")
    assert m["permissions"] == ["stats.read"]
    assert m["runtime"]["start"] == "lazy" and m["runtime"]["idle_stop_minutes"] > 0


def test_manifest_has_a_tutorial_written_for_this_mod():
    with open(os.path.join(ROOT, "odysseus-mod.json")) as f:
        tut = json.load(f)["tutorial"]
    text = " ".join(s["title"] + " " + s["body"] for s in tut["steps"])
    assert 2 <= len(tut["steps"]) <= 8
    for words in ("Happening now", "tokens per second", "transcript", "Export", "Import", "devops_summary"):
        assert words in text, words
    assert "My Mod" not in text and "\u2014" not in text
    assert any((s.get("action") or {}).get("settings") for s in tut["steps"])


def test_health_and_unsigned_requests(core):
    assert get(f"http://127.0.0.1:{core.mod_port}/health")[0] == 200
    assert get(f"http://127.0.0.1:{core.mod_port}/")[0] == 401
    assert get(f"http://127.0.0.1:{core.mod_port}/api/stats")[0] == 401


def test_page_and_its_assets(core):
    code, body = get(mod(core, "/"))
    assert code == 200 and b'data-boot="' in body and b"static/devops.js" in body
    assert b"&quot;hours&quot;: 24" in body           # the settings ride along, escaped
    assert get(mod(core, "/static/devops.js"))[0] == 200
    assert get(mod(core, "/static/devops.css"))[0] == 200
    assert get(mod(core, "/static/app.py"))[0] == 404
    js = open(os.path.join(ROOT, "devops_mod", "web", "devops.js")).read()
    assert "fetch('/" not in js and 'fetch("/' not in js      # relative URLs only (the frame URL)


def test_stats_come_from_the_core(core):
    code, body = get(mod(core, "/api/stats?hours=24"))
    d = json.loads(body)
    assert code == 200 and d["scope"] == "devops" and d["chat"]["fastest_model"] == "qwen3:8b"


def test_transcripts(core):
    code, body = get(mod(core, "/api/transcript/0123abcd"))
    assert code == 200 and json.loads(body)["blocks"][0]["text"] == "Fixed <the> build"
    assert get(mod(core, "/api/transcript/ffffffff"))[0] == 404
    assert get(mod(core, "/api/transcript/not-an-id"))[0] == 400


def test_card(core):
    code, body = get(mod(core, "/cards/now"))
    assert code == 200 and b"running now" in body and b"61.5 tok/s" in body and b"2 queued" in body


def test_settings_form_and_api(core):
    assert get(mod(core, "/settings"))[0] == 200
    code, _ = get(mod(core, "/settings"), "POST", raw=b"hours=168&refresh_s=1&sections=live&sections=coders",
                  headers={"Content-Type": "application/x-www-form-urlencoded"})
    assert code in (200, 303)
    saved = json.loads(open(os.path.join(core.state_dir, "settings.json")).read())
    assert saved == {"hours": 168, "refresh_s": 2, "sections": ["live", "coders"]}
    code, body = get(mod(core, "/api/settings"), "POST", {"hours": 1, "evil": True})
    assert code == 200 and json.loads(body)["hours"] == 1 and "evil" not in json.loads(body)
    get(mod(core, "/api/settings"), "POST", {"hours": 24, "refresh_s": 5, "sections": ["live", "chat", "coders"]})


def test_export_and_import(core):
    get(mod(core, "/api/settings"), "POST", {"hours": 720, "refresh_s": 30})
    code, body = get(mod(core, "/export"))
    exp = json.loads(body)
    assert code == 200 and exp["kind"] == "odysseus-devops-export" and exp["settings"]["hours"] == 720
    assert "stats" not in exp
    code, body = get(mod(core, "/export?stats=1"))
    assert json.loads(body)["stats"]["coders"]["runs"] == 5
    get(mod(core, "/api/settings"), "POST", {"hours": 1, "refresh_s": 5})
    code, body = get(mod(core, "/import"), "POST", exp)
    assert code == 200 and json.loads(body)["settings"]["hours"] == 720
    assert get(mod(core, "/import"), "POST", {"kind": "something-else", "settings": {}})[0] == 400
    assert get(mod(core, "/import"), "POST", raw=b"not json")[0] == 400
    assert get(mod(core, "/import"), "POST", dict(exp, version=9))[0] == 400
    get(mod(core, "/api/settings"), "POST", {"hours": 24, "refresh_s": 5})


def test_the_agent_tool(core):
    names = [t["function"]["name"] for t in core.list_tools()]
    assert names == ["devops_summary"]
    out = core.call_tool("devops_summary", {"hours": 24})
    text = out["output"]
    assert "2 queued messages" in text and "Claude Code fix (opus)" in text
    assert "61.5 tok/s" in text and "Fastest model: qwen3:8b" in text and "Most reliable: Claude Code (75%" in text
    assert "/#mod/devops/devops" in text
    schema = core.list_tools()[0]
    assert schema["x-odysseus"]["read_only"] is True


def test_without_the_permission_it_says_so(core):
    core.perms.discard("stats.read")
    try:
        time.sleep(2.1)          # past the mod's 2 second cache
        code, body = get(mod(core, "/api/stats?hours=1"))
        assert code == 503 and b"refused" in body
        assert "error" in core.call_tool("devops_summary", {"hours": 1})
    finally:
        core.perms.add("stats.read")


def test_clean_settings_unit():
    from devops_mod.app import clean_settings
    assert clean_settings(None) == {"hours": 24, "refresh_s": 5, "sections": ["live", "chat", "coders"]}
    assert clean_settings({"hours": 5, "refresh_s": "9999", "sections": ["nope"]}) == {
        "hours": 24, "refresh_s": 300, "sections": ["live", "chat", "coders"]}
