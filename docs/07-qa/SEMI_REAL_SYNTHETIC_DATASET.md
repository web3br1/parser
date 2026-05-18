# Semi-Real Synthetic Dataset

Dataset controlado para validar qualidade semantica do piloto, alem dos smokes tecnicos.

## Localizacao

- Gerador: `scripts/pilot/generate_semireal_documents.py`
- Arquivos: `examples/pilot_semireal/`
- Manifesto de expectativas: `examples/pilot_semireal/manifest.json`

## Composicao

- 20 documentos sinteticos ricos, mantidos em quantidade fixa para comparacao entre rodadas.
- Aproximadamente 11,6k caracteres extraidos pelos parsers locais na versao atual.
- 5 formatos suportados pelo MVP:
  - TXT: 4 arquivos
  - DOCX: 4 arquivos
  - PDF: 4 arquivos
  - CSV: 4 arquivos
  - XLSX: 4 arquivos
- 4 unidades ficticias:
  - Centro
  - Jardins
  - Moema
  - Vila Madalena

## Cobertura Semantica

O dataset cobre:

- precos de servicos;
- horarios de funcionamento;
- contatos e enderecos;
- meios de pagamento;
- regras de desconto;
- politica de cancelamento;
- FAQ;
- disponibilidade por profissional;
- servicos suspensos;
- conflito entre documentos;
- prompt injection embutido.
- regras expiradas ou descontinuadas;
- excecoes temporais com datas;
- contatos e meios de pagamento obsoletos;
- itens em piloto que exigem revisao manual;
- produtos que testam over-generalization como preco de servico.

## Regeneracao

```powershell
$env:UV_CACHE_DIR='.uv-cache'
uv run python scripts\pilot\generate_semireal_documents.py
```

## Validacao Local

```powershell
$env:UV_CACHE_DIR='.uv-cache'
uv run pytest tests\smoke\test_semireal_documents.py -q
uv run ruff check scripts\pilot\generate_semireal_documents.py tests\smoke\test_semireal_documents.py
```

Antes de rodar o piloto semi-real, todos os documentos devem ser aceitos pelos parsers locais.
