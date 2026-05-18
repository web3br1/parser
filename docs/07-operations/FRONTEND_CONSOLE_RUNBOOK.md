# FRONTEND_CONSOLE_RUNBOOK.md — Internal Web Console

## Scope

The console is an internal operator surface for the MVP workflow:

1. Select or create a workspace.
2. Upload sources.
3. Monitor source/job state.
4. Review extracted facts and rules.
5. Resolve unknown items.
6. Query published knowledge.
7. Create auditable privacy requests.

It is not a customer-facing chatbot, CRM, or external automation surface.

## Start

```powershell
corepack pnpm --filter @context-builder/web dev --hostname 127.0.0.1 --port 3000
```

Open:

```text
http://127.0.0.1:3000/login
```

Paste an operator JWT. The browser stores it in `sessionStorage`; never paste a service-role key.

## Routes

| Route | Purpose |
|---|---|
| `/workspaces` | List/create workspaces available to the token |
| `/workspaces/{workspaceId}` | Operational dashboard |
| `/workspaces/{workspaceId}/sources` | Upload and list sources |
| `/workspaces/{workspaceId}/sources/{sourceId}` | Source metadata and latest ingest job |
| `/workspaces/{workspaceId}/review` | Chunk-based human review and publish flow |
| `/workspaces/{workspaceId}/unknown` | Reclassify or ignore unclassified items |
| `/workspaces/{workspaceId}/query` | Auditable query against published knowledge |
| `/workspaces/{workspaceId}/knowledge` | Placeholder until published-record list endpoint exists |
| `/workspaces/{workspaceId}/settings` | Owner-only privacy export/delete request controls |

## Verification

Run before a pilot demo:

```powershell
corepack pnpm --filter @context-builder/web typecheck
corepack pnpm --filter @context-builder/web build
```

Smoke the main routes with hard per-route timeouts:

```powershell
node scripts\smoke\frontend_console_smoke.mjs
```

To smoke an already-running server:

```powershell
node scripts\smoke\frontend_console_smoke.mjs --base-url http://127.0.0.1:3000
```

If the local automation sandbox blocks process spawning, start the server manually and use `--base-url`.

The default route set is:

```text
/workspaces/demo
/workspaces/demo/sources
/workspaces/demo/review
/workspaces/demo/unknown
/workspaces/demo/query
/workspaces/demo/knowledge
/workspaces/demo/settings
```

## Known Placeholders

- Knowledge Base browsing needs a backend endpoint for published facts/rules.
- Settings shows privacy request creation only; real deletion execution remains backend-controlled and auditable.
- Workspace dashboard uses lightweight counts from existing workflow endpoints, not a dedicated metrics endpoint.
