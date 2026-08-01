import csv
import json
import re
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPORTS_DIR = ROOT / "reports"
INDEX_JS = REPORTS_DIR / "report_index.js"


def read_csv_row(path):
    with path.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    return rows[0] if rows else {}


def read_csv_rows(path):
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def rel(path, base=REPORTS_DIR):
    return Path(path).resolve().relative_to(base.resolve()).as_posix()


def stamp_from_name(path, prefix):
    match = re.search(rf"{re.escape(prefix)}_(\d{{8}}_\d{{6}})", path.stem)
    return match.group(1) if match else path.stem


def label_for(row, stamp):
    return row.get("condition_label") or row.get("experiment_id") or stamp


def figures_for_stamp(stamp):
    figure_dir = REPORTS_DIR / "figures"
    if not figure_dir.exists():
        return []
    return [
        rel(path)
        for path in sorted(figure_dir.glob(f"*_{stamp}.png"))
    ]


def comparison_images_for_stamp(stamp):
    comparison_dir = REPORTS_DIR / "comparisons"
    if not comparison_dir.exists():
        return []
    return [
        rel(path)
        for path in sorted(comparison_dir.glob(f"*_{stamp}.png"))
    ]


def collect_reports():
    reports = []
    for summary_path in sorted(REPORTS_DIR.glob("bandwidth_summary_*.csv"), reverse=True):
        stamp = stamp_from_name(summary_path, "bandwidth_summary")
        md_path = REPORTS_DIR / f"bandwidth_report_{stamp}.md"
        row = read_csv_row(summary_path)
        reports.append(
            {
                "stamp": stamp,
                "label": label_for(row, stamp),
                "summaryPath": rel(summary_path),
                "reportPath": rel(md_path) if md_path.exists() else "",
                "figures": figures_for_stamp(stamp),
                "markdown": md_path.read_text(encoding="utf-8") if md_path.exists() else "",
                "summary": row,
            }
        )
    return reports


def collect_comparisons():
    comparison_dir = REPORTS_DIR / "comparisons"
    if not comparison_dir.exists():
        return []

    comparisons = []
    for csv_path in sorted(comparison_dir.glob("comparison_summary_*.csv"), reverse=True):
        stamp = stamp_from_name(csv_path, "comparison_summary")
        md_path = comparison_dir / f"comparison_report_{stamp}.md"
        comparisons.append(
            {
                "stamp": stamp,
                "csvPath": rel(csv_path),
                "reportPath": rel(md_path) if md_path.exists() else "",
                "images": comparison_images_for_stamp(stamp),
                "markdown": md_path.read_text(encoding="utf-8") if md_path.exists() else "",
                "rows": read_csv_rows(csv_path),
            }
        )
    return comparisons


def build_index(reports_dir=REPORTS_DIR):
    global REPORTS_DIR, INDEX_JS
    REPORTS_DIR = Path(reports_dir)
    INDEX_JS = REPORTS_DIR / "report_index.js"
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    payload = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "reports": collect_reports(),
        "comparisons": collect_comparisons(),
    }
    content = "window.REPORT_INDEX = "
    content += json.dumps(payload, indent=2, ensure_ascii=False)
    content += ";\n"
    INDEX_JS.write_text(content, encoding="utf-8")
    return INDEX_JS


def main():
    path = build_index()
    print(f"Wrote {path}")


if __name__ == "__main__":
    main()
