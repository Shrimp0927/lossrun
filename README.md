# lossrun

Combines insurance loss-run PDFs from different carriers into one claims
table, and flags the problems a broker would otherwise find by eye.

```
uv sync
uv run lossrun process samples/*.pdf --out report.xlsx --json report.json \
    --lines GL,WC,auto,property --years 5
```

`report.xlsx` has four sheets: **Claims** (one row per claim), **Summary** (one
row per policy term), **Flags**, and **Sources** (how each file was read).
`--json` writes the same content as JSON. `--as-of YYYY-MM-DD` sets the report
date, which defaults to today.

Lines of coverage use the codes carriers print: `GL` (general liability), `WC`
(workers' compensation), `auto` and `property`.

## How it works

1. `extract.py` picks a carrier parser from the carrier name at the top of page 1.
2. The parser (`parsers/<carrier>.py`) reads the claims and checks them against
   the totals the report prints.
3. If no parser matches, or the parser fails, the page text goes to Claude
   instead (needs `ANTHROPIC_API_KEY`). Every claim and policy number it returns
   must appear in the PDF text.
4. `combine.py` merges all files into one claims table and a per-policy summary.
5. `flags.py` runs the checks below.
6. `export.py` writes the workbook and the JSON.

A file that cannot be read either way is listed as `failed` in Sources, the
rest are still processed, and the exit code is 1.

Amounts are copied as printed, never recomputed. Every claim row carries
`source_file` and `source_page`, so it can be checked against the PDF.

## Flags

| Code | Meaning |
|---|---|
| `STALE_VALUATION` | Report valued more than 90 days before the report date |
| `OPEN_RESERVE` | Open claim with a nonzero reserve |
| `DUPLICATE_CLAIM_NUMBER` | Same claim number in two files |
| `POSSIBLE_DUPLICATE` | Different claim numbers in two files, same date of loss, line and incurred |
| `MISSING_LINE` | A line named in `--lines` has no report |
| `COVERAGE_GAP` | Part of the last `--years` years has no policy period for a line |
| `INCURRED_MISMATCH` | Incurred ≠ paid + reserved |

Duplicate rows stay in the Claims sheet. In the Summary, a claim number
reported by several files counts once, using the most recently valued row. A
`POSSIBLE_DUPLICATE` is only a suspicion, so both rows still count.

## Samples

The PDFs in `samples/` are AI-generated. They are real PDF files, but the
carriers, the insured and every claim in them are made up; none comes from an
actual carrier. Each has a different layout, and together they trigger every
flag:

| File | Layout |
|---|---|
| `northfield_gl.pdf` | One table |
| `harborline_wc.pdf` | Claims grouped by policy year with subtotals, two pages |
| `pinecrest_property.pdf` | Plain text, two lines per claim |
| `keystone_gl_letter.pdf` | A letter: mostly sentences, with a small table |

`uv run python samples/generate_samples.py` rebuilds them.

## Adding a carrier

1. Copy `lossrun/parsers/northfield.py` and adapt `NAME`, `MARKER` (text
   from the top of page 1) and `parse()`.
2. Add the module to `PARSERS` in `lossrun/parsers/registry.py`.

## Tests

```
uv run pytest
uv run ruff format .
```

`tests/test_end_to_end.py` runs the command on the samples and compares the
result with `tests/expected_report.json`. The Claude path is tested with a fake
client; it has not been run against the real service.

## Limits

- Scanned PDFs (pictures of pages, with no text in them) are rejected.
- One insured per run is assumed; insured names are not matched across files.
- Each report is assumed to cover a single line of coverage.
