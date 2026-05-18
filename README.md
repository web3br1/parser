# Parser

Sistema para transformar conhecimento bruto de empresas em fatos e regras estruturados, validados por humanos e consultaveis por IA.

## Como navegar

Comece por [docs/00-start-here/CLAUDE.md](docs/00-start-here/CLAUDE.md). Ele e o indice operacional para qualquer implementacao.

Leitura rapida:

1. [Decisoes fechadas do MVP](docs/00-start-here/MVP_DECISIONS.md)
2. [Visao geral do sistema](docs/00-start-here/SYSTEM_OVERVIEW.md)
3. [Escopo do MVP](docs/01-product/MVP_SCOPE.md)
4. [Pipeline tecnico](docs/03-pipeline/PIPELINE.md)
5. [Modelo de dados](docs/04-data/DATA_MODEL.md)
6. [Criterios de aceite](docs/07-qa/ACCEPTANCE_CRITERIA.md)

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
| `examples` | Exemplos JSON esperados |
| `prototype` | Wireframe HTML |
| `supabase` | Migrations iniciais PostgreSQL/Supabase |
| `backend` | Contratos Python iniciais: Pydantic schemas e normalização determinística |

## Regra central

O LLM pode interpretar. Nunca pode criar verdade operacional sem schema, validacao humana e audit log estruturado.

