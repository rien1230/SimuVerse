// Small browser export helpers for filenames, downloads, and saved snapshots.
(function(global) {
  function pad(value) {
    return String(value).padStart(2, "0");
  }

  function timestamp(date = new Date()) {
    return [
      date.getFullYear(),
      pad(date.getMonth() + 1),
      pad(date.getDate())
    ].join("-") + "_" + [pad(date.getHours()), pad(date.getMinutes()), pad(date.getSeconds())].join("-");
  }

  function slugify(value) {
    return String(value || "results")
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-+|-+$/g, "")
      .slice(0, 80) || "results";
  }

  function downloadBlob(filename, blob) {
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  function downloadJson(filename, payload) {
    downloadBlob(
      filename,
      new Blob([JSON.stringify(payload, null, 2)], {
        type: "application/json;charset=utf-8"
      })
    );
  }

  function csvEscape(value) {
    const stringValue = value == null ? "" : String(value);
    return `"${stringValue.replace(/"/g, '""')}"`;
  }

  function buildCsv(rows, columnOrder, prefaceRows = []) {
    const safeRows = Array.isArray(rows) ? rows : [];
    const columns = columnOrder && columnOrder.length
      ? columnOrder
      : Array.from(safeRows.reduce((set, row) => {
          Object.keys(row || {}).forEach((key) => set.add(key));
          return set;
        }, new Set()));

    const preface = prefaceRows
      .map((row) => (Array.isArray(row) ? row : [row]).map(csvEscape).join(","))
      .join("\n");

    const header = columns.map(csvEscape).join(",");
    const body = safeRows
      .map((row) => columns.map((column) => csvEscape(row ? row[column] : "")).join(","))
      .join("\n");

    return [preface, preface ? "" : null, header, body].filter((part) => part !== null && part !== "").join("\n");
  }

  function downloadCsv(filename, rows, columnOrder, prefaceRows = []) {
    const csv = buildCsv(rows, columnOrder, prefaceRows);
    downloadBlob(
      filename,
      new Blob([csv], {
        type: "text/csv;charset=utf-8"
      })
    );
  }

  async function fetchJson(url, options) {
    const response = await fetch(url, options);
    if (!response.ok) {
      let detail = "";
      try {
        const data = await response.json();
        detail = data && (data.detail || data.message) ? `: ${data.detail || data.message}` : "";
      } catch (error) {
        detail = "";
      }
      throw new Error(`Request failed (${response.status})${detail}`);
    }
    return response.json();
  }

  async function exportRunFromApi({ apiBase, runId, filenamePrefix = "simuverse-run" }) {
    const summary = await fetchJson(`${apiBase}/runs/${encodeURIComponent(runId)}`);
    const payload = {
      export_type: "simulation_run",
      exported_at: new Date().toISOString(),
      replay_code: summary.seed ?? null,
      run: summary
    };

    downloadJson(
      `${filenamePrefix}-${slugify(runId)}-${timestamp()}.json`,
      payload
    );

    return summary;
  }

  function downloadComparisonCsv({ filename, title, setupSummary, insight, fairness, rows, columnOrder }) {
    const preface = [
      ["Comparison", title || "SimuVerse Comparison Results"],
      ["Setup", setupSummary || ""],
      ["Exported At", new Date().toISOString()],
      ["Insight", insight || ""],
      ["Fairness", fairness || ""]
    ];
    downloadCsv(filename, rows, columnOrder, preface);
  }

  global.SimuVerseExport = {
    timestamp,
    slugify,
    downloadJson,
    downloadCsv,
    fetchJson,
    exportRunFromApi,
    downloadComparisonCsv
  };
})(window);
