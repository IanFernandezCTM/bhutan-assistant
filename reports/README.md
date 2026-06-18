# reports/ — reproducible benchmarks

## Classifier accuracy

`benchmark_classifier.py` runs the prototype's **actual** classifier against the real
labelled test set and prints per-dimension accuracy. It replaces the previously
**unverified** `95.1% / 85.4%` figures (which appeared only in `app.py` docstrings and
matched no file in the repo).

### Test set provenance

`bhutan_classifier_test_set.csv` here is a **vendored copy** (credit: **Team B**, originally
`team_b/intent_classifier/bhutan_classifier_test_set_augmented_english.csv`). 234 rows =
**36 original hand-labelled questions (Q001–Q036)** + 198 synthetic augmentations, labelled
on the same 4 dimensions the prototype produces: `in_scope · safety · request_type · service`.
It is vendored so the benchmark is reproducible even on the Render deploy repo (where `team_b/`
is absent). The filename matches the one `app.py` historically referenced.

### Run it

```bash
.venv/Scripts/python.exe reports/benchmark_classifier.py            # offline KeywordClassifier
.venv/Scripts/python.exe reports/benchmark_classifier.py --gemini   # GeminiClassifier (needs GEMINI_API_KEY; costs API calls)
```

### Measured results — `KeywordClassifier` (offline fallback), 2026-06-18

| Slice | in_scope | safety | request_type | service | macro-avg | exact 4/4 |
|---|---|---|---|---|---|---|
| Full augmented (234) | 90.60% | 92.74% | 46.58% | 80.34% | **77.56%** | 38.03% |
| Original 36 (Q001–Q036) | 97.22% | 100.00% | 55.56% | 86.11% | **84.72%** | 44.44% |
| Health-filtered (155) | 85.81% | 95.48% | 50.32% | 81.94% | **78.39%** | 40.65% |

Notes:
- `request_type` is the weakest dimension (≈47–56%) and pulls the macro-average down.
- The `GeminiClassifier` (chain-of-thought) was **not** benchmarked here — it requires a
  `GEMINI_API_KEY` and bills API calls. Re-run with `--gemini` to measure it; record the
  number here when you do. **Until then, do not cite a Gemini accuracy figure as substantiated.**
- For comparison, Team B's own `KeywordClassifier` (with a MiniLM semantic fallback),
  health-filtered, scored: in_scope 0.8968, safety 0.9677, service 0.9032, request_type 0.6194
  (`team_b/intent_classifier/evaluation_metrics.csv`) — a different, slightly stronger classifier.
