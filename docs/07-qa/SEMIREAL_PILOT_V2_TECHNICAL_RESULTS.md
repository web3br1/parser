# Semi-Real Pilot V2 - Technical Results

Date: 2026-05-14  
Environment: `context-builder-dev` / Supabase project `znvixbtquyscpduxiavk`  
Workspace: `7669c38d-a756-4f70-b584-a1a9aefe142c`  
API: `http://localhost:8005`  
Classification model: `gemma4:31b` via Ollama  
Extraction model: `hf.co/hesamation/Qwen3.6-35B-A3B-Claude-4.6-Opus-Reasoning-Distilled-GGUF:Q4_K_M` via Ollama  

## Executive Result

The V2 semi-real pilot passed after retrying one classification job that had been consumed by an older duplicated worker process. Final automated gates passed:

| Gate | Threshold | Final Value | Status |
|---|---:|---:|---|
| Approval rate | `>= 0.70` | `1.00` | pass |
| Edit rate | `<= 0.30` | `0.00` | pass |
| Unknown rate | `<= 0.25` | `0.15` | pass |
| Critical errors | `= 0` | `0` | pass |

Final pipeline status: `passed`.

## Inputs

Dataset: 20 rich synthetic documents from `examples/pilot_semireal`.

Formats covered:

| Format | Count | Examples |
|---|---:|---|
| `txt` | 4 | service catalogs, exceptions, operational notes |
| `docx` | 4 | cancellation policy, FAQ, package rules, adversarial injection |
| `pdf` | 4 | business hours/contact, events, contact, conflicting policy |
| `csv` | 4 | prices, staff, agenda, service table |
| `xlsx` | 4 | promotions, products, cash/finance |

Upload result: 20/20 accepted by API.

## Stage Outputs

### 1. Upload

All 20 files were uploaded and each upload returned a source id and ingest job id.

Representative output:

```json
{
  "filename": "08_jardins_eventos.pdf",
  "format": "pdf",
  "source_id": "444ac9fc-2437-4f6d-9326-568de2dda9d5",
  "job_id": "6d15ad67-5e9c-4e9f-8510-448b85405662"
}
```

### 2. Ingest

Final ingest result:

| Metric | Value |
|---|---:|
| Sources | 20 |
| Chunks | 20 |
| Ingest jobs | 20 |
| Ingest failures | 0 |

Every synthetic document produced one chunk in this run.

### 3. Classification

Final classification result:

| Metric | Value |
|---|---:|
| Classification jobs | 20 |
| Succeeded | 20 |
| Failed | 0 |
| Chunks classified/extracted | 19 |
| Chunks needing review | 1 |
| Unknown queue items | 3 |

Important V2 finding: the new unknown-noise guard worked. The clean V2 run ended with `unknown_rate = 3 / 20 = 0.15`, down from the previous V1 rate of `6 / 20 = 0.30`.

### 4. Extraction

Final extraction result:

| Metric | Value |
|---|---:|
| Extraction jobs | 36 |
| Succeeded | 36 |
| Failed | 0 |
| Extracted facts | 51 |
| Business rules | 10 |

Fact types:

| Type | Count |
|---|---:|
| `business_hours` | 31 |
| `service_price` | 9 |
| `faq_item` | 5 |
| `payment_method` | 4 |
| `contact_info` | 2 |

Rule types:

| Type | Count |
|---|---:|
| `discount_rule` | 7 |
| `cancellation_policy` | 3 |

### 5. Review And Publish

The review/publish step was automated for synthetic data.

| Metric | Value |
|---|---:|
| Published facts | 51 |
| Published rules | 10 |
| Review actions failed | 0 |
| Edited events | 0 |
| Validation events | 122 |

Post-review statuses:

```json
{
  "fact_statuses": {"published": 51},
  "rule_statuses": {"published": 10},
  "unknown_statuses": {"open": 3}
}
```

Unknowns remain open intentionally; they are review inputs, not auto-published knowledge.

## Retry Incident

During the clean V2 run, `08_jardins_eventos.pdf` initially hit the same `KeyError` class seen in V1. Diagnosis showed that multiple Celery classification workers were alive simultaneously. One older worker consumed the classification task before the patched code was guaranteed to be the only consumer.

Recovery steps:

