# SBIR Scout

A self-hosted web app to **browse DoD SBIR/STTR topics**, run a **multi-agent LLM council**
(Canari, Vien, Anthracite, Davy) to decide which topics to bid, **track your pipeline**, get
**live proposal-writing feedback**, and **learn from debriefs** via OCR — all locally with
**Ollama (`gpt-oss:20b`)** and **Docling**.

- **Frontend:** React + TypeScript + Vite + Axios (served by nginx)
- **Backend:** FastAPI + httpx + SQLModel (SQLite)
- **LLM:** Ollama (`gpt-oss:20b`, configurable) running in-compose
- **OCR / doc parsing:** Docling (with python-docx / pypdf fallbacks)
- **Data source:** DSIP public API (`dodsbirsttr.mil`), proxied by the backend

---

## Quick start

```bash
cp .env.example .env          # tweak if you like
docker compose up --build
```

Then open **http://localhost:8080**.

- Frontend: http://localhost:8080
- Backend API + docs: http://localhost:8000/docs
- Ollama: http://localhost:11434

### Pull the model (one time)

`gpt-oss:20b` is large (~14 GB). Pull it into the compose Ollama once:

```bash
docker exec -it sbir-ollama ollama pull gpt-oss:20b
```

Or click **Pull** in the app under **Settings**. Until it finishes, the app automatically falls
back to `OLLAMA_FALLBACK_MODEL` (default `llama3.1:8b`). Change the model in `.env`
(`OLLAMA_MODEL`).

> GPU: the `ollama` service uses `gpus: all` by default (needs Docker Desktop + NVIDIA
> driver on Windows/WSL2, or nvidia-container-toolkit on Linux). Verify with
> `docker exec sbir-ollama nvidia-smi`. On a machine without an NVIDIA GPU, remove the
> `gpus: all` line from `docker-compose.yml` and Ollama will run on CPU.
> Note: `gpt-oss:20b` (~13 GB) is larger than a 12 GB card's VRAM, so Ollama splits
> layers across GPU+CPU (e.g. ~26% CPU / 74% GPU). It's still far faster than CPU-only.

---

## The agents

| Agent | Role | What it does |
|-------|------|--------------|
| **Canari** | Fit Scout / early-warning | Fast go/no-go signal + red flags & eligibility concerns |
| **Vien** | Technical Analyst | Feasibility + how your skills map to the required work |
| **Anthracite** | Business Developer | Customer need, competition, transition path, win probability |
| **Davy** | Capture Strategist | Win themes, discriminators, TPOC questions, next actions |
| **Council** | Chair | Synthesizes a 0–100 fit score + GO / NO-GO recommendation |

---

## Workflow

1. **Settings** — paste or upload your resume/capabilities (`.docx`/`.pdf` are OCR-extracted).
2. **Browse Topics** — search open/pre-release topics, select the ones you care about.
3. **Analysis** — run the council; get a fit score + GO/NO-GO with full agent breakdown.
4. **Tracker** — move topics through your bid pipeline and record outcomes.
5. **Proposals** — draft with **live LLM feedback**; **Full review** also uses the topic + debriefs.
6. **Debriefs** — upload government feedback for lost bids; OCR + LLM turn it into reusable lessons.

---

## Configuration (`.env`)

| Var | Default | Notes |
|-----|---------|-------|
| `OLLAMA_MODEL` | `gpt-oss:20b` | Model for all agents |
| `OLLAMA_FALLBACK_MODEL` | `llama3.1:8b` | Used until the main model is pulled |
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
