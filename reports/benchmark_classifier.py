"""
Reproducible benchmark of the prototype's classifier against the REAL labelled
test set, to replace the unsubstantiated 95.1% / 85.4% figures with measured numbers.

Test set provenance (Team B):
    team_b/intent_classifier/bhutan_classifier_test_set_augmented_english.csv
    234 rows = 36 original hand-labelled (Q001-Q036) + 198 synthetic.
    Labelled on the SAME 4 dimensions the prototype produces:
        in_scope · safety · request_type · service
A vendored copy lives next to this script as `bhutan_classifier_test_set.csv`
(the filename app.py historically referenced) so the benchmark is self-contained
and reproducible even on the deploy repo where team_b/ is not present.

Run:
    .venv/Scripts/python.exe reports/benchmark_classifier.py
    .venv/Scripts/python.exe reports/benchmark_classifier.py --gemini   # needs GEMINI_API_KEY (costs API calls)

Reports per-dimension accuracy and a macro-average, for:
    (a) the full augmented set (234 rows)
    (b) the 36 original questions (Q001-Q036) — the set app.py's claim referenced
    (c) the health-filtered set (compare with team_b/.../evaluation_metrics.csv)
"""
from __future__ import annotations

import argparse
import csv
import json
#import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROTOTYPE_DIR = HERE.parent
REPO_ROOT = PROTOTYPE_DIR.parent

# Import the prototype's classifiers without triggering Flask app construction.
sys.path.insert(0, str(PROTOTYPE_DIR))

DIMENSIONS = ["in_scope", "safety", "request_type", "service"]

# Candidate locations for the labelled test set, in priority order.
CSV_CANDIDATES = [
    HERE / "bhutan_classifier_test_set.csv",  # vendored (deploy-safe)
    REPO_ROOT / "team_b" / "intent_classifier" / "bhutan_classifier_test_set_augmented_english.csv",
]


def load_rows() -> tuple[list[dict], Path]:
    for path in CSV_CANDIDATES:
        if path.exists():
            with open(path, encoding="utf-8-sig", newline="") as fh:
                rows = list(csv.DictReader(fh))
            return rows, path
    raise FileNotFoundError(
        "Test set not found. Looked in:\n  " + "\n  ".join(str(c) for c in CSV_CANDIDATES)
    )


def make_classifier(use_gemini: bool):
    from app import KeywordClassifier  # noqa: E402

    if use_gemini:
        from app import GENAI_AVAILABLE, GEMINI_API_KEY, GeminiClassifier  # noqa: E402

        if not (GENAI_AVAILABLE and GEMINI_API_KEY):
            print("[warn] --gemini requested but google-generativeai/GEMINI_API_KEY unavailable; "
                  "falling back to KeywordClassifier.")
            return KeywordClassifier(), "KeywordClassifier"
        return GeminiClassifier(api_key=GEMINI_API_KEY), "GeminiClassifier"
    return KeywordClassifier(), "KeywordClassifier"


def score(rows: list[dict], classifier) -> dict:
    correct = {d: 0 for d in DIMENSIONS}
    total = len(rows)
    exact_match = 0
    for row in rows:
        pred = classifier.classify(row["user_question"])
        all_dims_ok = True
        for d in DIMENSIONS:
            gold = (row.get(d) or "").strip()
            got = pred[d].label
            if got == gold:
                correct[d] += 1
            else:
                all_dims_ok = False
        if all_dims_ok:
            exact_match += 1
    per_dim = {d: round(correct[d] / total, 4) for d in DIMENSIONS} if total else {}
    return {
        "n": total,
        "per_dimension_accuracy": per_dim,
        "macro_avg_accuracy": round(sum(per_dim.values()) / len(per_dim), 4) if per_dim else 0.0,
        "exact_match_all_4_dims": round(exact_match / total, 4) if total else 0.0,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--gemini", action="store_true", help="use GeminiClassifier (needs key, costs calls)")
    ap.add_argument("--json", action="store_true", help="emit machine-readable JSON only")
    args = ap.parse_args()

    rows, csv_path = load_rows()
    classifier, kind = make_classifier(args.gemini)

    originals = [r for r in rows if (r.get("id") or "").startswith("Q")]
    health_filtered = [r for r in rows if (r.get("service") or "").strip() != "health"]

    result = {
        "classifier": kind,
        "test_set": str(csv_path),
        "full_augmented_234": score(rows, classifier),
        "original_36_questions": score(originals, classifier),
        "health_filtered": score(health_filtered, classifier),
    }

    if args.json:
        print(json.dumps(result, indent=2))
        return

    print(f"\nClassifier under test : {kind}")
    print(f"Test set              : {csv_path.name}  ({len(rows)} rows)")
    for section, label in [
        ("full_augmented_234", "FULL augmented set"),
        ("original_36_questions", "Original 36 questions (Q001-Q036)"),
        ("health_filtered", "Health-filtered (compare team_b evaluation_metrics.csv)"),
    ]:
        s = result[section]
        print(f"\n== {label}  (n={s['n']}) ==")
        for d in DIMENSIONS:
            print(f"   {d:14s} {s['per_dimension_accuracy'][d]*100:6.2f}%")
        print(f"   {'macro-avg':14s} {s['macro_avg_accuracy']*100:6.2f}%")
        print(f"   {'exact 4/4':14s} {s['exact_match_all_4_dims']*100:6.2f}%")
    print()


if __name__ == "__main__":
    main()
