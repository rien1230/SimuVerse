# SimuVerse

SimuVerse is a real-time multi-agent social simulation platform built to explore how personality, trust, memory, stress, and emotion influence team behaviour. Four AI agents interact inside shared scenarios, exchange information, respond to social pressure, and work toward a common goal.

Developed as a final-year software engineering project with a focus on explainability, reproducibility, and interactive simulation.

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

## Key Features

- Real-time multi-agent simulation with personality, trust, stress, memory, and emotion dynamics
- FastAPI backend with REST endpoints and WebSocket streaming for live simulation updates
- Three configurable scenarios: Office, Café, and Escape Room
- Four team styles: Smooth, Tension, Creative, and Pressure
- Live user interventions — mood injection, forced meetings, urgency changes, and information reveal
- Seeded deterministic runs for reproducible experiments and replay
- Run history, JSON export, and step-by-step replay
- Batch experiment runner for comparing team styles, scenarios, and seed consistency
- Optional HuggingFace GoEmotions classifier with VADER fallback

---

## System Architecture

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

Metrics measured across runs:

- Task progress and completion behaviour
- Average trust and stress levels across agents
- Dialogue patterns and blocker resolution
- Intervention effects on team dynamics
- Reproducibility across repeated seeded runs

Controlled experiments showed statistically significant behavioural differences between team configurations (p = 0.0018), suggesting that team style and personality configuration meaningfully affected simulation outcomes.

---

## Setup

**Requirements:** Python 3.9+, pip, and a modern browser (Chrome or Safari recommended).

**1. Clone the repo, then install dependencies:**

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

> Optional: install `transformers` and `torch` for HuggingFace emotion classification. The app falls back to VADER automatically without them.

---

## Running Locally

Open **two terminals** at the same time.

**Terminal 1 — Backend:**
```bash
cd backend
.venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8007 --reload
```

**Terminal 2 — Frontend:**
```bash
python3 serve.py
```

Then open `http://localhost:5001` in your browser.

---

## How to Use It

**Setup** — choose a scenario (Office, Café, or Escape Room), a team style, and a mode (Watch or Live Interactive).

**Watch Mode** — the simulation runs automatically. Step through tick by tick, or hit Play. The *Why This Happened* panel explains each agent decision.

**Live Interactive Mode** — you control the pace. Apply interventions mid-run: boost urgency, inject a mood, force a meeting between two agents, or reveal blocked information.

**History** — all runs are saved automatically. Browse, replay, or export any past run.

**Experiments** — run controlled batch simulations. Compare team styles, scenarios, or seed consistency. View automated metric breakdowns across all conditions.

**Export** — download any completed run as a full JSON file including agent states, metrics, events, and interventions.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python, FastAPI, WebSockets |
| Frontend | Vanilla HTML, CSS, JavaScript |
| Simulation | Custom agent-based model (Mesa) |
| NLP | VADER + optional HuggingFace GoEmotions |
| Data | JSON event logs, seeded reproducible runs |

---

## Dependencies

| Package | Version | Purpose |
|---|---|---|
| fastapi | 0.128.8 | Web framework for the REST API |
| uvicorn | 0.39.0 | ASGI server |
| websockets | 15.0.1 | WebSocket support |
| pydantic | 2.13.3 | Data validation |
| mesa | 2.4.0 | Agent-based simulation engine |
| anyio | 4.12.1 | Async thread execution |
| vaderSentiment | 3.3.2 | Rule-based emotion analysis |
| numpy | 2.0.2 | Numerical operations and seeding |
