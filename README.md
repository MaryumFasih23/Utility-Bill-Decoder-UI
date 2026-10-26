# WTQ 2026 Utility Bill Decoder

Python 3.11+ CLI for K-Electric, IESCO and LESCO bills. The submitted CSVs are generated from the ten official test images and the original 120-question template using real Google Gemini runtime calls. Python 3.13.11 was used for development and the official run.

## Setup

From the extracted ZIP, enter `source/` and run in PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-lock.txt
Copy-Item .env.example .env
```

Set `GOOGLE_API_KEY_PRIMARY` in your local `.env`. The configured runtime is `MODEL_PROVIDER=google`, `MODEL_NAME=gemini-3.5-flash-lite`. Keep OpenAI verification disabled to reproduce the submitted runtime configuration. `requirements.txt` pins direct dependencies; `requirements-lock.txt` pins all installed dependencies. Network access to the Google API is required.

## Interactive Streamlit Web Application

Launch the modern interactive web application to upload bills, inspect extractions, explore 13-month consumption analytics, and ask arbitrary questions:

```powershell
streamlit run app.py
```

### Application Features
- **Side-by-Side Dual Pane**: View the original high-resolution bill image alongside extracted structured intelligence and analytics.
- **Executive Metric Cards**: Instant display of Units Consumed, Payable Within Due Date, Current Month Bill, and Late Payment Surcharges.
- **Visual Analytics**: Interactive Plotly charts for Charges vs. Taxes breakdown, 13-month historical consumption trends (with current month highlight), and Billed vs. Payment tracking.
- **Live Grounded Q&A**: Ask *any* arbitrary plain-English question about the uploaded bill. Answers are produced via grounded planning, executed with deterministic Decimal arithmetic, and display step-by-step calculation traces with cited source facts.
- **Level 1 Schema & Provenance**: Interactive Level 1 JSON preview with 1-click download, full evidence catalog, confidence ratings, and diagnostic reliability warnings.
- **Dataset Navigator**: Easily switch between official test bills, training samples, or upload your own JPEG/PNG bill.

## Regenerate both official CSVs

Place the original released `test-20261010T073553Z-1-001` folder beside `source/`. Run from `source/`:

```powershell
python main.py --bills "../test-20261010T073553Z-1-001/test/bills" --level1-template "../test-20261010T073553Z-1-001/test/csv/level1.csv" --level2-template "../test-20261010T073553Z-1-001/test/csv/level2.csv" --output "../output"
```

All input paths are arguments and can point to any folder containing the corresponding official files. This command fills only `json` and `answer`, preserves original headers, IDs, questions and ordering, and validates exactly ten Level 1 rows and 120 nonempty Level 2 answers. The original templates are never overwritten. Results are written as UTF-8 CSV with compact single-line JSON. No code changes or question-specific lookup tables are required.

Use `--no-cache` for a fresh image extraction and planning run. By default, content hashes of images, exact model, schema/prompt version and actual questions govern caches. A rerun resumes completed work after a failure. Model-generated text can vary across fresh API calls. Submitted values have no manual CSV edits.

## How it works

The approved Gemini model transcribes printed Level 1 fields and independently extracts rich evidence from original images, including historical consumption, billed amounts, payments, solar registers and adjustment notices. Python maps historical cells to stable fact IDs. Bounded image rereads address conflicts and unreadable values. Credits remain negative; duplicate printed charge/tax entries remain separate; unavailable fields remain null. Monetary subtotals are printed values and are never recomputed to force reconciliation.

For each bill, Gemini sees its original image, extracted evidence and actual template questions. It returns calculation plans and answer templates. Python executes Decimal arithmetic for averages, differences, percentages, counts, extrema and estimates. Numeric operands require source facts, prior results or actual question literals. Unsupported numbers and unreadable calculation inputs are rejected. Qualitative visual explanations retain an image-observation trace. Estimates identify assumptions and use bill-derived rates; no external tariff lookup is used. Missing information is stated explicitly. A bounded same-model plan repair handles invalid plans; unresolved processing errors stop the run.

`output/validation_report.json` and `output/diagnostics/` record runtime, source evidence, calculations and warnings locally. They are excluded from the submission to keep the required artifact small. Automated validation verifies structure and grounding constraints; it does not claim perfect interpretation or establish an official accuracy score.

## Repackage after regeneration

From `source/`:

```powershell
python scripts/package_submission.py --include-results --bills "../test-20261010T073553Z-1-001/test/bills" --level1-template "../test-20261010T073553Z-1-001/test/csv/level1.csv" --level2-template "../test-20261010T073553Z-1-001/test/csv/level2.csv" --output-dir "../output"
```

The allowlist includes runnable project source, this README, `.env.example`, exact dependencies and the two completed CSVs. It excludes actual credentials, caches, virtual environments, bill images, training artifacts and practice outputs. ZIP integrity, required paths, configured-secret exclusion and the fifteen MB limit are checked. The optional demo is omitted.

## Guide compliance checklist

- Approved runtime model: Gemini 3.5 Flash-Lite (`gemini-3.5-flash-lite`).
- Level 1: exact eighteen-key schema; numbers, ISO dates, signed credits, null for unavailable fields.
- Level 2: original 120 rows, bill-grounded English answers, deterministic arithmetic and labelled estimates.
- Original headers, IDs, questions and row order preserved; no empty result cells.
- Required `output/level1.csv`, `output/level2.csv` and runnable `source/` tree.
- Setup/run commands, Python version, pinned dependencies and all environment variables documented.
- No real `.env`, API keys or practice data; ZIP at most fifteen MB.
- Demo video is optional and is not included.

## AI usage disclosure

- Coding assistant: OpenAI Codex, used to implement/debug the application and inspect bills during development. It did not manually author submitted CSV answers.
- Runtime model: Google Gemini 3.5 Flash-Lite, ID `gemini-3.5-flash-lite`.
- Runtime API/service: Google Gemini API through the official `google-genai` Python SDK.
- Optional integration in code: GPT-4.1 mini (`gpt-4.1-mini`) through the official OpenAI SDK. Verification is disabled and was not used to generate these official CSVs.
- Earlier development and initial official attempts also used the approved Gemini 3.1 Flash-Lite (gemini-3.1-flash-lite). Final regeneration uses Gemini 3.5 Flash-Lite.
- Other runtime LLMs: none. Other runtime AI services: none.
- OCR engines, invoice/receipt extraction agents and Azure services: none.
- AI-generated images and other AI coding tools: none.

Practice helper modules remain in the source as development utilities. Official mode rejects offline practice evidence. No manually selected training evidence, reference answers, training images or practice result files are included in the final ZIP.
