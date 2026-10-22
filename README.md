# DevOps (Odysseus mod)

What [Odysseus](https://github.com/Jaron-Wilson/odysseus) is doing right now, how fast your models
write, and which coder finishes its runs, with each run's transcript. This was the built-in
**Build > DevOps** page; it is now a mod, and its tab takes over the old page (`replaces: "devops"`),
so `#devops` links, "take me to devops" and saved Workspace tabs open it.

## What it does

- **Happening now**: replies being written, coder runs (Claude Code, OpenCode, Antigravity),
  shell jobs and queued messages, each with a link to its chat.
- **Model speed** for a window (last hour, 24 hours, 7 days, 30 days): tokens per second
  (all tokens over the time spent writing them), tokens per hour, first-token wait, reply time and
  a chart of output over time, per model, with the fastest one marked.
- **Coders**: runs per coder and model, how many finished OK, failed or were cut off, average
  time, tokens, cost; the most picked and the most reliable coder; recent runs with
  **view transcript** (thinking, tool calls with their results, the final answer) and **copy
  resume**.
- A **Happening now** card for the Home page.
- An agent tool, `devops_summary` (read-only): "what's running right now?", "how fast is my model?".
- **Settings**: the window the tab opens with, the refresh interval, which sections show, and
  **export / import** of those settings as JSON (optionally with a snapshot of the numbers).
- A five-step tutorial, shown the first time you open the tab.

It does nothing while the tab is closed: it is a lazy mod that stops after 5 idle minutes, and the
page only refreshes while it is visible.

## Where the numbers come from

The mod has no data of its own besides its settings. It reads the core's stats API, which needs
Odysseus with the `stats.read` permission (the core API PR "read-only stats and machines APIs for
mods"):

| Call | What |
|---|---|
| `GET /api/mods/v1/stats?scope=devops&hours=24` | `src/devops_stats.py`'s snapshot: live, chat, coders |
| `GET /api/mods/v1/stats/transcripts/<run>` | one coder run's parsed transcript |

`stats.read` is server-wide, so Odysseus refuses it for a mod that every user may use: keep
**Who can use it** on "admins" (the default).

## Permissions

| Permission | Why |
|---|---|
| `stats.read` | read what is running, model speed and coder runs, and open a run's transcript |

## Install in Odysseus

Settings > Mods > Browse (the repository has the `odysseus-mod` topic; it is private, so Browse
needs a GitHub token), or Settings > Mods > Install with
`git@github.com:Jaron-Wilson/odysseus-devops.git`. Review the permission and approve. Standard
library only: no setup step.

## Develop

```
python -m pytest -q                 # the mod under the stand-in core
python -m odysseus_mod.devcore      # try it at http://127.0.0.1:7900/ with fake stats
```

Python 3.10+, standard library only. `odysseus_mod/` is the template's SDK (with `stats()`,
`stats_transcript()` and `machines()`).

## License

AGPL-3.0-or-later, like Odysseus, which this page came from.
