# Verification status — 10 October 2026

The official templates/questions are still unavailable. No official result CSV or
complete competition submission ZIP has been synthesized.

- `python -m pytest -q`: **80 passed**. Tests make no API calls.
- Actual `gemini-3.1-flash-lite` extraction processed IESCO_0004, KESC_0004,
  KESC_0008, LESCO_0005 and LESCO_0006.
- KESC_0008: **25/25 reference components match exactly**, with **no mismatches**.
  This is the documented diagnostic comparison, not the competition scoring formula.
- No accuracy score is reported for the other four bills: official labels are absent.
- Live general model planning + deterministic arithmetic completed and validated
  **60/60 representative practice answers** across the five images. These questions
  are not from an official guide or released test.
- A separate offline rehearsal uses selected manual transcriptions. It is clearly
  labelled practice and barred from official mode.
- A synthetic ten-bill, 120-row integration test checks exact template preservation,
  CSV escaping, schemas and row counts. It is not an official submission.
- Optional OpenAI verification remained disabled; no OpenAI API calls were made.

Remaining source warnings are retained rather than changing printed amounts:
IESCO has a subsidy-sign/source-line disagreement and printed subtotal relationships;
KESC_0004 has a credit/net-metering balance; LESCO_0005 has multiple meter registers,
so a single scalar units/readings interpretation is unavailable. Ambiguous questions
receive explicit insufficiency answers. See `diagnostics/training/training_report.json`
and `practice/live_output/validation_report.json` for the actual diagnostics.

Google model availability was verified. Transient HTTP 503 errors during development
were retried with bounded backoff. No quota-key rotation or unapproved model was used.
Sandbox network failures required network-enabled execution. A watcher must run with
working network access and the locally configured key to process released files.

Place unchanged official templates in `test/csv/` and their corresponding images in
`test/bills/`. `python main.py --watch --background` waits for complete, stable inputs,
then produces the validated ten-row and 120-row outputs without code changes.
Watcher logs and PID are in the workspace. Start only one watcher.

`source_ready.zip` is source-only, below fifteen MB, and excludes keys, caches, inputs,
practice outputs and environments. After actual official outputs exist, use
`python scripts/package_submission.py --include-results` to create the final ZIP.