1. Stopped all duplicate `worker_classification` processes.
2. Restarted one clean classification worker.
3. Re-enqueued the failed classification job:
   - Source: `444ac9fc-2437-4f6d-9326-568de2dda9d5`
   - Chunk: `9fbe573a-ad59-4b7d-bc4d-f40b63468d4d`
   - Job: `f0a30586-1b5a-4525-99cf-46cc3fd44f69`
4. The retry succeeded with 3 classification decisions.
5. The retry generated:
   - 2 facts: `service_price`, `faq_item`
   - 1 rule: `cancellation_policy`
6. All three derived records were published.

Final source 08 counts:

```json
{
  "chunks": 1,
  "facts": 2,
  "rules": 1,
  "jobs": 5,
  "unknowns": 0
}
```

## Code Changes Validated

### Ollama classification parser

File: `packages/model_gateway/src/model_gateway/ollama_client.py`

The parser now tolerates malformed classification items from local Ollama models:

- non-object items are skipped;
- objects without `classification` are skipped;
- missing `confidence` defaults to `0.0`;
- missing `reason` defaults to an empty string;
- the original raw response string is preserved for hashing.

Impact: malformed model output no longer crashes classification with `KeyError`.

### Classification noise floor

File: `workers/classification/src/worker_classification/classifier.py`

Added `UNKNOWN_MIN_CONFIDENCE = 0.30`.

Behavior:

- explicit model output `classification = "unknown"` is still routed to `unknown_facts_queue`;
- known fact types below the normal confidence threshold but below `0.30` are dropped as low-signal noise;
- known fact types in the uncertain band are still routed to review.

Impact: V2 unknown rate passed at `0.15`.

### Job retry hygiene

Files:

- `workers/classification/src/worker_classification/db.py`
- `workers/extraction/src/worker_extraction/db.py`

`mark_job_running` and `mark_job_succeeded` now clear stale `error_code` and `error_message`.

Impact: recovered jobs no longer keep misleading old error text after a successful retry.

## Verification Commands

Focused tests and lint:

```powershell
$env:UV_CACHE_DIR='.uv-cache'
uv run pytest workers\classification\tests\test_classification_db.py workers\extraction\tests\test_extraction_db.py packages\model_gateway\tests\test_ollama_client.py workers\classification\tests\test_classifier.py -q
uv run ruff check workers\classification\src\worker_classification\db.py workers\classification\tests\test_classification_db.py workers\extraction\src\worker_extraction\db.py workers\extraction\tests\test_extraction_db.py packages\model_gateway\src\model_gateway\ollama_client.py workers\classification\src\worker_classification\classifier.py
```

Result:

```text
27 passed
All checks passed
```

Final V2 metrics:

```powershell
uv run python scripts\pilot\pilot_metrics.py --workspace-id 7669c38d-a756-4f70-b584-a1a9aefe142c --output .run\semireal-pilot-v2-metrics-after-retry.json
```

Result: `passed = true`.

## Artifacts

| Artifact | Purpose |
|---|---|
| `.run/semireal-pilot-v2-report.json` | Raw clean V2 run before retry |
| `.run/semireal-pilot-v2-metrics-before-retry.json` | V2 gates before retry |
| `.run/semireal-pilot-v2-report-after-retry.json` | Final V2 operational report |
| `.run/semireal-pilot-v2-metrics-after-retry.json` | Final V2 quality gates |
| `.run/semireal-v2-source-08-diagnosis-final.json` | Final source 08 diagnostic |
| `docs/07-qa/SEMIREAL_PILOT_V2_RETRY_REPORT.md` | Auto-generated final run report |
| `docs/07-qa/SEMIREAL_PILOT_V2_TECHNICAL_RESULTS.md` | This technical report |

## Residual Risks And Follow-Ups

1. Source rows remain in `status = "processing"` even after chunk/job completion. This did not block publication or metrics, but the source finalization state machine needs a dedicated fix before production.
2. `unknown_facts_queue` still has 3 open items. This is acceptable for the pilot gate, but they should be semantically reviewed against the manifest before a real customer pilot.
3. The local Windows stack allowed duplicated Celery workers. The dev script should either assign unique worker names or provide a stronger `stop_local_stack.ps1` cleanup path.
4. The final pass validates pipeline mechanics and model robustness, not full semantic precision. The next QA layer should compare extracted values against `examples/pilot_semireal/manifest.json`.
