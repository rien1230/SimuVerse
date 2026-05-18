# SimuVerse

SimuVerse is a real-time multi-agent social simulation platform built to explore how personality, trust, memory, stress, and emotion influence team behaviour. Four AI agents interact inside a shared scenario, exchange information, respond to social pressure, and work toward a common goal.

The system supports automatic runs, manual step-by-step execution, live user interventions, deterministic replay, and controlled batch experiments. It was developed as a final-year software engineering project with a focus on explainability, reproducibility, and interactive simulation.

---

## Key Features

- Real-time multi-agent simulation with personality, trust, stress, memory, and emotion dynamics
- FastAPI backend with REST endpoints and WebSocket streaming for live simulation updates
- Three configurable scenarios: Office, Café, and Escape Room
- Four team styles: Smooth, Tension, Creative, and Pressure
- Live user interventions including mood injection, forced meetings, urgency changes, and information reveal
- Seeded deterministic runs for reproducible experiments and replay
- Run history, JSON export, and step-by-step replay
- Batch experiment runner for comparing team styles, scenarios, and seed consistency
- Optional HuggingFace GoEmotions classifier with VADER fallback

---

## Screenshots

### Setup — Choose your scenario, team style, and mode

<img width="437" height="248" alt="image" src="https://github.com/user-attachments/assets/752f1577-bc31-4f4f-85e9-9b3fa23ae348" />


### Live Simulation Dashboard — Watch mode with agent interactions and Why This Happened panel

<img width="468" height="266" alt="image" src="https://github.com/user-attachments/assets/7e5e18b7-1147-4b35-9be5-9e07185dfe84" />


### Live Interactive Mode — Agent states, simulation log, and intervention controls

<img width="468" height="266" alt="image" src="https://github.com/user-attachments/assets/67f40efc-73e3-441d-9773-95fa03b4e795" />

<img width="437" height="246" alt="image" src="https://github.com/user-attachments/assets/ebf3258a-d6b7-4431-bdfe-cdfe2b05f643" />

<img width="437" height="248" alt="image" src="https://github.com/user-attachments/assets/7bda9dbc-8e5a-4325-88d2-315bc23084d8" />

<img width="437" height="247" alt="image" src="https://github.com/user-attachments/assets/c44d9e8e-0e45-4f28-837d-90b13fb5d44a" />



### Run Summary — Metrics, progress timeline, and team analysis

<img width="468" height="264" alt="image" src="https://github.com/user-attachments/assets/1087cfa4-46ec-461d-bcb3-109dc8274947" />

<img width="468" height="266" alt="image" src="https://github.com/user-attachments/assets/d83648f9-1347-4835-b987-c8b741cf0ebe" />

<img width="277" height="409" alt="image" src="https://github.com/user-attachments/assets/b721b0a1-c15f-45bc-80d7-cfcb9a56c7b4" />



### Experiment Runner — Controlled batch comparisons across team styles and scenarios

<img width="437" height="284" alt="image" src="https://github.com/user-attachments/assets/0c7158ef-7e40-43f7-ba30-0474d246ec09" />

<img width="437" height="284" alt="image" src="https://github.com/user-attachments/assets/77742cc3-12be-46ac-853f-223740bb59f6" />

<img width="437" height="129" alt="image" src="https://github.com/user-attachments/assets/6084abf2-db9e-4043-9e08-3250ce7761b2" />

<img width="396" height="233" alt="image" src="https://github.com/user-attachments/assets/ec6b8ed3-fe7c-46c8-9bf9-c27589d2b96d" />

<img width="396" height="258" alt="image" src="https://github.com/user-attachments/assets/24d114df-196a-4426-acf1-e7e5f344a8b6" />



---

## System Architecture

SimuVerse is structured as a full-stack simulation system:

```
Frontend UI
HTML / CSS / JavaScript
        ↓
FastAPI Backend
REST API + WebSocket streaming
        ↓
Simulation Engine
Agent state, scenario logic, interventions, metrics
        ↓
Run History & Replay
JSON event logs, seeded runs, exports
```

The backend manages simulation state, agent decisions, interventions, metrics, and replay data. The frontend provides the live workspace, dashboard, setup flow, history view, and experiment comparison interface.

---

## Evaluation

SimuVerse was evaluated through controlled batch experiments comparing different team configurations under the same scenario and seed conditions.

The evaluation measured:

- Task progress and completion behaviour
- Average trust and stress levels across agents
- Dialogue patterns and blocker resolution
- Intervention effects on team dynamics

Controlled experiments showed statistically significant behavioural differences between team configurations (p = 0.0018), suggesting that team style and personality configuration meaningfully affected simulation outcomes.

The experiment runner also supports reproducibility checks by rerunning identical scenario, team, and seed combinations to verify consistent behaviour.

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

## Running Locally

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

## How to Use It

### 1. Setup Page
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
- **Team comparison** — run the same scenario with different team styles and compare trust, stress, friction, and progress
- **Scenario comparison** — fix the team and run different scenarios side by side
- **Seed reproducibility** — rerun the same conditions with identical seeds to test consistency
- View an automated results summary with metric breakdowns across all runs

### 6. Exporting
At the end of a run click **Export Data** to download the full run as a JSON file — includes all agent states, metrics, events, and interventions.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python, FastAPI, WebSockets |
| Frontend | Vanilla HTML, CSS, JavaScript |
| Simulation | Custom agent-based model (Mesa) |
| NLP | VADER sentiment analysis + optional HuggingFace GoEmotions |
| Data | JSON event logs, seeded reproducible runs |
