# Semi-Real Pilot V2 Retry Run Report

Script run id: `semireal-v1-1778763466` (legacy script label; this artifact is the V2 retry report)
Workspace id: `7669c38d-a756-4f70-b584-a1a9aefe142c`
Status: `passed`
API base: `http://localhost:8005`

## Dataset

- Documents expected: 20
- Documents uploaded: 20
- Formats: csv, docx, pdf, txt, xlsx

## Pipeline Outputs

- Jobs total: 76
- Jobs by status: `{"succeeded": 76}`
- Jobs by type: `{"classification": 20, "extraction": 36, "ingest": 20}`
- Job failures: 0

## Pre-Review Summary

- Counts: `{"chunks": 20, "facts": 51, "published_facts": 49, "published_rules": 9, "rules": 10, "sources": 20, "unknowns": 3}`
- Chunk statuses: `{"extracted": 19, "needs_review": 1}`
- Fact statuses: `{"extracted": 2, "published": 49}`
- Rule statuses: `{"extracted": 1, "published": 9}`
- Unknown statuses: `{"open": 3}`
- Fact types: `{"business_hours": 31, "contact_info": 2, "faq_item": 5, "payment_method": 4, "service_price": 9}`
- Rule types: `{"cancellation_policy": 3, "discount_rule": 7}`

## Review/Publish Outputs

- Actions attempted: 3
- Failed actions: 0
- Post-review counts: `{"chunks": 20, "facts": 51, "published_facts": 51, "published_rules": 10, "rules": 10, "sources": 20, "unknowns": 3}`
- Post-review fact statuses: `{"published": 51}`
- Post-review rule statuses: `{"published": 10}`

## Source Outputs

| File | Source ID | Upload Job ID |
|---|---|---|
| `01_centro_catalogo_servicos.txt` | `ef0a5c24-865f-48b2-9167-5550ad85d8e2` | `8df0b001-114f-45c1-90dc-715323640682` |
| `02_centro_politica_cancelamento.docx` | `98680643-2460-4609-8ec7-71435cee7637` | `b1113e81-ef87-45b3-9618-b9c9e54ae560` |
| `03_centro_horarios_e_contato.pdf` | `3e4382cf-a2b7-4de2-839b-ddb5d13689cf` | `a0ce9248-b660-4889-a8e9-d2db2c398f27` |
| `04_centro_tabela_precos.csv` | `ac859aa2-7253-4de5-886f-589527a834ee` | `6caee752-f6a9-481a-99d6-7ec8f643edd5` |
| `05_centro_promocoes.xlsx` | `8127a2fb-33c6-4e77-8ae5-f493655772d7` | `8dabe4e3-4a46-4ebe-ac1e-4594dee6ceb1` |
| `06_jardins_catalogo_quimica.txt` | `f05c738a-cf88-4cfc-ac8e-60d01efc9be2` | `d9126bb4-5cc4-4757-88dd-12e92ea66733` |
| `07_jardins_faq.docx` | `e5b20922-1e97-4508-8a08-f06a5951f843` | `663736fd-157b-4b94-af6d-22ab6732f44a` |
| `08_jardins_eventos.pdf` | `444ac9fc-2437-4f6d-9326-568de2dda9d5` | `6d15ad67-5e9c-4e9f-8510-448b85405662` |
| `09_jardins_equipe.csv` | `0729f6a4-8e3c-492f-ab6f-b956e3fb7aeb` | `855b856e-17ca-4433-b7c5-435b82742297` |
| `10_jardins_produtos.xlsx` | `f8830430-d166-429d-b4bb-c18b1dd01aa4` | `244df589-781a-43a8-a00d-e14e9dcce70c` |
| `11_moema_barbearia_precos.txt` | `9dd82ed7-97ec-4fa4-814d-a476df8749d4` | `474fc296-bedd-4061-ab79-ef1a03b501f4` |
| `12_moema_regras_pacotes.docx` | `1979f901-b02e-4f49-a743-e91665e231e1` | `d309503b-c63e-4d23-a45a-c6859a2c135b` |
| `13_moema_contato.pdf` | `5d310032-78ae-4e70-8a7b-e57676118fd7` | `79ab4922-2328-4d53-82be-802012525111` |
| `14_moema_agenda.csv` | `daafe447-84f7-4453-903c-9338a6e13779` | `88c4dca6-8ec9-4ea3-b04d-25f155b18cd7` |
| `15_moema_caixa.xlsx` | `e12541eb-cd8f-4f95-b09a-73681a59cba7` | `78c3af60-61b4-4d15-85ec-a0ac5a8ced4a` |
| `16_vila_madalena_excecoes.txt` | `1e8b8f63-0e91-4f15-bb79-a8d7522e30fb` | `112be6ff-788b-4113-a49e-d8e0cf80d489` |
| `17_vila_madalena_injection.docx` | `3b456133-f8dd-4016-9ae0-3008830a1b38` | `8e1edaf6-81e8-4161-ac98-5daac2e56761` |
| `18_vila_madalena_conflito.pdf` | `f762086a-64f2-4053-97a9-5eb12abc8826` | `70fb60da-3186-4ea0-8d97-94cb90d40226` |
| `19_vila_madalena_servicos.csv` | `f743d95c-a090-43cf-8249-29b4643ad4e8` | `48012ebc-3102-4db6-8f4a-4edf62eaf05e` |
| `20_vila_madalena_financeiro.xlsx` | `de80b4fa-760d-4c64-9dcd-ee847603ae04` | `e4080a1b-5bba-4df3-9e9c-f84099f8d785` |

## Notes

- Review/publish actions are automated technical approvals for synthetic data only.
- Semantic correctness still requires comparing extracted content against `examples/pilot_semireal/manifest.json`.
- Unknown queue items are intentionally not auto-resolved.
