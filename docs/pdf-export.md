# Custom PDF of a report

`report-pdf` prints an existing HTML report to PDF. It reuses the report's content, so no calculation is repeated. It is not `download-pdf`, which retrieves a native Application PDF from the appliance.

```powershell
le-results report-pdf --check
le-results report-pdf --report-dir artifacts/review/report --out artifacts/review/report.pdf
```

On Linux or macOS run the same `le-results` command in your shell.

## Requirements

No pip package and no administrator rights. The command finds Microsoft Edge, Google Chrome or Chromium in `PATH` or a standard install folder. To use a portable copy, unzip it somewhere you own and set `LE_RESULTS_BROWSER` to its executable. If nothing is found the command says so and the HTML report is unaffected. `pypdf` (a development dependency) adds a text check when it is installed.

## What it does

- Prints a temporary copy of `report.html` at A4 landscape with print styles, collapsed evidence sections opened, charts and panels kept whole and table headers repeated. The report on disk is never modified.
- Runs the browser headless with its own throwaway profile and name resolution disabled.
- Verifies the PDF: valid header and end marker, a countable page count, non-trivial content, no local path or home directory in the file and, when `pypdf` is available, the report title text. Failures carry a code: `pdf_invalid`, `pdf_blank`, `pdf_leak`, `pdf_incomplete`, `pdf_timeout`, `pdf_failed`, `pdf_renderer_missing`.
- Writes the PDF only after verification, through a rename. `--replace` swaps an existing PDF only after success; on any failure the previous file is untouched.
- Writes `<name>.pdf.receipt.json` with hashes, page count, renderer name, synthetic flag and verification level. The receipt holds no paths.

Synthetic and provenance labels come from the HTML, so a synthetic report prints as synthetic. Missing values stay unavailable and valid zeros stay zero because the report already encodes them.

## Evidence

The synthetic three-action review printed to three pages with Edge 156. Page images were inspected: title and badge, cards, both charts, coverage tables, the evidence table and the source and limitations text were present. An early print cut a chart across pages and left evidence collapsed; both were fixed in the print styles. Other browsers, operating systems and very long labels are untested.
