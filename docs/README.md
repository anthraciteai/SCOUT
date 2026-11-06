# SCOUT docs

Start here. These docs are written to get a new teammate — human or AI — productive fast.

## 30-second mental model

SCOUT ranks open **DoD SBIR/STTR** topics against your resume, then helps you pursue the
good ones. Everything runs **locally**: a React UI, a FastAPI backend, host **Ollama** for the
LLM, **Docling** for OCR, and the public **DSIP** API as the only outside data source.

```
You ─▶ Profile (resume = ME)
        │
        ▼
     Inbox  ──ranks──▶ open DSIP topics        (cheap keyword/embedding overlap)
        │
        ▼
   Workspace (one topic)  ──▶ OCR → Summary → Fit vs you → Reader
        │
        ▼
   Council (optional deep multi-agent pass) ──▶ GO / NO-GO + 0–100
        │
        ▼
   Proposals / Team room ──▶ draft with live LLM feedback
        │
        ▼
   Pipeline + Debriefs ──▶ track outcomes, learn from losses
```

## The docs

| Doc | What's in it |
|-----|--------------|
| [`pages.md`](pages.md) | Every screen in the UI: route, what it's for, which APIs it calls |
| [`workflows.md`](workflows.md) | The end-to-end flows (login → resume → inbox → fit → council → proposal → debrief) + the diagram |
| [`backend-api.md`](backend-api.md) | The FastAPI routers and what each group of endpoints does |
| [`topic-intelligence.md`](topic-intelligence.md) | The OCR → summary → fit pipeline, the Evidence Reader, and how results are stored/scoped |
| [`../architecture/auth-and-storage.md`](../architecture/auth-and-storage.md) | The org vault layout + auth (ACL gates, Keycloak/SeaweedFS) |
| [`../README.md`](../README.md) | How to run it (Docker, dev, config, the agent roster) |

Diagrams (in [`workflows.md`](workflows.md)): [overview](scout-overview.png) ·
[sources](scout-sources.png) · [topic intelligence](scout-topic-intel.png). Each has a
`.dot` source next to it; the old all-in-one is [`scout-workflow.png`](scout-workflow.png).

## Rules of the road (important for agents)

- **Everything is local.** Nothing is sent to third-party LLM services. The DSIP proxy only
  reads public topic data.
- **Host Ollama owns `127.0.0.1:11434`.** Do not start a second Ollama.
- **Don't `docker compose down`** unless you mean to stop the stack. Restart a single service
  with `docker compose restart backend` (Python has no auto-reload; the UI hot-reloads).
- **The cheap ranker is automatic; the Council is not.** Deep LLM passes are always an explicit
  button so you don't burn tokens by accident.
- **`.env` is secret** (gitignored). Only `.env.example` is tracked.

## Layout

```
scout/
  frontend/   React + TypeScript + Vite UI        (src/pages, src/components, src/api)
  backend/    FastAPI + SQLModel + the vault       (app/routers, app/vault.py, app/identity.py)
  docs/       ← you are here
  architecture/   deeper auth/storage notes + diagrams
```
