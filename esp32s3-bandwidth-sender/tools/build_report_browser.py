import csv
import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPORTS_DIR = ROOT / "reports"
INDEX_JS = REPORTS_DIR / "report_index.js"
INTEGRATED_REPORTS_DIR = ROOT.parent / "integrated-static-site" / "esp32-reports"
ORGANIZED_REPORT_DIRS = (
    "runs",
    "udp_matrices",
    "tcp_best_config",
    "udp_50ms_summary",
    "sqp_trace_simulation",
    "figures",
    "comparisons",
    "sqp_offline",
    "saturated_udp_condition_bundle_20260826",
    "saturated_udp_field_20260826",
)


def read_csv_row(path):
    with path.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    return rows[0] if rows else {}


def read_csv_rows(path):
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def rel(path, base=None):
    base = REPORTS_DIR if base is None else base
    return Path(path).resolve().relative_to(base.resolve()).as_posix()


def stamp_from_name(path, prefix):
    match = re.search(rf"{re.escape(prefix)}_(\d{{8}}_\d{{6}})", path.stem)
    return match.group(1) if match else path.stem


def label_for(row, stamp):
    return row.get("condition_label") or row.get("experiment_id") or stamp


def figures_for_stamp(stamp):
    return [
        rel(path)
        for path in sorted(REPORTS_DIR.rglob(f"*_{stamp}.png"))
        if "figures" in path.relative_to(REPORTS_DIR).parts
    ]


def setup_for_report(row, stamp, markdown):
    setup = {}
    db_path = row.get("db_path", "").replace("\\", "/").lower()
    if "wroom-typec-front-near" in db_path:
        setup.update(
            {
                "hardware": "ESP32-WROOM-32E",
                "power": "Type-C",
                "placement": "in front of the device",
                "distance": "near (<1 m)",
                "note": "N/A",
            }
        )
    elif stamp == "20260813_190121":
        setup.update(
            {
                "hardware": "ESP32-WROOM-32E",
                "power": "battery",
                "placement": "on-head",
                "distance": "near (<1 m)",
                "note": "on head",
            }
        )
    elif row.get("transport") == "udp":
        setup.update(
            {
                "hardware": "ESP32-S3",
                "power": "USB Type-C",
                "placement": "in front of the device",
                "distance": "near (<1 m)",
            }
        )

    note_match = re.search(r'"operator_notes":\s*"([^"]+)"', markdown)
    if note_match and not setup.get("note"):
        setup["note"] = note_match.group(1)
    return setup


def comparison_images_for_stamp(stamp, search_dir=None):
    comparison_dir = REPORTS_DIR / "comparisons"
    if not comparison_dir.exists():
        return []
    search_root = Path(search_dir) if search_dir else comparison_dir
    return [
        rel(path)
        for path in sorted(search_root.glob(f"*_{stamp}.png"))
    ]


def collect_reports():
    reports = []
    for summary_path in sorted(REPORTS_DIR.rglob("bandwidth_summary_*.csv"), reverse=True):
        stamp = stamp_from_name(summary_path, "bandwidth_summary")
        md_path = summary_path.parent / f"bandwidth_report_{stamp}.md"
        pdf_path = md_path.with_suffix(".pdf")
        row = read_csv_row(summary_path)
        markdown = md_path.read_text(encoding="utf-8") if md_path.exists() else ""
        reports.append(
            {
                "stamp": stamp,
                "label": label_for(row, stamp),
                "summaryPath": rel(summary_path),
                "reportPath": rel(md_path) if md_path.exists() else "",
                "pdfPath": rel(pdf_path) if pdf_path.exists() else "",
                "figures": figures_for_stamp(stamp),
                "markdown": markdown,
                "summary": row,
                "setup": setup_for_report(row, stamp, markdown),
            }
        )
    return reports


