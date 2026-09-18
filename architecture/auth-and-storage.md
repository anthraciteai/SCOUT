# SCOUT Auth + Org Vault (Keycloak + SeaweedFS / S3)

Adds sign-in and a per-user / per-company SBIR library so Ken, Jake, and Matt
can share an org (mission, products, group writing) while each keeps private
drafts and cached agent runs.

## Components

- `scout-backend` (`:8000`) — matcher, council, **vault + auth**. One boto3 S3
  client talks to SeaweedFS locally and AWS S3 in the cloud.
- `seaweedfs` (`:8333`) — local S3-compatible object store (org compose). Disk
  under `/data/vault` is always the working copy.
- `keycloak` (`:8081`) — OIDC. Dev imports the `scout` realm on start.

## Object-storage layout (bucket `scout`)

```
companies/{company_id}/mission.txt
companies/{company_id}/products.md
companies/{company_id}/employees.txt              # derived roster (not the gate)
companies/{company_id}/employees/{user_id}        # GATE: employed. delete = quit
companies/{company_id}/tags.json

users/{user_id}/me.md                             # LLM resume blob
users/{user_id}/skills.txt                        # roster excerpt
users/{user_id}/meta.json                         # {companies} listing
users/{user_id}/companies/{company_id}            # reverse index; auth ignores it
users/{user_id}/sbir/{topic_id}                   # GATE: personal grant
users/{user_id}/resume/tags.json                  # pointer {sha}
users/{user_id}/resume/v/{sha}/tags.json          # frozen matcher pack

sbirs/{topic_id}/tags.json                        # GATE: solicitation tagged (not under a company)
blobs/{sha}.json.gz                               # immutable council / agent runs

groups/{company_id}/{group_id}/members.txt
groups/{company_id}/{group_id}/sbir/{topic_id}    # GATE: group grant

sbir/{topic_id}/{company_id}/shared/topic.json
sbir/{topic_id}/{company_id}/shared/council.json       # pointer {sha}
sbir/{topic_id}/{company_id}/shared/proposal.md
sbir/{topic_id}/{company_id}/shared/approaches/{user_id}.json
sbir/{topic_id}/{company_id}/shared/collab.json
sbir/{topic_id}/{company_id}/users/{user_id}/meta.json
sbir/{topic_id}/{company_id}/users/{user_id}/flint.json    # GATE: Flint ran (pointer)
sbir/{topic_id}/{company_id}/users/{user_id}/council.json  # GATE: council ran (pointer)
sbir/{topic_id}/{company_id}/users/{user_id}/draft.exists  # GATE: non-empty draft
sbir/{topic_id}/{company_id}/users/{user_id}/draft.md
sbir/{topic_id}/{company_id}/users/{user_id}/chat/{agent}.json
```

- **Login:** `companies/{company_id}/employees/{user_id}` must **exist**. The reverse
  index `users/{id}/companies/{cid}` answers “who I work for” and is **not** trusted
  for access — a quit deletes the employee file; leftover reverse files cannot let
  them back in. Login never re-hires.
- **SBIR access:** `users/{user_id}/sbir/{topic_id}` or
  `groups/{company}/{group}/sbir/{topic_id}` exists. First Flint / Council / Open
  desk writes those gates.
- **Cache:** `flint.json` / `council.json` **existing** means that LLM already ran
  (`force=true` to replace). The file is a `{sha, model, cached_at}` pointer.
  Bytes live once at `blobs/{sha}.json.gz`. Ken’s slot and `shared/council.json`
  can point at the same sha. SQLite stores the sha, not a third copy.
- **Working log:** after a structured run, you can talk to that agent. Flint
  proposes a spark; you can reject it ("license, we can't ship TAK — use MQTT
  instead") and the substitute is appended to `chat/{agent}.json`. Teammates
  do not see your private log.
- **Privacy:** teammates see *that* you have a draft / Flint run, not the
  private text. Shared proposal.md is the federated write surface. Overlap on
  the group desk uses **approach cards** (`shared/approaches/{user}.json`) —
  Flint spark titles, tools, and markdown headings — never `draft.md`.
- **Group desk:** its own sidebar tab (`/desk`), not Browse / topic content.
  A desk only exists for SBIRs in the company pipeline (tracked). Opening it
  is “we are looking at this bid”; overlap matching is for two+ writers.
- **Collab:** opening the desk set-diffs those cards (0 tokens). Ken ∩ Jake on
  the same technical take is flagged immediately. Collier only runs if the card
  checksums changed, and only sees the cards plus that report. Promote appends
  to `shared/proposal.md` with an If-Match sha so two saves do not clobber.

## Local (stub auth, disk vault)

Default `docker compose up` seeds Ken / Jake / Matt / Dev (password = username)
and `AUTH_DISABLED=true` so the UI auto-enters as Dev. Switch people at `/login`.

## Production overlay (Keycloak + SeaweedFS)

```
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```

- Keycloak admin: http://localhost:8081 (admin / admin)
- Realm `scout`, SPA client `scout-frontend`, users `ken` / `jake` / `matt`
- SeaweedFS S3 creds: access `scout`, secret `scout-secret-key`
- `AUTH_DISABLED=false` — password required; Keycloak password-grant is a fallback

### Auth stub (no Keycloak)

`AUTH_DISABLED=true` (default compose). Do not use in a shared deployment.

## Cloud (AWS S3 + managed Keycloak)

```
export AWS_ACCESS_KEY_ID=... AWS_SECRET_ACCESS_KEY=... AWS_REGION=us-west-2
export STORAGE_ENDPOINT= STORAGE_BUCKET=scout-prod
export KEYCLOAK_URL=https://auth.example.com KEYCLOAK_REALM=scout
```

Empty `STORAGE_ENDPOINT` => boto3 uses real AWS S3.

## API (Bearer-gated when AUTH_DISABLED=false)

- `GET /api/auth/status`, `POST /api/auth/login`, `GET /api/auth/me`
- `GET /api/org/company` · `PUT /api/org/company/mission|products`
- `GET /api/org/sbir` · `GET|POST /api/org/sbir/{id}` (workspace / grant)
- `PUT /api/org/sbir/{id}/shared/proposal.md` · `.../mine/draft.md`
- `GET /api/org/sbir/{id}/collab` · `POST .../collab/refresh` · `POST .../collab/promote`
- `GET /api/analysis/chat/{topic}/{agent}` · `POST /api/analysis/chat`
  (working log; recorded under `users/{you}/chat/{agent}.json`)
- Council / Flint honor the vault cache automatically

## Notes

Working-log diagram: [`agent-chat-log.png`](agent-chat-log.png).
Overlap sequence: [`collab-overlap.png`](collab-overlap.png).

- `employees.txt` / `sbir.txt` are read-modify-write; fine at capture-team scale.
- Group membership is also materialized from the Keycloak token (`groups` claim)
  on login. File ACL remains the source of truth for company access.
- Matcher ranking uses cached `sbirs/{id}/tags.json` plus company/resume tags;
  inbox is **score high-to-low**, not a cutoff — anyone can bid any topic.

Prefix layout is the index. `list_prefix("companies/{id}/")` is the org pack;
`users/{id}/resume/` is every ME version without walking SBIRs; `sbirs/{id}/`
is one extract per solicitation. Tags never live under
`sbir/{topic}/{company}/` — that tree is work product, not capability metadata.
