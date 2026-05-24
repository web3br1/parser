# TASK-016 - Docs Canonicalization

Status: done

## Objective

Make the documentation match the current product direction and integration
branch: a local Context Compiler/data extractor that exports compiled context to
an external chatbot project.

## Scope

- Update root and docs indexes to point to Context Bundle, local runtime,
  Docker runtime and current tasks.
- Update start-here docs so implementers understand the chatbot boundary.
- Update MVP scope and decisions so `context_bundle.v1` is an MVP artifact.
- Keep historical task files TASK-001 through TASK-010 as history, and add
  TASK-011 through TASK-016 as the cleanup/productionization plan.
- Remove stale pilot-local references that point to old operation paths.

## Constraints

- Do not rewrite historical docs just to normalize encoding.
- Do not introduce placeholders or speculative commitments.
- Keep docs ASCII-compatible when adding new content.
- Preserve the rule that LLMs classify/extract but never create operational
  truth without schema, validation and audit log.

## Verification

```powershell
rg -n "TB[D]|implement late[r]|fill in detail[s]" README.md docs tasks
uv run --cache-dir .uv-cache python scripts\ci\secret_scan.py
```
