# Pages

Every screen in the UI, in the order they appear in the sidebar. Routes are defined in
`frontend/src/App.tsx`; each page is a file in `frontend/src/pages/`.

The sidebar groups them into **Find**, **Pursue**, and **Setup**.

---

## Find

### Inbox — `/` · `pages/Inbox.tsx`
The home screen. "Drop your resume. Qualified work comes to you." Extracts search terms from
your resume, queries open/pre-release DSIP topics, and **ranks them by overlap** (cheap, no
Council). Shows the match breakdown, an **Opportunity map** scatter (match vs Council fit, gold
ring = you already scored a fit), and per-topic cards that link into the Workspace.
- Calls: `MatchesApi` (scan/inbox), `ResumeApi`, `AnalysisApi` (any existing Council runs),
  `TrackerApi`, `TopicIntelApi.fitStatus`, `CatalogApi`.

### Browse — `/browse` · `pages/Browse.tsx`
Catalog search for when you already know what you're looking for. Strong matches come from the
last resume ranking and stay cached. Topic cards link to the detail/workspace views.
- Calls: `CatalogApi`, `TopicsApi`.

### Topic detail — `/topic/:id` · `pages/TopicDetail.tsx`
Read-only view of a single DSIP solicitation: full details, Q&A, and the official PDF/DOCX
download links. (The *working* view of a topic is the Workspace.)
- Calls: `TopicsApi.get` / `questions` / `downloadUrl`.

---

## Pursue

### Workspace — `/work/:id` · `pages/Workspace.tsx`
The single-topic command center. Tabs:
- **Summary** — LLM summary of the solicitation (problem, objective, phases, requirements).
- **Reader** — the raw OCR text with requirements color-linked to the sentences they came from
  (hover either side to highlight; see [`topic-intelligence.md`](topic-intelligence.md)).
- **Fit** — requirement-by-requirement scoring against *your* profile (meets/partial/gap +
  GO/NO-GO). Private to you; cached so re-opening costs no tokens.
- **Write** — save a draft into the group's shared `proposal.md`.
- **Source** — the raw text and PDF/DOCX links.
- Vanity URL `/work/:id/ME/:userId` renders the same page (fit identity still comes from the
  server-side token, never the URL).
- Calls: `TopicIntelApi` (text/summary/fit), `OrgApi` (shared proposal), `AnalysisApi`.

### Pipeline — `/tracker` · `pages/Tracker.tsx`
Your bid pipeline. Move tracked topics through stages and record win/loss outcomes. Lost bids
feed the Debriefs loop.
- Calls: `TrackerApi`, `GanttApi`.

### Council — `/analysis` · `pages/Analysis.tsx`
The **optional** deep multi-agent pass. Runs the roster (Canari, Vein, Anthracite, Collier,
Hewer, Flint, Davy) and a Chair that synthesizes a **0–100 fit + GO/NO-GO**. Never automatic —
you pick the topics. Results are cached in the vault so a second look doesn't re-run the LLM.
- Calls: `AnalysisApi`.

### Proposals — `/proposals` · `pages/Proposals.tsx`
Draft proposals with **live LLM feedback** as you write, and talk to individual personas
(Flint / Hewer / …) in a recorded working log. "Full review" also pulls in the topic + debriefs.
- Calls: `ProposalsApi`, `AnalysisApi` (chat).

### Team room — `/desk` · `/desk/:topicId` · `pages/GroupDesk.tsx`
Shared per-bid workspace for topics the company is actually bidding (must be tracked). Two+
writers get **overlap detection** on their approach cards (set-diff, 0 tokens; Collier only
runs if cards changed). Teammates see *that* you have a draft/Flint run, not the private text.
- Calls: `OrgApi` (sbir workspace, collab refresh/promote).

### Debriefs — `/debriefs` · `pages/Debriefs.tsx`
Upload government feedback for proposals that weren't selected. Docling OCR + the LLM turn it
into reusable lessons that later reviews can draw on.
- Calls: `DebriefsApi`.

---

## Setup

### Company — `/org` · `pages/Org.tsx`
The org pack: company **mission** and **products**. Shared by everyone in the company and used
as capability context in fit/council. Each product has a **build prompt** (what SBIR/STTR work
fits it) plus keywords; Scout folds these into matching so it finds topics per product — this is
how a new org tunes Scout to its own product lineup. Also where you manage people and switch
which seeded person you are.
- Calls: `OrgApi` (company mission; per-product build-prompts via `product-profiles`; roster).

### Profile — `/profile` · `pages/Profile.tsx`
Upload your resume and mark it **ME** (the tools *you* personally have used). Kept separate from
the company pack — Flint only sparks ideas from ME.
- Calls: `ResumeApi`, `OrgApi`.

### Settings — `/settings` · `pages/Settings.tsx`
Local model choice and the Council roster toggles.
- Calls: `SystemApi`.

---

## Auth gate

### Login — `/login` · `pages/Login.tsx`
Sign-in. Access is gated by `companies/<id>/employees/<you>` existing in the vault. In dev
(`AUTH_DISABLED=true`) the UI auto-enters as **Dev** and this page is only for switching people.
- Calls: `AuthApi` (status/login/me).
