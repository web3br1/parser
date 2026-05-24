# Parser

Sistema local para transformar conhecimento bruto de empresas em fatos e regras
estruturados, validados por humanos e exportaveis como contexto confiavel.

Este repositorio e o Context Compiler: ele prepara conhecimento validado e
exporta `context_bundle.v1` para um projeto externo de chatbot consumir. O
chatbot final nao faz parte deste projeto.

## Como navegar

Comece por [docs/00-start-here/CLAUDE.md](docs/00-start-here/CLAUDE.md). Ele e o indice operacional para qualquer implementacao.

Leitura rapida:

1. [Decisoes fechadas do MVP](docs/00-start-here/MVP_DECISIONS.md)
2. [Visao geral do sistema](docs/00-start-here/SYSTEM_OVERVIEW.md)
3. [Escopo do MVP](docs/01-product/MVP_SCOPE.md)
4. [Pipeline tecnico](docs/03-pipeline/PIPELINE.md)
5. [Context Bundle Export](docs/03-pipeline/CONTEXT_BUNDLE.md)
6. [Runtime local](docs/operations/LOCAL_RUNTIME.md)
7. [Docker local runtime](docs/operations/DOCKER_LOCAL_RUNTIME.md)
8. [Modelo de dados](docs/04-data/DATA_MODEL.md)
9. [Criterios de aceite](docs/07-qa/ACCEPTANCE_CRITERIA.md)

## Estrutura

| Pasta | Conteudo |
|-------|----------|
| `docs/00-start-here` | Entrada principal e visao geral |
| `docs/01-product` | ICP, escopo, fluxos de usuario e UX de validacao |
| `docs/02-architecture` | Arquitetura complementar e gateway de conectores |
| `docs/03-pipeline` | Fluxos tecnicos e contratos de entrada/saida |
| `docs/04-data` | Modelo de dados e registry de schemas |
| `docs/05-security` | Seguranca, RLS e isolamento multi-tenant |
| `docs/06-prompts` | Prompts de classificacao, extracao e avaliacao |
| `docs/07-qa` | Criterios de aceite e casos de teste |
| `docs/08-ops` | Observabilidade e regras de rejeicao |
| `docs/operations` | Runtime local, Docker local e smoke runbooks |
| `tasks` | Plano incremental de entrega e limpeza |
| `examples` | Exemplos JSON esperados |
| `prototype` | Wireframe HTML |
| `supabase` | Migrations iniciais PostgreSQL/Supabase |
| `backend` | Contratos Python iniciais: Pydantic schemas e normalização determinística |

## Artefato principal

O artefato que sobra para o chatbot externo e o `context_bundle.v1`: um JSON
deterministico com fontes publicadas, fatos publicados, regras publicadas,
evidencias referenciadas, readiness e hash de integridade. Ele nunca inclui
conteudo em rascunho, secrets, prompts crus, paths locais, stack traces ou
respostas brutas de provedor.

## Runtime local

Para desenvolvimento e piloto local, use Docker como runtime reproduzivel:

```bash
docker compose up --build
```

Os smoke scripts validam uma stack ja em execucao; eles nao iniciam nem param
servicos locais. Veja `docs/operations/LOCAL_RUNTIME.md` e
`docs/operations/DOCKER_LOCAL_RUNTIME.md`.

## Regra central

O LLM interno pode classificar e extrair. Nunca pode criar verdade operacional
sem schema, validacao humana e audit log estruturado. Interpretacao
conversacional pertence ao chatbot externo que consome o bundle.

