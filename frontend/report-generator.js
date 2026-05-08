/**
 * SimuVerse Report Generator
 * Produces a downloadable PDF from a structured run-data payload.
 *
 * Usage:
 *   window.SimuVerseReport.generate(payload)
 *
 * The payload shape is identical to what buildPdfPayload() / buildInteractionPdfPayload()
 * already return. This module replaces the old jsPDF drawing approach with a clean
 * HTML→PDF pipeline powered by html2pdf.js (html2canvas + jsPDF bundle, CDN loaded
 * lazily on first use).
 *
 * No DOM capture of the live UI. No window.print(). Off-screen div → downloaded file.
 * File name: SimuVerse_Run_<run_id>.pdf
 */

(function () {
  "use strict";

  /* ── html2pdf.js CDN (bundled, includes html2canvas + jsPDF) ── */
  const HTML2PDF_CDN =
    "https://cdnjs.cloudflare.com/ajax/libs/html2pdf.js/0.10.1/html2pdf.bundle.min.js";

  let _html2pdfLoaded = false;
  let _html2pdfLoading = null;

  function loadHtml2Pdf() {
    if (_html2pdfLoaded && typeof window.html2pdf === "function") {
      return Promise.resolve();
    }
    if (_html2pdfLoading) return _html2pdfLoading;

    _html2pdfLoading = new Promise((resolve, reject) => {
      const script = document.createElement("script");
      script.src = HTML2PDF_CDN;
      script.onload = () => {
        _html2pdfLoaded = true;
        _html2pdfLoading = null;
        resolve();
      };
      script.onerror = () => {
        _html2pdfLoading = null;
        reject(new Error("Failed to load html2pdf.js from CDN. Check your internet connection."));
      };
      document.head.appendChild(script);
    });
    return _html2pdfLoading;
  }

  /* ── Helpers ─────────────────────────────────────────────────── */

  function esc(v) {
    return String(v == null ? "" : v)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function pct(fraction) {
    const n = Number(fraction || 0);
    const p = n <= 1 ? n * 100 : n;
    return Math.round(p) + "%";
  }

  function fmt2(v) {
    const n = Number(v || 0);
    return isNaN(n) ? "—" : n.toFixed(2);
  }

  function fmtNum(v) {
    const n = Number(v);
    return isNaN(n) || v == null ? "—" : String(n);
  }

  /**
   * Collapse duplicate intervention labels.
   * [{label:"Inject Tension"}, {label:"Inject Tension"}, {label:"Ease Pressure"}]
   * → [{label:"Inject Tension", count:2, ...}, {label:"Ease Pressure", count:1, ...}]
   */
  function collapseInterventions(interventions) {
    const seen = new Map();
    for (const iv of interventions) {
      const key = String(iv.label || iv.type || "Intervention").trim();
      if (!seen.has(key)) {
        seen.set(key, { ...iv, label: key, count: 1 });
      } else {
        seen.get(key).count++;
      }
    }
    return Array.from(seen.values());
  }

  function verdictBadge(verdict) {
    const v = String(verdict || "").toLowerCase();
    if (v === "effective" || v === "positive") {
      return `<span style="background:#d1fae5;color:#065f46;padding:1px 7px;border-radius:99px;font-size:10px;font-weight:700;">Effective</span>`;
    }
    if (v === "backfired" || v === "negative") {
      return `<span style="background:#fee2e2;color:#991b1b;padding:1px 7px;border-radius:99px;font-size:10px;font-weight:700;">Backfired</span>`;
    }
    if (v === "neutral") {
      return `<span style="background:#f3f4f6;color:#374151;padding:1px 7px;border-radius:99px;font-size:10px;font-weight:700;">Neutral</span>`;
    }
    return "";
  }

  function isSuccess(outcome) {
    return /success|accepted|reached|escaped|completed/i.test(String(outcome || ""));
  }

  function normalizeMode(mode) {
    const m = String(mode || "").toLowerCase().trim();
    if (m === "step" || m === "auto" || m === "watch") return "Watch Mode";
    if (m === "watch_replay") return "Watch Mode Replay";
    if (m === "interactive_replay" || m === "live interactive replay") return "Live Interactive Replay";
    if (m === "live" || m === "live_interactive" || m === "live interaction") return "Live Interaction";
    return mode || "Unknown";
  }

  /* ── Color palette (matching SimuVerse brand) ────────────────── */
  const C = {
    navy:    "#112033",
    teal:    "#1f8f83",
    amber:   "#b97418",
    red:     "#c84a4a",
    blue:    "#2a78c5",
    muted:   "#617387",
    subtle:  "#8ea4b8",
    border:  "#d8e4ef",
    bg:      "#f4f7fb",
    white:   "#ffffff",
    success: "#065f46",
    successBg: "#d1fae5",
    failBg: "#fee2e2",
    failText: "#991b1b",
  };

  /* ── CSS for the off-screen report container ─────────────────── */
  function reportCss() {
    return `
      <style>
        @import url('https://fonts.googleapis.com/css2?family=Manrope:wght@400;500;600;700;800&display=swap');

        .svr {
          font-family: 'Manrope', 'Segoe UI', Arial, sans-serif;
          font-size: 11px;
          color: ${C.navy};
          background: ${C.white};
          width: 794px;
          box-sizing: border-box;
          line-height: 1.55;
        }
        .svr * { box-sizing: border-box; }

        /* ── Page break control ── */
        .svr-page {
          padding: 36px 40px 28px;
          page-break-after: always;
          break-after: page;
        }
        .svr-page:last-child {
          page-break-after: avoid;
          break-after: avoid;
        }

        /* ── Cover ── */
        .svr-cover {
          min-height: 1020px;
          display: flex;
          flex-direction: column;
          justify-content: center;
          background: ${C.navy};
          color: ${C.white};
          padding: 60px 56px;
        }
        .svr-cover-brand {
          font-size: 13px;
          font-weight: 800;
          letter-spacing: 0.15em;
          text-transform: uppercase;
          color: ${C.teal};
          margin-bottom: 32px;
        }
        .svr-cover-label {
          font-size: 11px;
          font-weight: 600;
          letter-spacing: 0.12em;
          text-transform: uppercase;
          color: rgba(255,255,255,0.45);
          margin-bottom: 10px;
        }
        .svr-cover-title {
          font-size: 36px;
          font-weight: 800;
          color: ${C.white};
          line-height: 1.15;
          margin-bottom: 12px;
        }
        .svr-cover-scenario {
          font-size: 20px;
          font-weight: 600;
          color: rgba(255,255,255,0.72);
          margin-bottom: 48px;
        }
        .svr-cover-meta {
          display: grid;
          grid-template-columns: 1fr 1fr;
          gap: 16px 32px;
          margin-top: 0;
        }
        .svr-cover-kv {
          border-left: 2px solid ${C.teal};
          padding-left: 12px;
        }
        .svr-cover-kv-label {
          font-size: 9px;
          font-weight: 700;
          letter-spacing: 0.12em;
          text-transform: uppercase;
          color: rgba(255,255,255,0.4);
          margin-bottom: 3px;
        }
        .svr-cover-kv-val {
          font-size: 13px;
          font-weight: 700;
          color: ${C.white};
        }
        .svr-cover-outcome {
          margin-top: 40px;
          padding: 18px 20px;
          border-radius: 10px;
          font-size: 15px;
          font-weight: 700;
        }
        .svr-cover-outcome.success {
          background: ${C.successBg};
          color: ${C.success};
        }
        .svr-cover-outcome.fail {
          background: rgba(200,74,74,0.18);
          color: #f8a0a0;
        }
        .svr-cover-footer {
          margin-top: auto;
          padding-top: 48px;
          font-size: 9px;
          color: rgba(255,255,255,0.3);
          letter-spacing: 0.06em;
        }

        /* ── Section headings ── */
        .svr-section-title {
          font-size: 9px;
          font-weight: 800;
          letter-spacing: 0.13em;
          text-transform: uppercase;
          color: ${C.muted};
          margin-bottom: 16px;
          padding-bottom: 8px;
          border-bottom: 1.5px solid ${C.border};
        }
        .svr-h2 {
          font-size: 17px;
          font-weight: 800;
          color: ${C.navy};
          margin: 0 0 6px;
        }
        .svr-page-intro {
          font-size: 10.5px;
          color: ${C.muted};
          margin-bottom: 24px;
          font-weight: 500;
        }

        /* ── Key metric strip ── */
        .svr-metric-strip {
          display: grid;
          grid-template-columns: repeat(4, 1fr);
          gap: 12px;
          margin-bottom: 24px;
        }
        .svr-metric-card {
          background: ${C.bg};
          border: 1px solid ${C.border};
          border-radius: 8px;
          padding: 12px 14px;
        }
        .svr-metric-label {
          font-size: 8.5px;
          font-weight: 700;
          letter-spacing: 0.1em;
          text-transform: uppercase;
          color: ${C.muted};
          margin-bottom: 4px;
        }
        .svr-metric-value {
          font-size: 20px;
          font-weight: 800;
          color: ${C.navy};
        }
        .svr-metric-sub {
          font-size: 9px;
          color: ${C.subtle};
          margin-top: 2px;
        }

        /* ── KV table ── */
        .svr-kv-table {
          width: 100%;
          border-collapse: collapse;
          margin-bottom: 22px;
          font-size: 10.5px;
        }
        .svr-kv-table tr {
          border-bottom: 1px solid ${C.border};
        }
        .svr-kv-table tr:last-child {
          border-bottom: none;
        }
        .svr-kv-table td {
          padding: 7px 4px;
          vertical-align: top;
        }
        .svr-kv-table td:first-child {
          font-weight: 700;
          color: ${C.muted};
          width: 38%;
          font-size: 9.5px;
          text-transform: uppercase;
          letter-spacing: 0.06em;
          padding-right: 12px;
        }
        .svr-kv-table td:last-child {
          color: ${C.navy};
          font-weight: 600;
        }

        /* ── Agent cards ── */
        .svr-agent-grid {
          display: grid;
          grid-template-columns: repeat(4, 1fr);
          gap: 10px;
          margin-bottom: 22px;
        }
        .svr-agent-card {
          border: 1px solid ${C.border};
          border-radius: 8px;
          padding: 12px 10px;
          background: ${C.bg};
        }
        .svr-agent-id {
          font-size: 11px;
          font-weight: 800;
          color: ${C.navy};
          margin-bottom: 3px;
        }
        .svr-agent-role {
          font-size: 9.5px;
          font-weight: 600;
          color: ${C.teal};
          margin-bottom: 6px;
          text-transform: uppercase;
          letter-spacing: 0.06em;
        }
        .svr-agent-row {
          font-size: 9.5px;
          color: ${C.muted};
          margin-bottom: 2px;
        }
        .svr-agent-row strong {
          color: ${C.navy};
          font-weight: 600;
        }

        /* ── Task list ── */
        .svr-task-list {
          list-style: none;
          padding: 0;
          margin: 0 0 22px;
        }
        .svr-task-item {
          display: flex;
          align-items: center;
          gap: 10px;
          padding: 8px 12px;
          border-radius: 6px;
          margin-bottom: 5px;
          font-size: 10.5px;
          font-weight: 600;
        }
        .svr-task-item.done {
          background: ${C.successBg};
          color: ${C.success};
        }
        .svr-task-item.pending {
          background: #fef3c7;
          color: #92400e;
        }
        .svr-task-icon {
          font-size: 13px;
          flex-shrink: 0;
        }

        /* ── Outcome summary box ── */
        .svr-outcome-box {
          border-radius: 10px;
          padding: 16px 18px;
          font-size: 11px;
          line-height: 1.6;
          margin-bottom: 22px;
          font-weight: 500;
        }
        .svr-outcome-box.success {
          background: ${C.successBg};
          color: ${C.success};
          border-left: 4px solid #10b981;
        }
        .svr-outcome-box.fail {
          background: ${C.failBg};
          color: ${C.failText};
          border-left: 4px solid ${C.red};
        }
        .svr-outcome-box.neutral {
          background: ${C.bg};
          color: ${C.navy};
          border-left: 4px solid ${C.border};
        }

        /* ── Intervention table ── */
        .svr-iv-table {
          width: 100%;
          border-collapse: collapse;
          margin-bottom: 22px;
          font-size: 10px;
        }
        .svr-iv-table thead tr {
          background: ${C.bg};
        }
        .svr-iv-table th {
          text-align: left;
          font-size: 8.5px;
          font-weight: 800;
          letter-spacing: 0.1em;
          text-transform: uppercase;
          color: ${C.muted};
          padding: 7px 10px;
          border-bottom: 1.5px solid ${C.border};
        }
        .svr-iv-table td {
          padding: 7px 10px;
          border-bottom: 1px solid ${C.border};
          vertical-align: middle;
        }
        .svr-iv-table td:last-child {
          text-align: right;
        }
        .svr-iv-table tr:last-child td {
          border-bottom: none;
        }

        /* ── Metrics history table ── */
        .svr-metrics-table {
          width: 100%;
          border-collapse: collapse;
          font-size: 9.5px;
          margin-bottom: 22px;
        }
        .svr-metrics-table th {
          text-align: right;
          font-size: 8px;
          font-weight: 800;
          letter-spacing: 0.1em;
          text-transform: uppercase;
          color: ${C.muted};
          padding: 5px 8px;
          border-bottom: 1.5px solid ${C.border};
        }
        .svr-metrics-table th:first-child { text-align: left; }
        .svr-metrics-table td {
          text-align: right;
          padding: 5px 8px;
          border-bottom: 1px solid ${C.border};
          color: ${C.navy};
          font-weight: 500;
        }
        .svr-metrics-table td:first-child {
          text-align: left;
          font-weight: 700;
          color: ${C.muted};
        }
        .svr-metrics-table tr:nth-child(even) td {
          background: ${C.bg};
        }

        /* ── Timeline / appendix ── */
        .svr-timeline-entry {
          padding: 10px 12px;
          border-left: 3px solid ${C.border};
          margin-bottom: 8px;
          border-radius: 0 6px 6px 0;
          background: ${C.bg};
          page-break-inside: avoid;
          break-inside: avoid;
        }
        .svr-timeline-entry.intervention {
          border-left-color: ${C.amber};
          background: #fffbeb;
        }
        .svr-tl-meta {
          font-size: 9px;
          font-weight: 700;
          color: ${C.muted};
          letter-spacing: 0.06em;
          text-transform: uppercase;
          margin-bottom: 3px;
        }
        .svr-tl-title {
          font-size: 10.5px;
          font-weight: 700;
          color: ${C.navy};
          margin-bottom: 3px;
        }
        .svr-tl-summary {
          font-size: 10px;
          color: ${C.muted};
          font-weight: 500;
        }

        /* ── Two-column layout helper ── */
        .svr-two-col {
          display: grid;
          grid-template-columns: 1fr 1fr;
          gap: 20px;
          margin-bottom: 22px;
        }

        /* ── Progress bar ── */
        .svr-progress-bar-wrap {
          background: ${C.border};
          border-radius: 99px;
          height: 6px;
          margin-top: 6px;
          overflow: hidden;
        }
        .svr-progress-bar-fill {
          height: 6px;
          border-radius: 99px;
          background: ${C.teal};
        }

        /* ── No-data note ── */
        .svr-empty {
          font-size: 10px;
          color: ${C.subtle};
          font-style: italic;
          padding: 10px 0;
        }

        /* ── Page footer (repeats on each page via sticky positioning workaround) ── */
        .svr-page-footer {
          margin-top: 24px;
          padding-top: 10px;
          border-top: 1px solid ${C.border};
          font-size: 8.5px;
          color: ${C.subtle};
          display: flex;
          justify-content: space-between;
          letter-spacing: 0.04em;
        }
      </style>
    `;
  }

  /* ── Page builders ───────────────────────────────────────────── */

  function buildCoverPage(d) {
    const outcomeClass = isSuccess(d.outcome) ? "success" : "fail";
    const meta = [
      ["Scenario",    d.scenario?.label || "—"],
      ["Team",        d.team?.label     || "—"],
      ["Mode",        normalizeMode(d.mode)],
      ["Run ID",      d.runId           || "—"],
    ];
    const metaHtml = meta.map(([k, v]) => `
      <div class="svr-cover-kv">
        <div class="svr-cover-kv-label">${esc(k)}</div>
        <div class="svr-cover-kv-val">${esc(v)}</div>
      </div>`).join("");

    return `
      <div class="svr-cover svr-page">
        <div class="svr-cover-brand">SimuVerse</div>
        <div class="svr-cover-label">Simulation Report</div>
        <div class="svr-cover-title">${esc(d.scenario?.label || "Simulation")}</div>
        <div class="svr-cover-scenario">${esc(normalizeMode(d.mode))} · ${esc(d.team?.label || "")}</div>

        <div class="svr-cover-meta">${metaHtml}</div>

        <div class="svr-cover-outcome ${outcomeClass}">
          Outcome: ${esc(d.outcome || "Unknown")}
        </div>

        <div class="svr-cover-footer">
          Exported ${esc(d.exportedAt || "")} &nbsp;·&nbsp; Seed ${esc(String(d.seed ?? "—"))}
        </div>
      </div>`;
  }

  function buildConfigAgentsPage(d) {
    const progressFraction = Number(d.finalMetrics?.progress || 0);
    const progressNorm = progressFraction <= 1 ? progressFraction : progressFraction / 100;
    const progressPct = Math.round(progressNorm * 100);
    const progressBarW = Math.max(0, Math.min(100, progressPct));

    const cfgRows = [
      ["Scenario",      d.scenario?.label   || "—"],
      ["Team preset",   d.team?.label       || "—"],
      ["Experience",    normalizeMode(d.mode)],
      ["Total steps",   fmtNum(d.totalSteps)],
      ["Seed",          String(d.seed ?? "—")],
      ["Outcome",       d.outcome           || "—"],
    ];

    const cfgHtml = cfgRows.map(([k, v]) => `
      <tr>
        <td>${esc(k)}</td>
        <td>${esc(v)}</td>
      </tr>`).join("");

    /* Final metrics strip */
    const fm = d.finalMetrics || {};
    const metricsStripHtml = `
      <div class="svr-metric-strip">
        <div class="svr-metric-card">
          <div class="svr-metric-label">Progress</div>
          <div class="svr-metric-value">${progressPct}%</div>
          <div class="svr-progress-bar-wrap">
            <div class="svr-progress-bar-fill" style="width:${progressBarW}%"></div>
          </div>
        </div>
        <div class="svr-metric-card">
          <div class="svr-metric-label">Team Trust</div>
          <div class="svr-metric-value">${fmt2(fm.trust)}</div>
          <div class="svr-metric-sub">Final value</div>
        </div>
        <div class="svr-metric-card">
          <div class="svr-metric-label">Team Stress</div>
          <div class="svr-metric-value">${fmt2(fm.stress)}</div>
          <div class="svr-metric-sub">Final value</div>
        </div>
        <div class="svr-metric-card">
          <div class="svr-metric-label">Friction</div>
          <div class="svr-metric-value">${fmt2(fm.conflict)}</div>
          <div class="svr-metric-sub">Final value</div>
        </div>
      </div>`;

    /* Agent cards */
    const agents = Array.isArray(d.agents) ? d.agents : [];
    const agentCardsHtml = agents.length
      ? agents.map((a) => {
          const personality = String(a.personality || a.strategy || "").replace(/_/g, " ")
            .replace(/\b\w/g, (c) => c.toUpperCase());
          const stress = a.finalStress != null ? fmt2(a.finalStress) : "—";
          const holds = a.holds || "—";
          return `
            <div class="svr-agent-card">
              <div class="svr-agent-id">${esc(a.id || "Agent")}</div>
              <div class="svr-agent-role">${esc(a.role || "Agent")}</div>
              ${personality ? `<div class="svr-agent-row"><strong>Style:</strong> ${esc(personality)}</div>` : ""}
              <div class="svr-agent-row"><strong>Holds:</strong> ${esc(holds)}</div>
              <div class="svr-agent-row"><strong>Final stress:</strong> ${esc(stress)}</div>
            </div>`;
        }).join("")
      : `<div class="svr-empty">No agent data recorded.</div>`;

    return `
      <div class="svr-page">
        <div class="svr-section-title">Run Overview</div>
        <h2 class="svr-h2">Configuration &amp; Results</h2>
        <p class="svr-page-intro">Key parameters for this simulation run and final outcome metrics.</p>

        ${metricsStripHtml}

        <div class="svr-two-col">
          <div>
            <div class="svr-section-title">Run Details</div>
            <table class="svr-kv-table">
              <tbody>${cfgHtml}</tbody>
            </table>
          </div>
          <div>
            <div class="svr-section-title">Outcome summary</div>
            <div class="svr-outcome-box ${isSuccess(d.outcome) ? "success" : "neutral"}">
              ${esc(d.outcomeSummary || d.outcome || "Run complete.")}
            </div>
          </div>
        </div>

        <div class="svr-section-title">Agent Overview</div>
        <div class="svr-agent-grid">
          ${agentCardsHtml}
        </div>

        <div class="svr-page-footer">
          <span>SimuVerse · Run ${esc(d.runId || "—")}</span>
          <span>Configuration &amp; Agents</span>
        </div>
      </div>`;
  }

  function buildMetricsPage(d) {
    const history = Array.isArray(d.metricsHistory) ? d.metricsHistory : [];

    /* Sample at most 25 rows to keep the table readable */
    let rows = history;
    if (rows.length > 25) {
      const step = Math.floor(rows.length / 25);
      rows = rows.filter((_, i) => i % step === 0);
      /* Always include first and last */
      if (rows[rows.length - 1] !== history[history.length - 1]) {
        rows.push(history[history.length - 1]);
      }
    }

    const tableHtml = rows.length
      ? `<table class="svr-metrics-table">
          <thead>
            <tr>
              <th>Step</th>
              <th>Progress</th>
              <th>Trust</th>
              <th>Stress</th>
              <th>Conflict</th>
              <th>Cohesion</th>
            </tr>
          </thead>
          <tbody>
            ${rows.map((m) => {
              const prog = Number(m.progress || 0);
              const normProg = prog <= 1 ? prog : prog / 100;
              return `<tr>
                <td>Step ${esc(String(m.tick ?? "—"))}</td>
                <td>${Math.round(normProg * 100)}%</td>
                <td>${fmt2(m.trust)}</td>
                <td>${fmt2(m.stress)}</td>
                <td>${fmt2(m.conflict)}</td>
                <td>${fmt2(m.cohesion)}</td>
              </tr>`;
            }).join("")}
          </tbody>
        </table>`
      : `<div class="svr-empty">No per-step metric history recorded for this run.</div>`;

    /* Task progress list */
    const tasks = Array.isArray(d.tasks) ? d.tasks : [];
    const doneCount = tasks.filter((t) => t.done).length;
    const taskListHtml = tasks.length
      ? `<ul class="svr-task-list">
          ${tasks.map((t) => `
            <li class="svr-task-item ${t.done ? "done" : "pending"}">
              <span class="svr-task-icon">${t.done ? "✓" : "○"}</span>
              <span>${esc(t.label || "Task")}</span>
            </li>`).join("")}
        </ul>`
      : `<div class="svr-empty">No task data recorded.</div>`;

    return `
      <div class="svr-page">
        <div class="svr-section-title">Metrics</div>
        <h2 class="svr-h2">Metric History</h2>
        <p class="svr-page-intro">
          Per-step values for trust, stress, conflict, and progress across the ${esc(String(d.totalSteps || 0))}-step run.
          ${rows.length < history.length ? `(Sampled ${rows.length} of ${history.length} steps for readability.)` : ""}
        </p>

        ${tableHtml}

        <div class="svr-section-title">Task Progress</div>
        <p class="svr-page-intro">
          ${doneCount} of ${tasks.length} task${tasks.length !== 1 ? "s" : ""} completed.
        </p>
        ${taskListHtml}

        <div class="svr-page-footer">
          <span>SimuVerse · Run ${esc(d.runId || "—")}</span>
          <span>Metrics &amp; Tasks</span>
        </div>
      </div>`;
  }

  function buildInterventionsPage(d) {
    const rawIvs = Array.isArray(d.interventions) ? d.interventions : [];
    const collapsed = collapseInterventions(rawIvs);

    /* Per-occurrence table (deduplicated but with count shown) */
    const tableHtml = collapsed.length
      ? `<table class="svr-iv-table">
          <thead>
            <tr>
              <th>Intervention</th>
              <th>Count</th>
              <th>Stress Δ</th>
              <th>Trust Δ</th>
              <th>Verdict</th>
            </tr>
          </thead>
          <tbody>
            ${collapsed.map((iv) => {
              const labelDisplay = iv.count > 1 ? `${esc(iv.label)} ×${iv.count}` : esc(iv.label);
              const stressChange = iv.stressChange != null ? (iv.stressChange > 0 ? "+" : "") + Number(iv.stressChange).toFixed(3) : "—";
              const trustChange  = iv.trustChange  != null ? (iv.trustChange  > 0 ? "+" : "") + Number(iv.trustChange ).toFixed(3) : "—";
              return `<tr>
                <td>${labelDisplay}</td>
                <td>${iv.count}</td>
                <td>${esc(stressChange)}</td>
                <td>${esc(trustChange)}</td>
                <td>${verdictBadge(iv.verdict)}</td>
              </tr>`;
            }).join("")}
          </tbody>
        </table>`
      : `<div class="svr-empty">No user interventions were applied during this run — it ran fully autonomously.</div>`;

    /* Full chronological list */
    const chronoHtml = rawIvs.length
      ? `<div class="svr-section-title" style="margin-top:22px;">Chronological Order</div>
         ${rawIvs.map((iv) => {
           const stressStr = iv.stressChange != null
             ? `Stress ${iv.stressChange > 0 ? "+" : ""}${Number(iv.stressChange).toFixed(3)}`
             : "";
           const trustStr = iv.trustChange != null
             ? `Trust ${iv.trustChange > 0 ? "+" : ""}${Number(iv.trustChange).toFixed(3)}`
             : "";
           const delta = [stressStr, trustStr].filter(Boolean).join(" · ");
           return `
             <div class="svr-timeline-entry intervention">
               <div class="svr-tl-meta">Step ${esc(String(iv.tick || "—"))} · Intervention</div>
               <div class="svr-tl-title">${esc(iv.label || "Intervention")}</div>
               ${delta ? `<div class="svr-tl-summary">${esc(delta)} ${verdictBadge(iv.verdict)}</div>` : ""}
             </div>`;
         }).join("")}`
      : "";

    return `
      <div class="svr-page">
        <div class="svr-section-title">Interventions</div>
        <h2 class="svr-h2">Intervention Summary</h2>
        <p class="svr-page-intro">
          ${rawIvs.length
            ? `${rawIvs.length} intervention${rawIvs.length !== 1 ? "s" : ""} applied across ${collapsed.length} distinct type${collapsed.length !== 1 ? "s" : ""}. Verdicts show whether each intervention moved metrics in a beneficial direction.`
            : "This was a fully autonomous run with no user interventions."}
        </p>

        ${tableHtml}
        ${chronoHtml}

        <div class="svr-page-footer">
          <span>SimuVerse · Run ${esc(d.runId || "—")}</span>
          <span>Interventions</span>
        </div>
      </div>`;
  }

  function buildTimelinePage(d) {
    const timeline = Array.isArray(d.timeline) ? d.timeline : [];

    /* Group into agent events and intervention events */
    const entries = timeline.filter((e) => e.hasEvent !== false || e.tick != null);

    const entriesHtml = entries.length
      ? entries.map((e) => {
          const isIv = String(e.eventType || e.title || "").toLowerCase()
            .match(/inject|reveal|force|nudge|boost|ease|intervention/);
          const meta = [
            `Step ${esc(String(e.tick || "—"))}`,
            e.actorName ? esc(e.actorName) : null,
            e.targetName && e.targetName !== e.actorName ? `→ ${esc(e.targetName)}` : null,
          ].filter(Boolean).join(" · ");

          const details = Array.isArray(e.actionDetails) && e.actionDetails.length
            ? e.actionDetails.slice(0, 2).join("; ")
            : "";

          return `
            <div class="svr-timeline-entry ${isIv ? "intervention" : ""}">
              <div class="svr-tl-meta">${meta}</div>
              <div class="svr-tl-title">${esc(e.title || "Interaction")}</div>
              ${e.summary ? `<div class="svr-tl-summary">${esc(String(e.summary).slice(0, 160))}</div>` : ""}
              ${details ? `<div class="svr-tl-summary" style="margin-top:3px;font-size:9px;">${esc(details)}</div>` : ""}
            </div>`;
        }).join("")
      : `<div class="svr-empty">No timeline events recorded for this run.</div>`;

    return `
      <div class="svr-page">
        <div class="svr-section-title">Appendix</div>
        <h2 class="svr-h2">Step-by-Step Event Log</h2>
        <p class="svr-page-intro">
          Every recorded interaction from Step 1 through Step ${esc(String(d.totalSteps || 0))}.
          Intervention steps are highlighted in amber.
        </p>

        ${entriesHtml}

        <div class="svr-page-footer">
          <span>SimuVerse · Run ${esc(d.runId || "—")}</span>
          <span>Event Log Appendix</span>
        </div>
      </div>`;
  }

  /* ── Main HTML assembler ─────────────────────────────────────── */

  function buildReportHtml(d) {
    return `
      <!DOCTYPE html>
      <html lang="en">
      <head>
        <meta charset="UTF-8">
        ${reportCss()}
      </head>
      <body>
        <div class="svr">
          ${buildCoverPage(d)}
          ${buildConfigAgentsPage(d)}
          ${buildMetricsPage(d)}
          ${buildInterventionsPage(d)}
          ${buildTimelinePage(d)}
        </div>
      </body>
      </html>`;
  }

  /* ── Core generate() function ────────────────────────────────── */

  async function generate(payload) {
    if (!payload || typeof payload !== "object") {
      console.error("[SimuVerseReport] generate() called with no payload.");
      return { ok: false, error: "No payload" };
    }

    /* Show a user-visible progress indicator */
    let progressEl = null;
    try {
      progressEl = document.createElement("div");
      progressEl.id = "svr-export-progress";
      progressEl.style.cssText = [
        "position:fixed;bottom:24px;right:24px;z-index:99999",
        "background:#112033;color:#fff;font-family:Manrope,sans-serif",
        "font-size:13px;font-weight:700;padding:12px 20px;border-radius:10px",
        "box-shadow:0 4px 20px rgba(0,0,0,0.3);pointer-events:none",
      ].join(";");
      progressEl.textContent = "Preparing PDF…";
      document.body.appendChild(progressEl);

      /* Load html2pdf.js if not already present */
      await loadHtml2Pdf();
      if (typeof window.html2pdf !== "function") {
        throw new Error("html2pdf.js loaded but window.html2pdf is not a function.");
      }

      progressEl.textContent = "Rendering report…";

      /* Build the off-screen container */
      const container = document.createElement("div");
      container.style.cssText = [
        "position:fixed;left:-9999px;top:0;width:794px",
        "background:#fff;z-index:-1;overflow:visible",
      ].join(";");
      container.innerHTML = buildReportHtml(payload);
      document.body.appendChild(container);

      const reportRoot = container.querySelector(".svr");

      const runId = String(payload.runId || "run").replace(/[^a-zA-Z0-9_\-]/g, "_");
      const fileName = `SimuVerse_Run_${runId}.pdf`;

      progressEl.textContent = "Generating PDF…";

      const opt = {
        margin:       [8, 8, 8, 8],   /* top, left, bottom, right — mm */
        filename:     fileName,
        image:        { type: "jpeg", quality: 0.95 },
        html2canvas:  {
          scale:        2,
          useCORS:      true,
          logging:      false,
          windowWidth:  794,
          scrollX:      0,
          scrollY:      0,
        },
        jsPDF: {
          unit:        "mm",
          format:      "a4",
          orientation: "portrait",
          compress:     true,
        },
        pagebreak: {
          mode:   ["css", "legacy"],
          before: ".svr-page",
          avoid:  [".svr-agent-card", ".svr-timeline-entry", ".svr-task-item"],
        },
      };

      await window.html2pdf().set(opt).from(reportRoot).save();

      document.body.removeChild(container);
      progressEl.textContent = "✓ PDF downloaded";
      setTimeout(() => {
        if (progressEl && progressEl.parentNode) {
          progressEl.parentNode.removeChild(progressEl);
        }
      }, 2500);

      return { ok: true, filename: fileName };

    } catch (err) {
      console.error("[SimuVerseReport] PDF generation failed:", err);
      if (progressEl && progressEl.parentNode) {
        progressEl.textContent = "PDF export failed — check console";
        progressEl.style.background = "#c84a4a";
        setTimeout(() => {
          if (progressEl && progressEl.parentNode) progressEl.parentNode.removeChild(progressEl);
        }, 4000);
      }
      /* Surface a user-friendly alert */
      alert(
        "PDF export failed.\n\n" +
        "This usually means the CDN library could not load (check your internet connection) " +
        "or the browser blocked the download.\n\n" +
        "Error: " + (err.message || String(err))
      );
      return { ok: false, error: err.message || String(err) };
    }
  }

  /* ── Public API ──────────────────────────────────────────────── */
  window.SimuVerseReport = { generate };

})();
