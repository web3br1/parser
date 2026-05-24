# SYSTEM_OVERVIEW.md - Visao Geral do Sistema

## O que este sistema faz

Transforma informacoes brutas de empresas em fontes de verdade estruturadas,
validadas por humanos e exportaveis como `context_bundle.v1` para um chatbot ou
runtime externo consumir.

**Problema resolvido:** empresas pequenas tem conhecimento espalhado em PDFs,
planilhas, mensagens e na cabeca do dono. Isso gera atendimento inconsistente,
retrabalho e automacoes frageis.

**Solucao:** uma camada local de organizacao, validacao, publicacao e exportacao
de verdades empresariais. O chatbot vem depois, em outro projeto, como interface
sobre o contexto compilado.

## O que este sistema nao e

- Nao e chatbot.
- Nao e runtime final de conversa.
- Nao e RAG generico sem schema.
- Nao substitui validacao humana em dados criticos.
- Nao e ERP, CRM ou sistema de automacao.

## Fluxo canonico

```text
Input messy
  -> Input quality gate
  -> Normalizacao deterministica
  -> Chunking semantico
  -> Classificacao por chunk
  -> Extracao com schema fixo
  -> Roteamento para fatos, regras ou unknown queue
  -> Validacao humana
  -> published_facts / published_rules
  -> context_bundle.v1 com readiness e hash
  -> Chatbot externo consome o bundle
```

## Separacao de camadas

| Camada | Conteudo | Storage |
|--------|----------|---------|
| Dados brutos | Arquivos originais imutaveis | File storage privado |
| Dados estruturados | Fatos extraidos e validados | PostgreSQL `extracted_facts` |
| Regras | Politicas e condicoes validadas | PostgreSQL `business_rules` |
| Publicados | Conhecimento aprovado, ativo e nao superseded | Views `published_facts` / `published_rules` |
| Readiness | Lacunas, contradicoes e bloqueios de importacao | Consultas de qualidade |
| Export | Bundle deterministico para runtime externo | `context_bundle.v1` |

## Artefato de saida

O principal artefato deste projeto e o Context Bundle:

- `schema_version = "context_bundle.v1"`;
- fontes publicadas;
- fatos publicados;
- regras publicadas;
- evidencias referenciadas;
- readiness (`ready`, `warning`, `blocked`);
- `integrity.bundle_hash` deterministico;
- audit log de exportacao.

O bundle nunca inclui drafts, unknown queue bruta, secrets, bearer tokens, URLs
assinadas, paths locais, prompts crus, stack traces, respostas brutas de
provedor ou conteudo nao publicado.

## Camadas de ingestao por versao

| Versao | Fontes aceitas |
|--------|----------------|
| MVP | Upload manual: PDF textual, DOCX, XLSX, CSV, TXT, texto colado |
| V1 | URL publica controlada e importacao assistida CSV/JSON |
| V2 | Conectores oficiais: Google Sheets, Drive, Business Profile, Instagram, YouTube, WhatsApp Business |
| V3 | Monitoramento continuo de mudanca em fontes externas |

Toda fonte externa passa por quality gate, classificacao de confiabilidade e
validacao humana antes de virar verdade operacional. Nunca ha scraping
irrestrito.

## Confiabilidade de fonte

Cada fonte recebe `source_reliability`, que impacta resolucao de conflitos e
readiness do bundle.

| Tipo | Exemplos | Confiabilidade |
|------|----------|----------------|
| `official_document` | Contrato assinado, politica aprovada | Alta |
| `official_website` | Site institucional | Media-alta |
| `official_api` | Google Business, WhatsApp Business | Media-alta |
| `internal_spreadsheet` | Planilha de precos interna | Media |
| `marketing_content` | Post patrocinado | Media-baixa |
| `social_post` | Instagram organico | Baixa |
| `review` | Google Reviews | Muito baixa |
| `conversation` | DM, WhatsApp | Baixa |

Conflito entre tipos com diferenca de dois ou mais niveis pode ser resolvido
pela fonte superior quando a regra permitir. Mesmo nivel exige revisao humana.

## Versionamento

Toda saida deve ser reproduzivel. Cada fato ou regra armazena:

| Campo | O que versiona |
|-------|----------------|
| `schema_version` | Versao do schema usado na extracao |
| `prompt_version` | Versao/hash do prompt usado |
| `model_provider` / `model_name` | Provedor e modelo de IA |
| `supersedes` / `superseded_by` | Cadeia de substituicao de facts/rules |
| `source_version` | Inteiro incrementado a cada re-upload |

O export registra `context_version`, `bundle_hash` e `audit_logs.action =
'context_bundle.export'`.

## Readiness do bundle

O sistema nao improvisa quando a fonte nao cobre o assunto. Em vez de responder
ao usuario final, ele informa ao consumidor externo se o contexto esta pronto:

| Estado | Uso |
|--------|-----|
| `ready` | O consumidor pode importar como contexto ativo |
| `warning` | Pode importar, mas deve mostrar avisos operacionais |
| `blocked` | Nao deve ativar como contexto de producao |

Bloqueios comuns: ausencia de fontes publicadas, ausencia de registros
publicados, unknowns abertos, contradicoes abertas ou registros publicados sem
proveniancia.

## Nicho inicial

**Generico:** sistema agnostico de nicho por padrao.
**Prioritario no MVP:** estudios de estetica (SP e RJ).

Extensao para outros nichos deve acontecer por schema/configuracao, nao por
alteracao do core.

## Principios nao-negociaveis

1. Sem schema fixo -> nao extrai.
2. Sem validacao humana -> nao publica.
3. Sem audit log versionado -> nao executa.
4. Dado dinamico -> nunca via RAG.
5. Unknown -> fila de revisao, nunca banco estruturado.
6. Fonte externa -> quality gate + confiabilidade + validacao antes de publicar.
7. LLM classifica e extrai; nunca cria verdade sozinho.
8. Todo input e tratado como hostil.
9. Chatbot externo consome contexto; conversa final nao mora neste repo.
