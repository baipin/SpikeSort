const state = {
  eidRows: [],
  regionRows: [],
  filteredRows: [],
};

const els = {
  searchInput: document.getElementById("searchInput"),
  labFilter: document.getElementById("labFilter"),
  regionFilter: document.getElementById("regionFilter"),
  minGoodClusters: document.getElementById("minGoodClusters"),
  sortSelect: document.getElementById("sortSelect"),
  resetButton: document.getElementById("resetButton"),
  shownCount: document.getElementById("shownCount"),
  totalCount: document.getElementById("totalCount"),
  totalInsertions: document.getElementById("totalInsertions"),
  totalGoodClusters: document.getElementById("totalGoodClusters"),
  resultsBody: document.getElementById("resultsBody"),
  detailPanel: document.getElementById("detailPanel"),
  detailTitle: document.getElementById("detailTitle"),
  detailContent: document.getElementById("detailContent"),
  closeDetail: document.getElementById("closeDetail"),
  downloadFiltered: document.getElementById("downloadFiltered"),
  loading: document.getElementById("loading"),
};

function parseCsv(text) {
  const rows = [];
  let row = [];
  let value = "";
  let quoted = false;

  for (let i = 0; i < text.length; i += 1) {
    const char = text[i];
    const next = text[i + 1];

    if (quoted) {
      if (char === '"' && next === '"') {
        value += '"';
        i += 1;
      } else if (char === '"') {
        quoted = false;
      } else {
        value += char;
      }
      continue;
    }

    if (char === '"') {
      quoted = true;
    } else if (char === ",") {
      row.push(value);
      value = "";
    } else if (char === "\n") {
      row.push(value);
      rows.push(row);
      row = [];
      value = "";
    } else if (char !== "\r") {
      value += char;
    }
  }

  if (value || row.length) {
    row.push(value);
    rows.push(row);
  }

  const headers = rows.shift();
  return rows
    .filter((items) => items.length === headers.length)
    .map((items) => Object.fromEntries(headers.map((header, index) => [header, items[index]])));
}

function numeric(row, key) {
  return Number(row[key] || 0);
}

function formatNumber(value) {
  return Number(value || 0).toLocaleString("en-US");
}

function splitList(value) {
  return String(value || "")
    .split(";")
    .map((item) => item.trim())
    .filter(Boolean);
}

function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function populateFilters() {
  const labs = [...new Set(state.eidRows.flatMap((row) => splitList(row.labs)))].sort();
  const regions = [...new Set(state.eidRows.flatMap((row) => splitList(row.brain_region_acronyms)))].sort();

  for (const lab of labs) {
    els.labFilter.insertAdjacentHTML("beforeend", `<option value="${escapeHtml(lab)}">${escapeHtml(lab)}</option>`);
  }
  for (const region of regions) {
    els.regionFilter.insertAdjacentHTML("beforeend", `<option value="${escapeHtml(region)}">${escapeHtml(region)}</option>`);
  }
}

function rowMatches(row) {
  const query = els.searchInput.value.trim().toLowerCase();
  const lab = els.labFilter.value;
  const region = els.regionFilter.value;
  const minGood = Number(els.minGoodClusters.value || 0);

  if (lab && !splitList(row.labs).includes(lab)) return false;
  if (region && !splitList(row.brain_region_acronyms).includes(region)) return false;
  if (numeric(row, "n_good_clusters_total") < minGood) return false;

  if (!query) return true;
  const haystack = [
    row.eid,
    row.pids,
    row.labs,
    row.subjects,
    row.recording_dates,
    row.probes,
    row.probe_types,
    row.brain_region_acronyms,
    row.good_brain_region_acronyms,
  ].join(" ").toLowerCase();
  return haystack.includes(query);
}

function sortRows(rows) {
  const [key, direction] = els.sortSelect.value.split(":");
  const sign = direction === "desc" ? -1 : 1;
  const numericKeys = new Set([
    "n_good_clusters_total",
    "n_overall_clusters_total",
    "n_spikes_total",
    "n_trials",
    "recording_minutes",
  ]);

  return [...rows].sort((a, b) => {
    const av = numericKeys.has(key) ? numeric(a, key) : String(a[key] || "");
    const bv = numericKeys.has(key) ? numeric(b, key) : String(b[key] || "");
    if (av < bv) return -1 * sign;
    if (av > bv) return 1 * sign;
    return String(a.eid).localeCompare(String(b.eid));
  });
}

function renderStats(rows) {
  els.shownCount.textContent = formatNumber(rows.length);
  els.totalCount.textContent = formatNumber(state.eidRows.length);
  els.totalInsertions.textContent = formatNumber(rows.reduce((sum, row) => sum + numeric(row, "n_insertions"), 0));
  els.totalGoodClusters.textContent = formatNumber(rows.reduce((sum, row) => sum + numeric(row, "n_good_clusters_total"), 0));
}

