# Source Pack Compiler Runbook

The source pack compiler turns a normalized upload folder into a strict
`context_bundle.v1` artifact.

Canonical test pack:

```powershell
C:\tmp\context-builder-sources\compounding-pharmacy-gold
```

Default output:

```powershell
C:\tmp\context-builder-sources\compounding-pharmacy-gold\compounding-pharmacy-gold.context_bundle.v1.json
```

## Process

1. Detect a source pack by looking for `00_source_manifest.md`.
2. Parse manifest front matter, official references and document roles.
3. Register every numbered source file as a published source.
4. Extract citable evidence from CSV rows and Markdown sections.
5. Compile facts, rules, gaps, tests, memory policy and tool recommendations.
6. Sanitize forbidden transport data before export.
7. Validate the artifact as `ContextBundleResponse`.
8. Compute `integrity.bundle_hash` with `json.sort_keys.compact.v1`.

`README.md` is package documentation and is not counted as a numbered source.
The current gold pack has 64 numbered source files plus manifest and README.

## Commands

Write the bundle:

```powershell
uv run --cache-dir .uv-cache python scripts\source_pack\compile_context_bundle.py C:\tmp\context-builder-sources\compounding-pharmacy-gold
```

Write to an explicit path:

```powershell
uv run --cache-dir .uv-cache python scripts\source_pack\compile_context_bundle.py C:\tmp\context-builder-sources\compounding-pharmacy-gold --output C:\tmp\context-builder-sources\compounding-pharmacy-gold\compounding-pharmacy-gold.context_bundle.v1.json
```

Check whether the existing output is current:

```powershell
uv run --cache-dir .uv-cache python scripts\source_pack\compile_context_bundle.py C:\tmp\context-builder-sources\compounding-pharmacy-gold --check
```

Run compiler tests:

```powershell
uv run --cache-dir .uv-cache pytest packages\source_pack\tests tests\compat\test_compounding_pharmacy_source_pack_compiler.py -q
```

## Upload UX

The end user should not manually create manifest-aware commands. In the product
flow, folder or zip upload should first run source-pack preflight:

- if `00_source_manifest.md` exists and numbered files match manifest roles,
  treat the upload as a source pack and compile as a package;
- if no manifest exists, fall back to normal per-file ingest;
- if the manifest is present but incomplete, stop before compile and show the
  missing files or invalid roles.

This compiler is the backend primitive for that future upload UX.
