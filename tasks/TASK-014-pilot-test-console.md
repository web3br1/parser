# TASK-014 - Pilot Test Console

Status: done

## Objective

Add a focused internal Pilot Test console so operators can exercise the local
extractor flow without turning this project into the chatbot product.

## Scope

- Add `/workspaces/[workspaceId]/pilot-test` route in the web console.
- Add a client Pilot Test component with source draft, flow status, readiness
  cards and explicit run controls.
- Keep flow logic testable outside React.
- Add the route to the workspace navigation.
- Include the route in frontend smoke checks.

## Constraints

- The console is an operator tool, not the end-user chatbot.
- UI must not expose provider secrets, raw prompts, raw tool JSON, private
  filesystem paths, stack traces or imported source content outside focused
  review surfaces.
- Temporary test artifacts must be cleaned up even when the test command fails.

## Verification

```powershell
corepack pnpm --filter @context-builder/web pilot-flow:test
corepack pnpm --filter @context-builder/web typecheck
corepack pnpm --filter @context-builder/web build
node scripts\smoke\frontend_console_smoke.mjs --fetch-only
```

Implemented in commit `c05e345`.
