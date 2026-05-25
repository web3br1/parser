# Decisoes Pendentes

Todas as decisoes pendentes foram fechadas em 2026-05-12. Este arquivo fica
apenas como ponte para evitar links quebrados.

A documentacao operacional canonica esta em:

```text
docs/operations/
```

`docs/07-operations/` foi removido na limpeza SDD porque duplicava runbooks e
mantinha orientacoes antigas de stack local via PowerShell.

Resumo:

```text
D-001 a D-023: decided
C-001 a C-003: decided
```

Decisao tecnica mais relevante para implementacao imediata:

```text
D-008: workers usam modelos locais via Ollama por padrao.
MODEL_PROVIDER=ollama
OLLAMA_BASE_URL=http://localhost:11434
CLASSIFICATION_MODEL=gemma4:31b
EXTRACTION_MODEL=hf.co/hesamation/Qwen3.6-35B-A3B-Claude-4.6-Opus-Reasoning-Distilled-GGUF:Q4_K_M
```
