# Model Benchmarks

Benchmarks locais para escolher modelos Ollama do piloto.

## Metodo

Fonte de metricas: API `/api/generate` do Ollama.

Campos usados:

```text
total_duration
load_duration
prompt_eval_count
prompt_eval_duration
eval_count
eval_duration
```

Velocidade de geracao:

```text
tokens_per_second = eval_count / eval_duration * 1_000_000_000
```

Comando:

```powershell
python scripts\benchmark\ollama_benchmark.py
```

## Rodada inicial

Relatorios:

```text
.run\ollama-benchmark-initial.json
.run\ollama-benchmark-initial.md
```

Resumo:

| Modelo | Tarefa | JSON ok | Esperado ok | Total s | Output tokens/s | Leitura |
|---|---|---:|---:|---:|---:|---|
| `gemma4:31b` | classification | sim | sim | 80-102 | 3.3-3.6 | Melhor qualidade para classificacao entre testados |
| `glm-4.7-flash:latest` | classification | nao | nao | 12 | 15-16 | Rapido, mas falhou contrato JSON/esperado |
| `qwen3.6:27b` | classification | nao | nao | 38-48 | 2.5 | Falhou contrato |
| `kwangsuklee/Qwen3.5-27B-Claude-4.6-Opus-Reasoning-Distilled-GGUF:latest` | extraction | sim | sim | 98.5 | 2.5 | Correto, mas lento |
| `hf.co/hesamation/Qwen3.6-35B-A3B-Claude-4.6-Opus-Reasoning-Distilled-GGUF:Q4_K_M` | extraction | sim | sim | 102.7 | 7.8 | Correto e gera mais rapido; carga inicial maior |

## Rodadas focadas

Relatorios:

```text
.run\ollama-benchmark-classification-gemma4.json
.run\ollama-benchmark-extraction-27b.json
.run\ollama-benchmark-extraction-35b.json
```

Resultados:

| Modelo | Tarefa | JSON ok | Esperado ok | Total s | Load s | Output tokens/s |
|---|---|---:|---:|---:|---:|---:|
| `gemma4:31b` | classification | sim | sim | 27.5-48.4 | 4.1-25.9 | 3.3 |
| `kwangsuklee/Qwen3.5-27B-Claude-4.6-Opus-Reasoning-Distilled-GGUF:latest` | extraction | sim | sim | 104.2 | 66.7 | 2.5 |
| `hf.co/hesamation/Qwen3.6-35B-A3B-Claude-4.6-Opus-Reasoning-Distilled-GGUF:Q4_K_M` | extraction | sim | sim | 24.5 | 13.7 | 7.8 |

## Recomendacao atual

```dotenv
MODEL_PROVIDER=ollama
CLASSIFICATION_MODEL=gemma4:31b
EXTRACTION_MODEL=hf.co/hesamation/Qwen3.6-35B-A3B-Claude-4.6-Opus-Reasoning-Distilled-GGUF:Q4_K_M
EXTRACTION_MODEL_FALLBACK=kwangsuklee/Qwen3.5-27B-Claude-4.6-Opus-Reasoning-Distilled-GGUF:latest
```

Motivo:

```text
gemma4:31b foi o unico classificador testado que manteve JSON parseavel e resposta esperada.
O modelo 35B de extracao foi correto e mais rapido em geracao no teste focado.
O modelo 27B fica como fallback por ser menor.
```

## Validacao no pipeline completo

Smoke full com Redis real, Supabase real e Ollama local:

```text
Relatorio: .run\smoke-full-pilot-redis-35b.json
Resultado: passed
Tempo aproximado: 2m39s
Modelo de classificacao: gemma4:31b
Modelo de extracao: hf.co/hesamation/Qwen3.6-35B-A3B-Claude-4.6-Opus-Reasoning-Distilled-GGUF:Q4_K_M
```

Comparacao operacional:

```text
Pipeline com 27B de extracao: ~9m30s
Pipeline com 35B de extracao: ~2m39s
```

Decisao operacional:

```text
Manter 35B como EXTRACTION_MODEL principal para o piloto.
Manter 27B como EXTRACTION_MODEL_FALLBACK.
```

## Caveats

Estes resultados medem casos curtos e controlados.

Antes do piloto baseline, repetir com:

```text
1. documentos reais anonimizados
2. 5-10 casos por fact_type
3. modelo ja carregado e modelo frio
4. smoke full apos trocar EXTRACTION_MODEL
```