def collect_comparisons():
    comparison_dir = REPORTS_DIR / "comparisons"
    if not comparison_dir.exists():
        return []

    comparisons = []
    for csv_path in sorted(comparison_dir.rglob("comparison_summary_*.csv"), reverse=True):
        stamp = stamp_from_name(csv_path, "comparison_summary")
        md_path = csv_path.parent / f"comparison_report_{stamp}.md"
        pdf_path = md_path.with_suffix(".pdf")
        comparisons.append(
            {
                "stamp": stamp,
                "csvPath": rel(csv_path),
                "reportPath": rel(md_path) if md_path.exists() else "",
                "pdfPath": rel(pdf_path) if pdf_path.exists() else "",
                "images": comparison_images_for_stamp(stamp, csv_path.parent),
                "markdown": md_path.read_text(encoding="utf-8") if md_path.exists() else "",
                "rows": read_csv_rows(csv_path),
            }
        )
    return comparisons


def write_report_index_files(payload, reports_dir):
    reports_dir = Path(reports_dir)
    content = "window.REPORT_INDEX = "
    content += json.dumps(payload, indent=2, ensure_ascii=False)
    content += ";\n"

    index_js = reports_dir / "report_index.js"
    index_js.write_text(content, encoding="utf-8")

    index_html = reports_dir / "index.html"
    if index_html.exists():
        html = index_html.read_text(encoding="utf-8")
        pattern = r"window\.REPORT_INDEX = \{.*?\};\s*</script>"
        replacement = content + "\n\n</script>"
        updated, count = re.subn(pattern, replacement, html, count=1, flags=re.DOTALL)
        if count:
            index_html.write_text(updated, encoding="utf-8")
        else:
            print(f"Warning: could not refresh inline REPORT_INDEX in {index_html}")

    return index_js


def copy_tree_contents(src_dir, dst_dir):
    src_dir = Path(src_dir)
    dst_dir = Path(dst_dir)
    if not src_dir.exists():
        return
    dst_dir.mkdir(parents=True, exist_ok=True)
    for src_path in src_dir.rglob("*"):
        rel_path = src_path.relative_to(src_dir)
        dst_path = dst_dir / rel_path
        if src_path.is_dir():
            dst_path.mkdir(parents=True, exist_ok=True)
        else:
            dst_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src_path, dst_path)


def sync_integrated_site(source_reports_dir=REPORTS_DIR):
    source_reports_dir = Path(source_reports_dir)
    if source_reports_dir.resolve() == INTEGRATED_REPORTS_DIR.resolve():
        return None
    if not INTEGRATED_REPORTS_DIR.parent.exists():
        return None

    INTEGRATED_REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    for pattern in ("bandwidth_report_*.md", "bandwidth_summary_*.csv", "udp_throughput_matrix_*.csv"):
        for src_path in source_reports_dir.glob(pattern):
            shutil.copy2(src_path, INTEGRATED_REPORTS_DIR / src_path.name)
    for src_path in source_reports_dir.rglob("*.pdf"):
        if src_path.is_file():
            dst_path = INTEGRATED_REPORTS_DIR / src_path.relative_to(source_reports_dir)
            dst_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src_path, dst_path)

    for filename in ("index.html", "report_index.js"):
        src_path = source_reports_dir / filename
        if src_path.exists():
            shutil.copy2(src_path, INTEGRATED_REPORTS_DIR / filename)

    for dirname in ORGANIZED_REPORT_DIRS:
        copy_tree_contents(source_reports_dir / dirname, INTEGRATED_REPORTS_DIR / dirname)

    return build_index(INTEGRATED_REPORTS_DIR, sync_integrated=False)


def build_index(reports_dir=REPORTS_DIR, sync_integrated=True):
    global REPORTS_DIR, INDEX_JS
    REPORTS_DIR = Path(reports_dir)
    INDEX_JS = REPORTS_DIR / "report_index.js"
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    payload = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "reports": collect_reports(),
        "comparisons": collect_comparisons(),
    }
    INDEX_JS = write_report_index_files(payload, REPORTS_DIR)
    primary_reports_dir = REPORTS_DIR
    primary_index_js = INDEX_JS
    if sync_integrated:
        integrated_index = sync_integrated_site(REPORTS_DIR)
        if integrated_index:
            print(f"Wrote {integrated_index}")
        REPORTS_DIR = primary_reports_dir
        INDEX_JS = primary_index_js
    return primary_index_js


def main():
    path = build_index()
    print(f"Wrote {path}")


if __name__ == "__main__":
    main()
