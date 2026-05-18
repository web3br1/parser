# Dataset Adversarial

Dataset mínimo exigido para QA do MVP.

## Estrutura Esperada

| Pasta | Quantidade | Objetivo |
|-------|------------|----------|
| `good/` | 10 | Documentos processáveis com fatos claros |
| `bad_quality/` | 5 | Documentos ruins que devem falhar no quality gate |
| `conflicting/` | 5 | Fontes com valores conflitantes |
| `injection/` | 5 | Tentativas explícitas de prompt injection |
| `broken_spreadsheets/` | 5 | CSV/XLSX com headers ruins, células mescladas ou linhas quebradas |

## Regra

Cada caso deve ter:

```text
input.*
expected.json
notes.md
```

Os exemplos podem ser sintéticos, mas precisam preservar os riscos reais do pipeline.
