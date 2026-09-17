# SCOUT

Anthracite AI's capture matcher: **drop your resume, qualified work comes to you.**

SCOUT ranks open **DoD SBIR/STTR** topics against your profile, then lets you optionally run a
**multi-agent LLM council** (Canari, Vien, Anthracite, Collier, Hewer, Flint, Davy) on the ones worth
a closer look. Pipeline, live proposal feedback, and debrief OCR stay local — **Ollama**
(`llama3.2:3b`) and **Docling**.

- **Frontend:** React + TypeScript + Vite + Axios (served by nginx)
- **Backend:** FastAPI + httpx + SQLModel (SQLite)
- **LLM:** host Ollama (`llama3.2:3b`, already on :11434)
- **OCR / doc parsing:** Docling (with python-docx / pypdf fallbacks)
- **Data source:** DSIP public API (`dodsbirsttr.mil`), proxied by the backend

The matcher does **not** run the council. Ranking is keyword overlap against DSIP search.
Deep-score is an explicit button.

---

## Quick start

```bash
cp .env.example .env          # tweak if you like
docker compose up --build     # minimal local: UI + API + disk vault, host Ollama
```

Then open **http://localhost:8080**. Leave it running — you should not need to
re-run compose to use the app.

Ken, Jake, and Matt are seeded in the **anthracite** org. The UI starts as Dev;
switch people at **Org → switch** or `/login`. Council and Flint results are
cached under `sbir/{topic}/{company}/users/{you}/` so a second look does not
re-run the LLM.

### Production overlay (Keycloak + SeaweedFS)

Not needed to prove the product locally. Same layout as CANARI `architecture/auth-and-storage.md`:

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```

- File ACL: `companies/anthracite/employees.txt`
- Federated SBIRs: `groups/anthracite/capture/sbir.txt` + each user's `sbir.txt`
- Group writing: `sbir/{id}/anthracite/shared/proposal.md`
- Private work: `sbir/{id}/anthracite/users/{ken|jake|matt}/`
- Keycloak: http://localhost:8081 (admin/admin) · passwords = usernames

Details: [`architecture/auth-and-storage.md`](architecture/auth-and-storage.md)

- Frontend: http://localhost:8080
- Backend API + docs: http://localhost:8000/docs
- Ollama: host process on http://127.0.0.1:11434 (not a SCOUT container)

### Keep it running

Containers use `restart: unless-stopped`. Docker starts on boot, so SCOUT comes
back after a reboot. A user systemd unit also runs `docker compose up -d` when
you log in.

```bash
# one-time (already enabled on this laptop)
systemctl --user enable --now scout.service

# open later — no compose needed if it is already up
xdg-open http://localhost:8080
# or search "SCOUT" in the app launcher
```

Do **not** `docker compose down` unless you intend to stop it. `Ctrl+C` in a
foreground `docker compose up` will also stop the stack; use `-d` instead.

### Hunt without looking

SCOUT seeds an **Anthracite capabilities** pack (VEIN / CANARI / DAVY / Core) if
no resume is on file, then ranks open DSIP topics on a timer (07:30 and 15:30,
plus a few minutes after login). New fits get a desktop notification. Digest:

`~/.local/share/scout/inbox.md`

The council is never auto-run — only the cheap ranker.

```bash
systemctl --user enable --now scout-scan.timer
```

### Pull the model (one time)

This machine already has `llama3.2:3b` on the host snap. That is the default. To use 8b later:

```bash
ollama pull llama3.1:8b
```

Then set `OLLAMA_MODEL=llama3.1:8b` in `.env` and recreate `scout-backend`.
Do **not** start a second Ollama on :11434 — the snap already owns that port.

> **GPU:** the host snap Ollama can use the RTX A1000 directly (no nvidia-container-toolkit
> required). `llama3.2:3b` fits the 4 GB card. `gpt-oss:20b` does not — leave it off.

---

## How it works

1. **Profile** — upload **ME** (your resume: tools you have used) separately from the
   company / product pack. Flint only sparks from ME.
2. **Inbox** — SCOUT extracts search terms, queries open/pre-release DSIP topics, and ranks
   them by overlap. This is the default home screen. **Flint this topic** is optional and
   does not run the rest of the council.
3. **Deep-score (optional)** — run the council on the top 5 ranked matches, or on a single
   card. Not automatic.
4. **Browse** — catalog search if you already know a topic.
5. **Pipeline** — move topics through the bid stages and record outcomes.
6. **Proposals** — draft with **live LLM feedback**; **Full review** also uses the topic + debriefs.
7. **Debriefs** — upload government feedback for lost bids; OCR + LLM turn it into reusable lessons.

### The agents (council only)

| Agent | Role | What it does |
|-------|------|--------------|
| **Canari** | Fit Scout / early-warning | Fast go/no-go signal + red flags & eligibility concerns |
| **Vien** | Technical Analyst | Feasibility + how your skills map to the required work |
| **Anthracite** | Business Developer | Customer need, competition, transition path, win probability |
| **Collier** | Teaming & Staffing | Roles and partners to cover gaps |
| **Hewer** | Lift & Adaptation | 0–10 effort to adapt what you already have |
| **Flint** | Creative toolwright | Unexpected approaches using only tools on the **ME** resume |
| **Davy** | Capture Strategist | Win themes, discriminators, TPOC questions, next actions |
| **Council** | Chair | Synthesizes a 0–100 fit score + GO / NO-GO recommendation |

---

## Configuration (`.env`)

| Var | Default | Notes |
|-----|---------|-------|
| `OLLAMA_BASE_URL` | `http://host.docker.internal:11434` | Host snap Ollama |
| `OLLAMA_MODEL` | `llama3.2:3b` | Model for extract + council |
| `OLLAMA_FALLBACK_MODEL` | `llama3.1:8b` | Used if 3b is missing |
| `DSIP_BASE_URL` | `https://www.dodsbirsttr.mil/topics/api/public` | Upstream API |
| `DSIP_USER_AGENT` | (browser UA) | Required — DSIP returns 403 without it |
| `USE_DOCLING` | `true` | Set `false` to skip heavy Docling and use light extractors |
| `BACKEND_PORT` | `8000` | |
| `FRONTEND_PORT` | `8080` | |

---

## Local dev (without Docker)

Backend:
```bash
cd backend
python -m venv .venv && . .venv/Scripts/activate   # Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
OLLAMA_BASE_URL=http://localhost:11434 uvicorn app.main:app --reload
```

Frontend:
```bash
cd frontend
npm install
npm run dev        # proxies /api -> http://localhost:8000
```

---

## Notes

- All processing is local; nothing is sent to third-party LLM services.
- The DSIP proxy only reads public topic data.
- Data (SQLite + uploads) lives in the `app_data` Docker volume; models in `ollama_models`.
