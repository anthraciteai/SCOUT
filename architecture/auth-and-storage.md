# SCOUT Auth + Org Vault (Keycloak + SeaweedFS / S3)

Adds sign-in and a per-user / per-company SBIR library so Ken, Jake, and Matt
can share an org (mission, products, group writing) while each keeps private
drafts and cached agent runs. Same shape as CANARI `library-api`.

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
companies/{company_id}/employees.txt          # login ACL

users/{user_id}/me.md                         # personal resume / tools
users/{user_id}/skills.txt
users/{user_id}/sbir.txt                      # topic ids this person can open
users/{user_id}/companies.txt
users/{user_id}/passwd                        # stub auth only

groups/{company_id}/{group_id}/members.txt
groups/{company_id}/{group_id}/sbir.txt       # federated list for the group

sbir/{topic_id}/{company_id}/shared/topic.json
sbir/{topic_id}/{company_id}/shared/council.json   # first cached council (org)
sbir/{topic_id}/{company_id}/shared/proposal.md    # group writing
sbir/{topic_id}/{company_id}/users/{user_id}/flint.json
sbir/{topic_id}/{company_id}/users/{user_id}/council.json
sbir/{topic_id}/{company_id}/users/{user_id}/draft.md   # private
```

- **Login:** a user may enter a company only if their `user_id` is in
  `companies/{company_id}/employees.txt`.
- **SBIR access:** topic id is in `users/{user_id}/sbir.txt` **or** a group
  `sbir.txt` they belong to. First Flint / Council / Open desk **grants** both
  the user file and `groups/{company}/capture/sbir.txt`.
- **Cache:** council and Flint JSON are keyed by user (and a shared copy for
  the org). Same topic + same person + same model → no second LLM call unless
  `force=true`.
- **Privacy:** teammates see *that* you have a draft / Flint run, not the
  private text. Shared proposal.md is the federated write surface.

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
- Council / Flint honor the vault cache automatically

## Notes

- `employees.txt` / `sbir.txt` are read-modify-write; fine at capture-team scale.
- Group membership is also materialized from the Keycloak token (`groups` claim)
  on login. File ACL remains the source of truth for company access.
- Matcher ranking is still cheap and uncached; only LLM council / Flint is cached.
