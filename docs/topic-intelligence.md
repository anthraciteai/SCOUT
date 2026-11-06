# Topic intelligence

How SCOUT turns a raw solicitation into a readable summary and a personal fit, how the Evidence
Reader works, and how all of it is stored and scoped.

Code: `backend/app/routers/topic_intel.py`, `frontend/src/pages/Workspace.tsx`,
`frontend/src/components/EvidenceReader.tsx`, `frontend/src/lib/evidence.ts`.

This is separate from the cheap Inbox ranker (`matcher.py`). The ranker is keyword/embedding
overlap over DSIP *summary* JSON. Topic intelligence pulls the **full solicitation PDF** and
runs OCR + the LLM.

---

## The pipeline

```
DSIP PDF ──Docling OCR──▶ raw text ──LLM──▶ summary ──┐
                           (fallback:        {tldr,     │   + capability text
                            DSIP details     problem,   │   (your resume ME +
                            JSON)            objective,  │    company mission/products)
                                            phases,      │
                                            requirements │
                                            [{need,      ▼
                                             evidence}], LLM ──▶ fit
                                            keywords}        {overall_fit 0–100,
                                                              recommendation GO/NO-GO,
                                                              requirements[{need, status:
                                                               meets|partial|gap, evidence,
                                                               matched_capability}],
                                                              strengths[], gaps[]}
```

Every step is cached, so re-opening a topic is cheap:

- `_ensure_text(topic_id)` — downloads the PDF, OCRs with Docling (off-thread). Falls back to
  harvesting readable strings from the DSIP `/details` JSON if there's no usable PDF.
- `_ensure_summary(topic_id)` — one LLM call that returns structured JSON.
- `_fit(topic_id)` — compares the shared summary's requirements to *your* capability text and
  returns a per-requirement verdict. Forcing a re-score reuses the shared summary (it does
  **not** re-OCR or re-summarize — that work is identity-independent).

## Shared vs private (and why)

| Artifact | Depends on | Scope | Vault key |
|----------|-----------|-------|-----------|
| OCR text | the topic only | **shared, global** | `sbirs/{id}/intel/text.json` |
| Summary | the topic only | **shared, global** | `sbirs/{id}/intel/summary.json` |
| Fit | the topic **and you** | **per-user** | `sbir/{id}/{company}/users/{you}/fit.json` |

The OCR and summary are identical for everyone who looks at the same solicitation, so they're
computed **once and reused across every group and org** — a big token saving. A fit is scored
against one person's resume, so it's private: keyed by the caller's verified identity and read
back only for that same person. A legacy flat disk cache (`{data_dir}/topic_intel/{id}/`) is
migrated into the vault on first read, so nothing is re-OCR'd during the transition.

## Saving tokens

- The summary is shared, so the expensive OCR + summarize happens once per topic, ever.
- `GET /api/topics/{id}/fit` returns your cached fit with **no model call**, so the Workspace
  can show an existing fit instantly on open.
- `GET /api/topics/mine/fits?ids=…` tells the Inbox which topics you've already scored (gold
  ring on the Opportunity map) — also no model call.
- A forced re-score only re-runs the fit, never the OCR/summary.

## The Evidence Reader

`Workspace → Reader`. Goal: make the raw OCR trustworthy by linking each **requirement** back
to the **sentence(s)** it was derived from.

- `frontend/src/lib/evidence.ts`
  - `splitSegments(text)` — splits the raw text into segments such that joining them back
    exactly reproduces the original (no characters lost).
  - `buildEvidenceModel(text, requirements, {minShared, minFrac})` — matches each requirement's
    evidence quote to text segments using **significant-token overlap** (robust to OCR noise
    and paraphrase — the LLM's quote rarely matches the OCR verbatim). Returns which segments
    belong to which requirements, plus how many requirements were grounded.
  - Color helpers (`EVIDENCE_PALETTE`, `colorForReq`, `rgba`).
- `frontend/src/components/EvidenceReader.tsx` — two panes: the requirements list (color
  swatches) and the raw text with each matched segment tinted. Hovering either side highlights
  the other (bidirectional). A badge shows "N of M grounded"; requirements with no match are
  flagged.

## Auth

Identity is the thing that makes per-user fit meaningful. `backend/app/identity.py`:

- **Dev:** `AUTH_DISABLED=true` → a fixed `dev @ anthracite` identity.
- **Stub tokens:** `scout.<body>.<sig>`, HMAC-signed with `auth_secret` (scripts/dev).
- **Keycloak:** the access token is verified **locally** against the realm JWKS
  (`.../protocol/openid-connect/certs`) via `PyJWKClient`:
  - RS256 signature, `exp`, issuer, and audience (accepts the client id in `aud` **or** `azp`).
  - JWKS is fetched once and cached by `kid`, so steady state is zero network — no per-request
    `/userinfo` round-trip.
  - `user_id` / `company_id` / `groups` come from the verified claims (company = first non-
    `capture` group, else the default).

Fit reads/writes are additionally gated by **company membership** (`vault.can_read_sbir`) in
prod, and keyed by the authenticated `user_id`, so a user can only ever see their own fit.

## Tests

- Backend: `app/tests/test_topic_intel.py` (shared vs per-user storage, legacy migration, fit
  isolation) and `app/tests/test_identity.py` (JWK signature / exp / issuer / audience).
- Frontend: `src/lib/evidence.test.ts`, `src/components/EvidenceReader.test.tsx`,
  `src/components/TopicScatter.test.tsx`, `src/lib/opportunity.test.ts`.
