# Context Bundle Cross-Repo Handoff

This guide defines the handoff from the Parser upstream project to the runtime
chatbot/importer project.

```text
Parser
  reviewed facts/rules/evidence/tests
  -> context_bundle.v1 fixtures/export

Runtime app
  context_bundle.v1
  -> schema/hash/security validation
  -> dry-run import
  -> RAG/Graph import
  -> context tests
  -> publish
```

## Upstream Commands

Check that the committed JSON Schema still matches the Pydantic contract:

```powershell
uv run --cache-dir .uv-cache python scripts\context_bundle\export_json_schema.py --check
```

Check that committed fixtures still match the production bundle service:

```powershell
uv run --cache-dir .uv-cache python scripts\context_bundle\export_golden_bundle.py --check
```

Check that the committed contract manifest still matches the schema and
fixtures:

```powershell
uv run --cache-dir .uv-cache python scripts\context_bundle\export_contract_manifest.py --check
```

Regenerate both fixtures after an intentional contract change:

```powershell
uv run --cache-dir .uv-cache python scripts\context_bundle\export_golden_bundle.py
```

Regenerate the JSON Schema after an intentional contract change:

```powershell
uv run --cache-dir .uv-cache python scripts\context_bundle\export_json_schema.py
```

Regenerate the contract manifest after schema or fixture regeneration:

```powershell
uv run --cache-dir .uv-cache python scripts\context_bundle\export_contract_manifest.py
```

Generate only the ready fixture into a temporary handoff directory:

```powershell
uv run --cache-dir .uv-cache python scripts\context_bundle\export_golden_bundle.py --variant golden --output-dir C:\tmp\context-bundle-handoff
```

The canonical fixture files are:

- `examples/context_bundle/context-bundle.v1.schema.json`
- `examples/context_bundle/golden-context-bundle.v1.json`
- `examples/context_bundle/blocked-context-bundle.v1.json`
- `examples/context_bundle/context-bundle-contract.v1.manifest.json`

## Runtime Importer Expectations

The runtime importer should validate the manifest and bundle before any
mutation:

- The contract manifest should match the copied schema and fixture artifact
  hashes before the runtime accepts a synchronized handoff package.
- The manifest should come from a trusted commit, tag, pinned digest or signed
  release. It proves consistency between files, not authenticity of an
  untrusted package.
- `checks.command` values are informational allowlist entries for CI; the
  runtime must not execute arbitrary commands from manifest JSON.
- `schema_version` must equal `context_bundle.v1`.
- The top-level envelope and nested contract objects must reject unknown fields.
- `integrity.bundle_hash` must match the public payload with `generated_at`
  replaced by `stable-for-hash`.
- `context_version` must equal `ctx_{first_12_hex_chars_of_bundle_hash}`.
- Integrity counts must equal the actual array lengths.
- `readiness.status = "blocked"` must prevent active publish.
- Security scanning must reject bearer tokens, API-key shaped values, signed URL
  markers, private local paths, raw prompts, provider responses and stack traces.

## Compatibility Gate

Parser-side compatibility gate:

```powershell
uv run --cache-dir .uv-cache pytest tests\compat -q
uv run --cache-dir .uv-cache python scripts\context_bundle\export_json_schema.py --check
uv run --cache-dir .uv-cache python scripts\context_bundle\export_golden_bundle.py --check
uv run --cache-dir .uv-cache python scripts\context_bundle\export_contract_manifest.py --check
uv run --cache-dir .uv-cache python scripts\ci\secret_scan.py
```

The canonical artifact order is schema, fixtures, manifest, then secret scan.
The runtime should verify manifest hashes from a trusted upstream revision
before copying the synchronized schema and fixture artifacts into its own
validator tests.

Runtime-side compatibility gate:

```bash
npm run typecheck
npm run test -- tests/context-bundle
```

The first runtime slice should copy the upstream golden fixture into the runtime
repo and validate it without writing to RAG, graph or active bot config.

## Change Rules

Contract changes are allowed only when they preserve this sequence:

1. Update the Pydantic contract and service projection.
2. Regenerate the JSON Schema with `export_json_schema.py`.
3. Regenerate fixtures with `export_golden_bundle.py`.
4. Regenerate the contract manifest with `export_contract_manifest.py`.
5. Run Parser compatibility tests and secret scan.
6. Update the runtime validator/hash tests with the new schema, fixtures and
   manifest.
7. Keep both repos accepting the same `context_bundle.v1` artifact before
   release.