function renderTable(rows) {
  if (!rows.length) {
    els.resultsBody.innerHTML = `<tr><td class="empty" colspan="9">No matching eid records.</td></tr>`;
    return;
  }

  els.resultsBody.innerHTML = rows
    .map((row) => {
      const regions = splitList(row.brain_region_acronyms);
      const visibleRegions = regions.slice(0, 8).join(", ");
      const extra = regions.length > 8 ? ` +${regions.length - 8}` : "";
      return `
        <tr data-eid="${escapeHtml(row.eid)}">
          <td class="mono">${escapeHtml(row.eid)}</td>
          <td>${escapeHtml(row.labs)}</td>
          <td>${escapeHtml(row.subjects)}</td>
          <td>${escapeHtml(row.recording_dates)}</td>
          <td>${escapeHtml(row.probes)}</td>
          <td>${formatNumber(row.n_good_clusters_total)} / ${formatNumber(row.n_overall_clusters_total)}</td>
          <td>${formatNumber(row.n_spikes_total)}</td>
          <td>${formatNumber(row.n_trials)}</td>
          <td class="regions">${escapeHtml(visibleRegions + extra)}</td>
        </tr>`;
    })
    .join("");
}

function applyFilters() {
  const rows = sortRows(state.eidRows.filter(rowMatches));
  state.filteredRows = rows;
  renderStats(rows);
  renderTable(rows);
}

function renderDetail(eid) {
  const row = state.eidRows.find((item) => item.eid === eid);
  if (!row) return;

  const regionRows = state.regionRows
    .filter((item) => item.eid === eid)
    .sort((a, b) => numeric(b, "n_good_clusters_labeled") - numeric(a, "n_good_clusters_labeled"));
  const goodRegions = splitList(row.good_brain_region_acronyms);

  els.detailTitle.textContent = row.eid;
  els.detailContent.innerHTML = `
    <div class="detail-grid">
      ${detailField("Lab", row.labs)}
      ${detailField("Subject", row.subjects)}
      ${detailField("Date", row.recording_dates)}
      ${detailField("Probes", row.probes)}
      ${detailField("PIDs", row.pids)}
      ${detailField("Good / all clusters", `${formatNumber(row.n_good_clusters_total)} / ${formatNumber(row.n_overall_clusters_total)}`)}
      ${detailField("Spikes", formatNumber(row.n_spikes_total))}
      ${detailField("Trials", formatNumber(row.n_trials))}
      ${detailField("Duration seconds", Number(row.duration_seconds || 0).toFixed(1))}
      ${detailField("Regions", row.n_unique_regions)}
    </div>
    <div class="region-list">
      ${goodRegions.map((region) => `<span class="chip">${escapeHtml(region)}</span>`).join("")}
    </div>
    <div class="subtable">
      <table>
        <thead>
          <tr>
            <th>PID</th>
            <th>Probe</th>
            <th>Region</th>
            <th>Good</th>
            <th>All</th>
          </tr>
        </thead>
        <tbody>
          ${regionRows.map((item) => `
            <tr>
              <td class="mono">${escapeHtml(item.pid)}</td>
              <td>${escapeHtml(item.probe_name)}</td>
              <td>${escapeHtml(item.acronym)}</td>
              <td>${formatNumber(item.n_good_clusters_labeled)}</td>
              <td>${formatNumber(item.n_clusters_labeled)}</td>
            </tr>`).join("")}
        </tbody>
      </table>
    </div>
  `;
  els.detailPanel.classList.add("open");
  els.detailPanel.setAttribute("aria-hidden", "false");
}

function detailField(label, value) {
  return `<div class="field"><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong></div>`;
}

function toCsv(rows) {
  const columns = [
    "eid",
    "labs",
    "subjects",
    "recording_dates",
    "n_insertions",
    "probes",
    "probe_types",
    "pids",
    "n_good_clusters_total",
    "n_overall_clusters_total",
    "n_spikes_total",
    "n_trials",
    "recording_minutes",
    "n_unique_regions",
    "brain_region_acronyms",
  ];
  const esc = (value) => {
    const text = String(value ?? "");
    return /[",\n\r]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
  };
  return [columns.join(","), ...rows.map((row) => columns.map((column) => esc(row[column])).join(","))].join("\n");
}

function downloadFilteredCsv() {
  const blob = new Blob([toCsv(state.filteredRows)], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = "filtered_eid_directory.csv";
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

function bindEvents() {
  for (const el of [els.searchInput, els.labFilter, els.regionFilter, els.minGoodClusters, els.sortSelect]) {
    el.addEventListener("input", applyFilters);
    el.addEventListener("change", applyFilters);
  }

  els.resetButton.addEventListener("click", () => {
    els.searchInput.value = "";
    els.labFilter.value = "";
    els.regionFilter.value = "";
    els.minGoodClusters.value = "";
    els.sortSelect.value = "n_good_clusters_total:desc";
    applyFilters();
  });

  els.resultsBody.addEventListener("click", (event) => {
    const row = event.target.closest("tr[data-eid]");
    if (row) renderDetail(row.dataset.eid);
  });

  els.closeDetail.addEventListener("click", () => {
    els.detailPanel.classList.remove("open");
    els.detailPanel.setAttribute("aria-hidden", "true");
  });

  els.downloadFiltered.addEventListener("click", downloadFilteredCsv);
}

async function init() {
  try {
    const [eidText, regionText] = await Promise.all([
      fetch("./eid_directory.csv").then((res) => res.text()),
      fetch("./brain_regions_by_insertion.csv").then((res) => res.text()),
    ]);
    state.eidRows = parseCsv(eidText);
    state.regionRows = parseCsv(regionText);
    populateFilters();
    bindEvents();
    applyFilters();
  } catch (error) {
    els.resultsBody.innerHTML = `<tr><td class="empty" colspan="9">Failed to load CSV files: ${escapeHtml(error.message)}</td></tr>`;
  } finally {
    els.loading.classList.add("hidden");
  }
}

init();
