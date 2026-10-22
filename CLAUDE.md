# CLAUDE.md: the DevOps mod

An Odysseus mod (contract: `docs/mods.md` in Jaron-Wilson/odysseus). It is the DevOps page that
used to be built into Odysseus; the numbers stay in the core and come through the mod API.

- `devops_mod/app.py`: routes (`/`, `/api/stats`, `/api/transcript/<run>`, `/cards/now`,
  `/settings`, `/export`, `/import`), the `devops_summary` tool. Uses `odysseus_mod.ModApp`.
- `devops_mod/web/`: the page (`index.html`, `devops.js`, `devops.css`). Relative URLs only: the
  page runs in a sandboxed frame under `/mods/devops/~<token>/`. A chat link opens `/#<session>`
  in a new tab, because a mod frame cannot move the Odysseus page.
- Core calls: `app.core.stats("devops", hours)` and `app.core.stats_transcript(run_id)`
  (`stats.read`, admin-only mods). Settings through `app.core.settings()`.
- Keep it idle when nobody looks: lazy start, `idle_stop_minutes`, refresh only while visible.
- Tests: `python -m pytest -q` (under `odysseus_mod.devcore`, whose `stats` and `transcripts`
  the tests fill in). Every feature gets a test; the tutorial test checks it names the features.
- American English, no em dashes. Bump `version` (and `tutorial.version` when the features
  change) for each release; tag `vX.Y.Z`.
