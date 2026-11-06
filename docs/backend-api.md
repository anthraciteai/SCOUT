# Backend API

FastAPI app in `backend/app/`. Routers live in `app/routers/` and are registered in
`app/main.py`. Interactive docs when running: **http://localhost:8000/docs**.

All business routes are under `/api`. When `AUTH_DISABLED=false`, requests are Bearer-gated
(see [auth](#auth)).

## Routers

| Router | Prefix | What it does |
|--------|--------|--------------|
| `system` | `/api/system` | Health + status (`auth_disabled`, model info). |
| `auth` | `/api/auth` | `status`, `login`, `me`. Identity + stub/Keycloak tokens. |
| `org` | `/api/org` | Company mission/products (incl. structured per-product build-prompts); per-bid SBIR workspace; shared `proposal.md`; group collab (overlap refresh/promote). |
| `topics` | `/api/topics` | DSIP topics: `search`, `{id}` detail, `{id}/questions`, `{id}/download/{fmt}`, `{id}/reference/{name}`. |
| `topic_intel` | `/api/topics` | OCR → summary → fit for one topic (see below). |
| `matches` | `/api/matches` | Resume → DSIP ranking (the Inbox). Scan + inbox read. |
| `catalog` | `/api/catalog` | Build/search the local topic catalog. |
| `analysis` | `/api/analysis` | The Council (multi-agent) + per-agent working-log chat. |
| `team` | `/api/team` | Company roster. |
| `tracker` | `/api/tracker` | Pipeline stages + outcomes (the bid tracker). |
| `proposals` | `/api/proposals` | Proposal drafts + persona reviews. |
| `debriefs` | `/api/debriefs` | Debrief upload → OCR → lessons. |
| `resume` | `/api/resume` | Resume upload/parse; mark **ME**. |

> Note: `topics` and `topic_intel` share the `/api/topics` prefix. Because `topics` defines a
> catch-all `GET /{topic_id}`, any new single-segment route on `topic_intel` must use a
> two-segment path (e.g. `GET /api/topics/mine/fits`) to avoid being swallowed.

## Topic intelligence endpoints (`topic_intel.py`)

| Method + path | Scope | Notes |
|---------------|-------|-------|
| `GET /api/topics/{id}/text` | shared | OCR text (Docling), with a DSIP-JSON fallback. `?force=` re-OCRs. |
| `POST /api/topics/{id}/summary` | shared | LLM summary (requirements + evidence). `?force=` recomputes. |
| `POST /api/topics/{id}/fit` | per-user | Score vs your profile. `?force=` re-scores (reuses the shared summary). |
| `GET /api/topics/{id}/fit` | per-user | The caller's cached fit, or `null`. **No model call.** |
| `GET /api/topics/mine/fits?ids=a,b,c` | per-user | Which of these topics the caller has already scored. No model call. |

Shared artifacts are computed once and reused across the whole org; fit is private per user.
See [`topic-intelligence.md`](topic-intelligence.md).

## Per-product build-prompts (`org.py`)

Each company defines its own products with a **build prompt** (what SBIR work fits the product)
plus explicit keywords, so Scout is multi-tenant — a new org tunes matching to its own lineup.

| Method + path | Scope | Notes |
|---------------|-------|-------|
| `GET /api/org/company/product-profiles` | company | Structured products `[{id,name,summary,prompt,keywords[]}]`. Migrates legacy `products.md` on first read. |
| `PUT /api/org/company/product-profiles` | company | Save products. Regenerates `products.md`, re-tags company + people so matching reflects the new prompts/keywords. |

Stored at `companies/{id}/products.json`. The keywords are folded directly into the company tag
pack (`catalog._product_keywords`), so they always count in ranking rather than relying on LLM
phrase extraction.

## Auth

- Dev: `AUTH_DISABLED=true` → every request is `dev @ anthracite`; no token needed.
- Prod: send `Authorization: Bearer <jwt>`. The backend verifies the Keycloak token locally
  against the realm JWKS (RS256 + exp + issuer + audience). Stub tokens (`scout.<body>.<sig>`,
  HMAC) are also accepted for scripted/dev use.
- Identity flows through a request-scoped contextvar (`current_identity()` in
  `app/identity.py`); the vault uses it to scope reads/writes and enforce company membership.

## Storage

Persistence is the **vault** (`app/vault.py`): disk at `/data/vault` in dev, S3/SeaweedFS in
prod, same key layout either way. Existence of a key is often the permission gate (e.g.
`companies/{id}/employees/{you}` = employed). Full layout and ACL rules:
[`../architecture/auth-and-storage.md`](../architecture/auth-and-storage.md).

## Run / test

```bash
# tests (inside the backend container)
docker compose exec backend python -m pytest app/tests -q

# restart after a Python change (no auto-reload by design)
docker compose restart backend
```
