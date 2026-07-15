const fs = require("fs");
const path = require("path");
const vm = require("vm");

const root = __dirname;
const dataPath = path.join(root, "data.js");
const lzPath = path.join(root, "lz-string.min.js");

function csvEscape(value) {
  if (value === null || value === undefined) return "";
  const s = String(value);
  return /[",\r\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
}

function writeCsv(fileName, rows, columns) {
  const lines = [
    columns.join(","),
    ...rows.map((row) => columns.map((col) => csvEscape(row[col])).join(",")),
  ];
  fs.writeFileSync(path.join(root, fileName), lines.join("\n") + "\n");
}

function parseOverallClusters(text) {
  const match = String(text || "").match(/(\d+)\s+good,\s+(\d+)\s+overall/);
  return {
    good: match ? Number(match[1]) : "",
    overall: match ? Number(match[2]) : "",
  };
}

function parseMinutes(text) {
  const match = String(text || "").match(/([\d.]+)\s+minutes/);
  return match ? Number(match[1]) : "";
}

function unique(values) {
  return [...new Set(values.filter((v) => v !== null && v !== undefined && v !== ""))];
}

const data = fs.readFileSync(dataPath, "utf8");
const lzCode = fs.readFileSync(lzPath, "utf8");
const sandbox = {};
vm.createContext(sandbox);
vm.runInContext(lzCode, sandbox);

const compressed = data.match(/const FLASK_CTX_COMPRESSED = "([^"]+)";/);
if (!compressed) {
  throw new Error("FLASK_CTX_COMPRESSED was not found in data.js");
}

const decompressed = sandbox.LZString.decompressFromBase64(compressed[1]);
const ctx = JSON.parse(decompressed);
fs.writeFileSync(path.join(root, "flask_ctx.json"), JSON.stringify(ctx));

const sessions = ctx.SESSIONS;
const insertionRows = [];
const regionRows = [];
const eidMap = new Map();

for (const s of sessions) {
  const clusterCounts = parseOverallClusters(s["N clusters"]);
  const acronyms = s._acronyms || [];
  const goodFlags = s._good_ids || [];
  const regions = unique(acronyms);
  const goodRegions = unique(acronyms.filter((_, i) => goodFlags[i]));
  const rowJsonBytes = Buffer.byteLength(JSON.stringify(s));
  const durationSeconds = Number(s._duration || 0);

  const insertion = {
    eid: s.eid,
    pid: s.pid,
    id: s.ID,
    lab: s.Lab,
    subject: s.Subject,
    dob: s.DOB,
    recording_date: s["Recording date"],
    probe_name: s["Probe name"],
    probe_type: s["Probe type"],
    dset_bwm: Boolean(s.dset_bwm),
    dset_rs: Boolean(s.dset_rs),
    n_clusters_text: s["N clusters"],
    n_good_clusters: clusterCounts.good,
    n_overall_clusters: clusterCounts.overall,
    n_spikes: Number(s["N spikes"] || 0),
    n_trials: Number(s["N trials"] || 0),
    recording_length: s["Recording length"],
    recording_minutes: parseMinutes(s["Recording length"]),
    duration_seconds: durationSeconds,
    n_cluster_region_labels: acronyms.length,
    n_unique_regions: regions.length,
    n_good_unique_regions: goodRegions.length,
    brain_region_acronyms: regions.join(";"),
    good_brain_region_acronyms: goodRegions.join(";"),
    brain_regions_text: s._regions || "",
    session_json_bytes: rowJsonBytes,
  };
  insertionRows.push(insertion);

  const regionMap = new Map();
  for (let i = 0; i < acronyms.length; i += 1) {
    const acronym = acronyms[i] || "";
    if (!acronym) continue;
    if (!regionMap.has(acronym)) {
      regionMap.set(acronym, { total: 0, good: 0 });
    }
    const entry = regionMap.get(acronym);
    entry.total += 1;
    if (goodFlags[i]) entry.good += 1;
  }
  for (const [acronym, counts] of regionMap.entries()) {
    regionRows.push({
      eid: s.eid,
      pid: s.pid,
      lab: s.Lab,
      subject: s.Subject,
      recording_date: s["Recording date"],
      probe_name: s["Probe name"],
      acronym,
      n_clusters_labeled: counts.total,
      n_good_clusters_labeled: counts.good,
    });
  }

  if (!eidMap.has(s.eid)) {
    eidMap.set(s.eid, {
      eid: s.eid,
      labs: new Set(),
      subjects: new Set(),
      recording_dates: new Set(),
      probes: new Set(),
      probe_types: new Set(),
      pids: new Set(),
      dset_bwm: false,
      dset_rs: false,
      n_insertions: 0,
      n_good_clusters: 0,
      n_overall_clusters: 0,
      n_spikes: 0,
      n_trials_max: 0,
      duration_seconds_max: 0,
      recording_minutes_max: 0,
      regions: new Set(),
      goodRegions: new Set(),
      jsonBytes: 0,
    });
  }

  const e = eidMap.get(s.eid);
  e.labs.add(s.Lab);
  e.subjects.add(s.Subject);
  e.recording_dates.add(s["Recording date"]);
  e.probes.add(s["Probe name"]);
  e.probe_types.add(s["Probe type"]);
  e.pids.add(s.pid);
  e.dset_bwm = e.dset_bwm || Boolean(s.dset_bwm);
  e.dset_rs = e.dset_rs || Boolean(s.dset_rs);
  e.n_insertions += 1;
  e.n_good_clusters += Number(clusterCounts.good || 0);
  e.n_overall_clusters += Number(clusterCounts.overall || 0);
  e.n_spikes += Number(s["N spikes"] || 0);
  e.n_trials_max = Math.max(e.n_trials_max, Number(s["N trials"] || 0));
  e.duration_seconds_max = Math.max(e.duration_seconds_max, durationSeconds);
  e.recording_minutes_max = Math.max(e.recording_minutes_max, Number(insertion.recording_minutes || 0));
  regions.forEach((r) => e.regions.add(r));
  goodRegions.forEach((r) => e.goodRegions.add(r));
  e.jsonBytes += rowJsonBytes;
}

