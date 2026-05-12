# SimuVerse

SimuVerse is a multi-agent social simulation platform built for research and teaching. Four AI agents interact inside a shared scenario — exchanging information, building trust, managing stress, and working toward a shared goal. You can watch the simulation play out automatically, step through it manually, or intervene in real time to steer agent behaviour.

## What it does

Agents have distinct personalities, memory, trust relationships, and stress levels that shift as they communicate. Each run is seeded and fully reproducible. Three scenario types are available:

- **Office** — a project team must share information to complete a proposal
- **Café** — a group decides on a restaurant by pooling what each member knows
- **Escape Room** — agents must combine clues to solve a puzzle chain

You can apply interventions mid-run (boost urgency, inject a mood, force a meeting, reveal information) and watch how the team dynamics respond. Every run is saved to history and can be replayed or exported.

---

## Requirements

- **Python 3.9 or higher**
- **pip** (comes with Python)
- A modern browser — Chrome or Safari recommended

The following Python packages are installed automatically via `requirements.txt`:

| Package | Version | Purpose |
|---|---|---|
| fastapi | 0.128.8 | Web framework for the REST API |
| uvicorn | 0.39.0 | ASGI server that runs the backend |
| websockets | 15.0.1 | WebSocket support for live simulation streaming |
| pydantic | 2.13.3 | Request/response data validation |
| mesa | 2.4.0 | Agent-based simulation engine |
| anyio | 4.12.1 | Async thread execution in API routes |
| vaderSentiment | 3.3.2 | Rule-based emotion analysis (fallback NLP) |
| numpy | 2.0.2 | Numerical operations and random seeding |

> **Optional:** `transformers` and `torch` can be installed for ML-based emotion classification (HuggingFace GoEmotions). The app works without them — it falls back to VADER automatically.

---

## Setup

**1. Clone or download the project**, then open a terminal in the project folder.

**2. Create the virtual environment and install dependencies:**

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

> On Windows use `.venv\Scripts\activate` instead of `source .venv/bin/activate`

---

## Running locally

You need **two terminals open at the same time**.

**Terminal 1 — Backend:**

```bash
cd backend
.venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8007 --reload
```

**Terminal 2 — Frontend:**

```bash
python3 serve.py
```

**Then open in your browser:**

```
http://localhost:5001
```

---

## How to use it

### 1. Setup page
Go to **Setup** from the home screen. Choose:
- **Scenario** — Office, Café, or Escape Room
- **Team style** — affects how agents behave (Smooth, Tension, Creative, or Pressure)
- **Mode** — Watch Mode or Live Interactive

### 2. Watch Mode
The simulation runs automatically on the dashboard. You can:
- Use **Prev / Next** to step through the run tick by tick
- Use **Play** to let it run at speed
- See the **Why This Happened** panel for explanations of each agent decision

### 3. Live Interactive Mode
You control the pace. You can:
- Press **Next Step** to advance the simulation one tick at a time
- Apply **interventions** mid-run:
  - **Boost Urgency / Ease Pressure** — change the stress environment
  - **Inject Mood** — type a feeling and inject it into the group
  - **Nudge Strategy** — push agents toward cooperation
  - **Force Meeting** — make two specific agents interact
  - **Reveal Info** — unlock a blocked piece of information
- When the run ends a summary modal appears with options to export or start a new run

### 4. History
All completed runs are saved automatically. Go to **History** to:
- Browse all past runs with their scenario, team, outcome, and metrics
- Replay any run step by step in the dashboard
- Delete runs you no longer need

### 5. Experiments
The **Experiments** page lets you run controlled batch simulations for comparison and analysis. You can:
- **Team comparison** — run the same scenario with different team styles and compare how trust, stress, friction, and progress differ across conditions
- **Scenario comparison** — fix the team and run different scenarios side by side to compare outcomes across environments
- **Seed reproducibility** — rerun the same conditions with identical starting seeds to test consistency
- Use repeatable run IDs (seeds) so every condition starts from the same point, ensuring a fair comparison
- View an automated results summary with metric breakdowns across all runs

This is useful for evaluating how team dynamics and agent behaviour change under different conditions in a reproducible, controlled way.

### 6. Exporting
At the end of a run click **Export Data** to download the full run as a JSON file — includes all agent states, metrics, events, and interventions.

---

## Tech stack

- **Backend:** Python, FastAPI, WebSockets
- **Frontend:** Vanilla HTML/CSS/JavaScript
- **Simulation:** Custom agent-based model with personality, memory, trust, and stress
- **NLP:** VADER sentiment analysis (optional HuggingFace emotion classifier)
