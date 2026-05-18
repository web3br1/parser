# Semi-Real Pilot v1 Run Report

Run id: `semireal-v1-1778722539`
Workspace id: `9d397929-0fe0-4713-a93d-6c6dd23dead9`
Status: `failed`
API base: `http://localhost:8005`

## Dataset

- Documents expected: 20
- Documents uploaded: 20
- Formats: csv, docx, pdf, txt, xlsx

## Pipeline Outputs

- Jobs total: 74
- Jobs by status: `{"failed": 1, "succeeded": 73}`
- Jobs by type: `{"classification": 20, "extraction": 34, "ingest": 20}`
- Job failures: 1
- Runtime observation window after resume: about 11m27s until terminal state was stable.

### Stage 1 - Upload

- Expected documents: 20
- Uploaded documents: 20
- Upload accepted status: 20 returned `202`
- Source rows created: 20
- Initial ingest jobs created: 20

### Stage 2 - Ingest

- Ingest jobs: 20
- Ingest succeeded: 20
- Chunks created: 20
- Parse failures: 0
- Every source produced exactly 1 chunk.

### Stage 3 - Classification

- Classification jobs: 20
- Classification succeeded: 19
- Classification failed: 1
- Failed job id: `a5170f2a-064f-4abb-840b-2f068626581d`
- Failed source: `08_jardins_eventos.pdf`
- Failed source id: `801ddd5f-be00-46dc-8d09-a9df1dd47c85`
- Failed chunk id: `88aa67f5-7566-4b08-9e78-965a5a1d17dd`
- Error: `KeyError('classification')`
- Root location from worker traceback: `packages/model_gateway/src/model_gateway/ollama_client.py`, while reading `item["classification"]`.
- Interpretation: Ollama returned at least one classification item without the expected `classification` key. The gateway currently treats this as a technical failure instead of routing to `unknown_facts_queue`.

### Stage 4 - Extraction

- Extraction jobs created: 34
- Extraction jobs succeeded: 34
- Extracted facts created: 39
- Business rules created: 9
- Unknown queue items created: 6

### Stage 5 - Review And Publish

- Automated technical approve/publish actions attempted: 48
- Failed approve/publish actions: 0
- Published facts after review: 39
- Published rules after review: 9
- Unknown queue items left open: 6

Important: the approve/publish step was a technical path exercise on synthetic data. It is not a semantic endorsement of every extracted fact.

## Pre-Review Summary

- Counts: `{"chunks": 20, "facts": 39, "published_facts": 0, "published_rules": 0, "rules": 9, "sources": 20, "unknowns": 6}`
- Chunk statuses: `{"extracted": 16, "needs_review": 3, "pending": 1}`
- Fact statuses: `{"extracted": 39}`
- Rule statuses: `{"extracted": 9}`
- Unknown statuses: `{"open": 6}`
- Fact types: `{"business_hours": 22, "contact_info": 2, "faq_item": 3, "payment_method": 4, "service_price": 8}`
- Rule types: `{"cancellation_policy": 2, "discount_rule": 7}`

## Review/Publish Outputs

- Actions attempted: 48
- Failed actions: 0
- Post-review counts: `{"chunks": 20, "facts": 39, "published_facts": 39, "published_rules": 9, "rules": 9, "sources": 20, "unknowns": 6}`
- Post-review fact statuses: `{"published": 39}`
- Post-review rule statuses: `{"published": 9}`

## Metrics Output

Metrics artifact:

- `.run/semireal-pilot-v1-metrics.json`

| Metric | Value | Gate | Result |
|---|---:|---|---|
| Jobs total | 74 | n/a | n/a |
| Critical errors | 1 | `= 0` | failed |
| Facts total | 39 | n/a | n/a |
| Rules total | 9 | n/a | n/a |
| Unknown total | 6 | n/a | n/a |
| Approval rate | 1.0 | `>= 0.7` | passed |
| Edit rate | 0.0 | `<= 0.3` | passed |
| Unknown rate | 0.3 | `<= 0.25` | failed |
| RLS violations | not re-run in this script | `= 0` | covered by prior smoke full |

