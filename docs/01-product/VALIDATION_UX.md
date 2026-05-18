# VALIDATION_UX.md — UX de Validação Humana

## Problema central

O dono de PME não vai validar 300 fatos extraídos de PDF um a um.
Se a UX de validação for uma fila de cards de aprovação sem contexto, ele abandona na segunda sessão.
Sem validação, o sistema nunca vira fonte confiável. O produto colapsa.

---

## Princípios de UX de validação

1. **Contexto sempre visível:** mostrar o trecho original do documento ao lado do fato extraído
2. **Ação em 1 clique:** aprovar deve ser o caminho mais fácil
3. **Agrupamento inteligente:** mostrar fatos do mesmo tipo juntos (todos os preços, todos os horários)
4. **Priorização:** fatos com ambiguidades detectadas aparecem primeiro
5. **Progresso visível:** "8 de 23 fatos validados neste documento"

---

## Fluxo de validação por bloco

```
Card de validação mostra:
  ┌─────────────────────────────────────────┐
  │ TRECHO ORIGINAL:                        │
  │ "Atendemos de segunda a sexta das 9h    │
  │  às 18h, exceto feriados."              │
  │                                         │
  │ EXTRAÍDO:                               │
  │ Horário: seg-sex, 09:00 às 18:00        │
  │ Exceção: feriados                       │
  │                                         │
  │ [✓ Aprovar]  [✎ Editar]  [✗ Rejeitar]  │
  └─────────────────────────────────────────┘
```

---

## Tratamento de ambiguidades

Quando o sistema detectar campo vago, mostrar ao usuário:

```
  ┌─────────────────────────────────────────┐
  │ TRECHO: "Clientes antigos têm desconto  │
  │  no Pix."                               │
  │                                         │
  │ ⚠️ PRECISAMOS DE MAIS INFORMAÇÃO:       │
  │                                         │
  │ 1. O que define "cliente antigo"?       │
  │    [__________________________]         │
  │                                         │
  │ 2. Qual o percentual de desconto?       │
  │    [__________________________]         │
  │                                         │
  │ 3. Quem aprova o desconto?              │
  │    [__________________________]         │
  │                                         │
  │ [Salvar e aprovar]  [Ignorar por agora] │
  └─────────────────────────────────────────┘
```

---

## Mensagens de estado para o usuário

| Situação | Mensagem |
|----------|----------|
| Dado aprovado usado | (sem aviso — comportamento normal) |
| Dado não validado disponível | "Encontrei uma informação ainda não validada. Confirmar antes de usar?" |
| Nenhum dado aprovado | "Ainda não temos essa informação validada no sistema." |
| Itens na unknown queue | "Encontramos X trechos ainda não classificados para sua revisão." |
| Contradição detectada | "Identificamos um conflito entre dois documentos. Sua revisão é necessária." |

---

## O que não fazer na UX de validação

- Não mostrar JSON bruto para o usuário
- Não pedir aprovação sem mostrar o trecho original
- Não bloquear o sistema enquanto há itens pendentes (validação é assíncrona)
- Não misturar fatos de tipos diferentes na mesma tela de validação em lote