const eidRows = [...eidMap.values()].map((e) => ({
  eid: e.eid,
  labs: [...e.labs].join(";"),
  subjects: [...e.subjects].join(";"),
  recording_dates: [...e.recording_dates].join(";"),
  n_insertions: e.n_insertions,
  probes: [...e.probes].join(";"),
  probe_types: [...e.probe_types].join(";"),
  pids: [...e.pids].join(";"),
  dset_bwm: e.dset_bwm,
  dset_rs: e.dset_rs,
  n_good_clusters_total: e.n_good_clusters,
  n_overall_clusters_total: e.n_overall_clusters,
  n_spikes_total: e.n_spikes,
  n_trials: e.n_trials_max,
  duration_seconds: e.duration_seconds_max,
  recording_minutes: e.recording_minutes_max,
  n_unique_regions: e.regions.size,
  n_good_unique_regions: e.goodRegions.size,
  brain_region_acronyms: [...e.regions].join(";"),
  good_brain_region_acronyms: [...e.goodRegions].join(";"),
  session_json_bytes_total: e.jsonBytes,
}));

writeCsv("sessions_by_insertion.csv", insertionRows, [
  "eid",
  "pid",
  "id",
  "lab",
  "subject",
  "dob",
  "recording_date",
  "probe_name",
  "probe_type",
  "dset_bwm",
  "dset_rs",
  "n_clusters_text",
  "n_good_clusters",
  "n_overall_clusters",
  "n_spikes",
  "n_trials",
  "recording_length",
  "recording_minutes",
  "duration_seconds",
  "n_cluster_region_labels",
  "n_unique_regions",
  "n_good_unique_regions",
  "brain_region_acronyms",
  "good_brain_region_acronyms",
  "brain_regions_text",
  "session_json_bytes",
]);

writeCsv("eid_directory.csv", eidRows, [
  "eid",
  "labs",
  "subjects",
  "recording_dates",
  "n_insertions",
  "probes",
  "probe_types",
  "pids",
  "dset_bwm",
  "dset_rs",
  "n_good_clusters_total",
  "n_overall_clusters_total",
  "n_spikes_total",
  "n_trials",
  "duration_seconds",
  "recording_minutes",
  "n_unique_regions",
  "n_good_unique_regions",
  "brain_region_acronyms",
  "good_brain_region_acronyms",
  "session_json_bytes_total",
]);

writeCsv("brain_regions_by_insertion.csv", regionRows, [
  "eid",
  "pid",
  "lab",
  "subject",
  "recording_date",
  "probe_name",
  "acronym",
  "n_clusters_labeled",
  "n_good_clusters_labeled",
]);

const summary = {
  source_url: "https://viz.internationalbrainlab.org/app?spikesorting=ss_2024-05-06",
  source_data_url: "https://viz.internationalbrainlab.org/static/cache/ss_2024-05-06/data.js",
  default_spikesorting: "ss_2024-05-06",
  default_pid: ctx.DEFAULT_PID,
  default_dset: ctx.DEFAULT_DSET,
  data_js_bytes: fs.statSync(dataPath).size,
  lz_string_bytes: fs.statSync(lzPath).size,
  decompressed_json_bytes: Buffer.byteLength(decompressed),
  n_session_records: sessions.length,
  n_unique_eids: eidRows.length,
  n_unique_pids: unique(sessions.map((s) => s.pid)).length,
  n_bwm_insertions: sessions.filter((s) => s.dset_bwm).length,
  n_rs_insertions: sessions.filter((s) => s.dset_rs).length,
  output_files: [
    "flask_ctx.json",
    "sessions_by_insertion.csv",
    "eid_directory.csv",
    "brain_regions_by_insertion.csv",
  ],
};
fs.writeFileSync(path.join(root, "summary.json"), JSON.stringify(summary, null, 2) + "\n");

const readme = `# IBL Viz ss_2024-05-06 data directory

Source page: ${summary.source_url}

Source data file: ${summary.source_data_url}

## Summary

- Session/insertion records shown by the web app: ${summary.n_session_records}
- Unique eids: ${summary.n_unique_eids}
- Unique pids/insertions: ${summary.n_unique_pids}
- Brain-wide-map insertion records: ${summary.n_bwm_insertions}
- Repeated-sites insertion records: ${summary.n_rs_insertions}
- data.js size: ${summary.data_js_bytes} bytes
- Decompressed JSON size: ${summary.decompressed_json_bytes} bytes

## Files

- flask_ctx.json: full decompressed web-app context.
- eid_directory.csv: one row per eid, aggregating all probes/insertions for that eid.
- sessions_by_insertion.csv: one row per web-app session/insertion record.
- brain_regions_by_insertion.csv: one row per eid/pid/probe/brain-region acronym.
- summary.json: machine-readable summary and source metadata.
`;
fs.writeFileSync(path.join(root, "README.md"), readme);

console.log(JSON.stringify(summary, null, 2));