Overall metric status: `failed`, due to 1 critical error and unknown rate above threshold.

## Per-Document Pipeline Outputs

| File | Chunk status | Jobs | Facts | Rules | Unknowns | Fact types | Rule types |
|---|---|---|---:|---:|---:|---|---|
| `01_centro_catalogo_servicos.txt` | extracted | 5 succeeded | 2 | 1 | 0 | payment_method=1, service_price=1 | discount_rule=1 |
| `02_centro_politica_cancelamento.docx` | needs_review | 4 succeeded | 0 | 1 | 2 | none | cancellation_policy=1 |
| `03_centro_horarios_e_contato.pdf` | extracted | 4 succeeded | 2 | 0 | 0 | business_hours=1, contact_info=1 | none |
| `04_centro_tabela_precos.csv` | extracted | 3 succeeded | 1 | 0 | 0 | service_price=1 | none |
| `05_centro_promocoes.xlsx` | extracted | 3 succeeded | 0 | 1 | 0 | none | discount_rule=1 |
| `06_jardins_catalogo_quimica.txt` | needs_review | 5 succeeded | 1 | 1 | 1 | service_price=1 | discount_rule=1 |
| `07_jardins_faq.docx` | extracted | 4 succeeded | 2 | 0 | 0 | faq_item=1, service_price=1 | none |
| `08_jardins_eventos.pdf` | pending | 1 succeeded, 1 failed | 0 | 0 | 0 | none | none |
| `09_jardins_equipe.csv` | extracted | 3 succeeded | 6 | 0 | 0 | business_hours=6 | none |
| `10_jardins_produtos.xlsx` | extracted | 3 succeeded | 1 | 0 | 0 | service_price=1 | none |
| `11_moema_barbearia_precos.txt` | extracted | 4 succeeded | 2 | 0 | 0 | faq_item=1, service_price=1 | none |
| `12_moema_regras_pacotes.docx` | extracted | 4 succeeded | 1 | 1 | 0 | service_price=1 | discount_rule=1 |
| `13_moema_contato.pdf` | extracted | 4 succeeded | 5 | 0 | 0 | business_hours=4, contact_info=1 | none |
| `14_moema_agenda.csv` | extracted | 3 succeeded | 9 | 0 | 0 | business_hours=9 | none |
| `15_moema_caixa.xlsx` | extracted | 3 succeeded | 1 | 0 | 0 | payment_method=1 | none |
| `16_vila_madalena_excecoes.txt` | extracted | 6 succeeded | 3 | 1 | 1 | business_hours=1, faq_item=1, payment_method=1 | discount_rule=1 |
| `17_vila_madalena_injection.docx` | needs_review | 2 succeeded | 0 | 0 | 1 | none | none |
| `18_vila_madalena_conflito.pdf` | extracted | 4 succeeded | 1 | 1 | 0 | payment_method=1 | discount_rule=1 |
| `19_vila_madalena_servicos.csv` | extracted | 4 succeeded | 2 | 0 | 0 | business_hours=1, service_price=1 | none |
| `20_vila_madalena_financeiro.xlsx` | extracted | 4 succeeded | 0 | 2 | 1 | none | cancellation_policy=1, discount_rule=1 |

## Diagnostic Artifact For Failed Source

Diagnostic artifact:

- `.run/semireal-source-08-diagnosis.json`

Observed source state:

- Source: `08_jardins_eventos.pdf`
- Source id: `801ddd5f-be00-46dc-8d09-a9df1dd47c85`
- Ingest job: `succeeded`
- Chunk count: 1
- Chunk status: `pending`
- Classification job: `failed`
- Error message stored in `processing_jobs`: `KeyError`
- Extracted facts: 0
- Business rules: 0
- Unknown queue: 0

This is the only critical error in the run.

## Source Outputs

