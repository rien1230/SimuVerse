<<<<<<< HEAD
SimuVerse is a small-group social simulation that explores how emotions and dialogue shape trust, conflict, and contagion. Four lightweight agents run on a seeded Mesa engine with personality, short/long-term memory, goals, and a simple mood model (valence–arousal). You can watch an automatic baseline or run an experiment by tweaking agent personalities. Short user inputs like “I feel ignored” are classified (GoEmotions) and injected into the world; agent dialogue is generated with a Concordia-style loop (goals + memory + context → ChatGPT) behind safety moderation. A live 2D viewer shows avatars, expressions, and colour-coded relationship ties as the story unfolds.

The project is built for reproducibility and evaluation: deterministic seeds, per-tick JSONL logs, exact replay, and clear metrics (polarisation, contagion speed, conflict rate) with simple ablations (LLM on/off, emotion on/off). Tech stack: Python (Mesa) core with a REST/WebSocket API, a React + Canvas viewer, and a thin SQLite/PostgreSQL layer for run metadata and artifact links. Ethics by design: consent banner, no PII in storage, ephemeral user text, and moderated outputs. Intended for teaching, coursework, and research demos where clarity, auditability, and repeatability matter.
=======
# Your project name here

## Information about this repository

This is the repository that you are going to use **individually** for developing your project. Please use the resources provided in the module to learn about **plagiarism** and how plagiarism awareness can foster your learning.

Regarding the use of this repository, once a feature (or part of it) is developed and **working** or parts of your system are integrated and **working**, define a commit and push it to the remote repository. You may find yourself making a commit after a productive hour of work (or even after 20 minutes!), for example. Choose commit message wisely and be concise.

Please choose the structure of the contents of this repository that suits the needs of your project but do indicate in this file where the main software artefacts are located.
>>>>>>> 24fc3283a7791a75e2ccbdc6dc0ef928ed9b7f83