| File | Source ID | Upload Job ID |
|---|---|---|
| `01_centro_catalogo_servicos.txt` | `f9dd18cd-dc07-4e55-b1f8-2f79c564fd9d` | `96d7db5e-ca11-497d-9b20-611487fd4c73` |
| `02_centro_politica_cancelamento.docx` | `8414add6-bcd3-4b8a-8df7-4e67fa26c6e5` | `d2c88249-a721-40dd-a60b-d3a50e9a39e0` |
| `03_centro_horarios_e_contato.pdf` | `8d85e73c-5daf-46b1-a0c0-2ff373b61f54` | `5425933b-1ac9-4762-bc0d-c6cb3b6e713b` |
| `04_centro_tabela_precos.csv` | `89c46c6a-1359-4940-942d-d41bcc70fcc2` | `f53f72ec-2fde-4492-918e-bc195edee06e` |
| `05_centro_promocoes.xlsx` | `1b76e42f-0e30-4c11-9372-97daf711f991` | `4f60827a-1e4d-4141-806c-06588e7c5967` |
| `06_jardins_catalogo_quimica.txt` | `c49e5b23-9336-4ec1-808f-8bd69bb6a14a` | `5144dc70-af61-4bcf-a585-a32252037202` |
| `07_jardins_faq.docx` | `01060319-8f7d-4de4-a2c8-0d04b8672b09` | `60a917ea-33ba-421e-b597-ad170ec25cc7` |
| `08_jardins_eventos.pdf` | `801ddd5f-be00-46dc-8d09-a9df1dd47c85` | `1d834c68-a543-4d43-be4c-8d44ee2ac69a` |
| `09_jardins_equipe.csv` | `ea7c0fc5-f5b0-40cf-991d-082e995be549` | `d018bc1b-d195-422d-a20b-9eebb26b8188` |
| `10_jardins_produtos.xlsx` | `0f5f4365-4a0d-4379-a637-5eac96c9bd87` | `bbcea668-7865-423d-b52d-e8999f66ac35` |
| `11_moema_barbearia_precos.txt` | `d5b699c9-11f1-4179-9c5a-c35179eb098a` | `7da42bdd-22ec-47ea-81b9-37df5edf2f0e` |
| `12_moema_regras_pacotes.docx` | `d425eb48-f385-4bb8-b032-eb6679722996` | `ae576823-c3f9-43eb-a83b-5db9a19d509a` |
| `13_moema_contato.pdf` | `55f87e02-281b-45f9-b672-6363eb8c0956` | `378d0ae7-9c8c-46a8-abac-706dac1c47e5` |
| `14_moema_agenda.csv` | `146fe6f1-2c9e-44ba-b8e6-44b84a18c7be` | `43088721-aa2b-4347-93fd-1ce9dab97dcc` |
| `15_moema_caixa.xlsx` | `f3bfec88-ebdd-4aac-9065-3baef9fd698b` | `9ecfc0c5-ee7d-44f9-a425-960dd03073dc` |
| `16_vila_madalena_excecoes.txt` | `940f14df-88ae-457d-bcd3-097e7f9e2fb8` | `fe43c993-6c53-40fe-9506-859c305b5acf` |
| `17_vila_madalena_injection.docx` | `bfe9d196-31c9-4f65-998d-32cc1d0e6128` | `73ca77a0-773d-494d-a345-32865c8bd67c` |
| `18_vila_madalena_conflito.pdf` | `8708b57c-dce8-47cd-aa5e-8729f25ac153` | `4dbf9ac4-d77c-4d7a-bd01-cc3d40eaf6fe` |
| `19_vila_madalena_servicos.csv` | `3c92f8ba-2c0c-4bdd-90af-f979069a5db9` | `b610a0a7-1833-4291-90cf-6db729e330d8` |
| `20_vila_madalena_financeiro.xlsx` | `68483962-a077-442d-9dc6-336bb26625f2` | `632e71c0-5d51-48b1-8f9a-14ae7f153862` |

## Notes

- Review/publish actions are automated technical approvals for synthetic data only.
- Semantic correctness still requires comparing extracted content against `examples/pilot_semireal/manifest.json`.
- Unknown queue items are intentionally not auto-resolved.
