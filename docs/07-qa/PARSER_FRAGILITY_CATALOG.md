# Parser Fragility Catalog

Status: active catalog seed
Date: 2026-06-06

## Purpose

This catalog names parser failure hypotheses before new implementation work
starts. Each entry is small enough to reproduce, severe enough to prioritize
and concrete enough to become a red test. It treats raw input as hostile until
parser evidence, diagnostics and review signals prove otherwise.

The catalog is independent from Hermes, Tri-Memory, agent memory, runtime app,
UI, OCR, LLM adjudication and benchmark scoring flows.

## Fragility Record Format

| fragility_id | affected_layer | severity | failure_hypothesis | minimal_reproducer_idea | expected_red_test | expected_negative_adversarial_assertion | expected_benchmark_signal | current_status |
|---|---|---|---|---|---|---|---|---|
| fragility_id | Stable identifier such as PF-001 | Required | One sentence describing the unsafe parser behavior | Small fixture shape that can reproduce the behavior | Planned pytest path and test function | Assertion that blocks unsafe promotion or noisy review output | Benchmark field that should later move when the fragility is fixed | One allowed status |
| affected_layer | Parser layer or report surface most likely to expose the issue | Required | Keep the hypothesis scoped to that layer | Prefer deterministic text or generated PDF fixtures | Use smoke, parser, or adversarial tests | Include the negative condition, not only a positive expectation | Use diagnostic report names, not success theater | One allowed status |
| severity | One allowed severity value | Required | Rank publication, review and diagnostic risk | Fixture should be minimal enough for TDD | Target a red test that can fail before implementation | Assertion must catch overclaim, miss, drift or duplicate noise | Signal must remain diagnostic rather than a pass claim | One allowed status |
| failure_hypothesis | Concrete statement of what can go wrong | Required | Avoid generic quality goals | Include source text shape and parser mistake | Name the future failing test | Include at least one assert-style negative check | Name the metric or JSON field affected | One allowed status |
| minimal_reproducer_idea | Smallest useful fixture idea | Required | Fixture should isolate one failure mode | Avoid real private PDFs | Path can point to future adversarial tests | Assertion should be inspectable without external services | Signal should be observable in benchmark JSON | One allowed status |
| expected_red_test | Future red test target | Required | Test should fail for the named behavior only | Prefer deterministic parser fixtures | Start with a repository test path | Negative assertion should verify absence of unsafe output | Signal should be stable enough for trend review | One allowed status |
| expected_negative_adversarial_assertion | Required negative or adversarial assertion | Required | Must reject false promotion, false cleanliness, drift or noisy packets | Assertion should mention the unsafe output that must not appear | Keep it as a testable condition | Use assert wording so reviewers can translate directly | Link to diagnostic field that should expose the risk | One allowed status |
| expected_benchmark_signal | Diagnostic signal to influence later | Required | This is not a scoring claim | Signal can be current or planned benchmark JSON field | Use names under benchmark dot notation | Signal must help locate the risk later | Avoid vanity metrics | One allowed status |
| current_status | Lifecycle state for this fragility | Required | Status changes only after test, fix or benchmark evidence | Start new hypotheses as discovered | Use only allowed values below | Reviewers may reject vague or untestable status moves | Benchmark evidence is required before benchmarked | One allowed status |

## Allowed Statuses

| status | Meaning |
|---|---|
| discovered | Hypothesis is cataloged and ready to become a red test. |
| red_test_written | A red test exists and fails for the expected reason. |
| fixed | Parser behavior changed and the red test is green. |
| benchmarked | Benchmark diagnostics were rerun and the signal was recorded. |
| accepted | Risk is accepted with evidence and product approval. |
| known_limit | Current architecture cannot address it without a later scoped task. |

## Allowed Severities

| severity | Meaning |
|---|---|
| critical_publication_risk | Could publish or approve a false fact, false evidence or false source claim. |
| high_review_risk | Could misroute human review or hide a material parser uncertainty. |
| medium_quality_risk | Could create repeatable quality loss, noisy packets or weak diagnostics. |
| low_diagnostic_risk | Could reduce observability without directly changing extracted truth. |

## Seed Fragilities

| fragility_id | affected_layer | severity | failure_hypothesis | minimal_reproducer_idea | expected_red_test | expected_negative_adversarial_assertion | expected_benchmark_signal | current_status |
|---|---|---|---|---|---|---|---|---|
| PF-001 | metadata_extraction | critical_publication_risk | A book-like or nested multi-document PDF references several POP codes and the parser promotes a nested section code as the file-level document_code. | Text fixture titled Compilado de POPs with TOC lines for POP 101 and POP 102 plus body sections for each nested POP. | tests/adversarial/test_parser_metadata_overclaim.py::test_nested_pop_code_is_not_file_metadata | assert result.metadata.get("document_code") is None and "missing_document_code" in result.metadata["gap_codes"] | benchmark.metadata_gap_codes.missing_document_code and benchmark.review_packet_reason_counts.missing_metadata | discovered |
| PF-002 | semantic_unit_extraction | high_review_risk | Table of contents lines containing normative verbs are promoted as requirement candidates even though they are only navigation text. | Sumario section with dot leaders such as 5.2 Deve registrar incidentes followed by page numbers and no matching body rule. | tests/adversarial/test_parser_semantics_overclaim.py::test_toc_normative_line_is_not_requirement | assert all(candidate.kind != "requirement" for candidate in candidates if candidate.evidence.section_title == "Sumario") | benchmark.semantic_candidate_false_positive_rate and benchmark.semantic_candidate_kind_counts.requirement | discovered |
| PF-003 | section_resolver | high_review_risk | Recurring headers or footers containing procedural words contaminate body sections and become standalone chunks or semantic candidates. | Three-page text fixture with the same header Toda NC deve ser registrada and distinct body sections on each page. | tests/adversarial/test_parser_boilerplate_contamination.py::test_repeated_header_is_boilerplate_not_body_section | assert header_quote not in [chunk.text for chunk in chunks] and assert not any(candidate.evidence.quote == header_quote for candidate in semantic_candidates) | benchmark.section_diagnostics.boilerplate_counts and benchmark.chunk_diagnostics.structure_risk_counts | discovered |
| PF-004 | table_figure_understanding | critical_publication_risk | Figure references are described as visual understanding when the parser only has caption or reference text and has not inspected pixels. | PDF page with embedded image, sparse text and Figura 3 reference without an explanatory caption. | tests/adversarial/test_parser_visual_overclaim.py::test_figure_reference_without_caption_stays_visual_risk | assert all(candidate.kind in {"figure_reference", "visual_risk"} for candidate in table_figure_candidates) | benchmark.table_figure_risk_counts.visual_content_without_caption and benchmark.review_packet_reason_counts.visual_table_figure_risk | discovered |
| PF-005 | review_packet_grouping | medium_quality_risk | Section hierarchy gaps create one review packet per affected chunk instead of a grouped packet that a human can resolve once. | Fixture with many 5.2 style subsections and no parent 5 section, producing repeated section_hierarchy_gap risks. | tests/adversarial/test_parser_review_noise.py::test_section_hierarchy_gap_packets_are_grouped | assert review_packet_reason_counts["ambiguous_section_hierarchy"] <= unique_ambiguous_section_paths | benchmark.review_packet_count and benchmark.review_packet_reason_counts.ambiguous_section_hierarchy | discovered |
| PF-006 | evidence_integrity | critical_publication_risk | Evidence quotes or page spans drift so a candidate points to text that is absent from the claimed source page. | Two-page fixture with duplicate requirement wording on page 2 and page 7 plus one page-specific qualifier. | tests/adversarial/test_parser_evidence_integrity.py::test_candidate_quote_and_page_span_match_source_page | assert candidate.evidence.quote in source_text_by_page[candidate.evidence.page_start] | benchmark.evidence_drift_count and benchmark.semantic_candidate_count | discovered |
| PF-007 | page_profile_quality_gate | high_review_risk | OCR-required image-only pages pass as clean text extraction and downstream layers treat missing text as a complete parse. | Tiny generated PDF with one image-only page and no extractable text layer. | tests/adversarial/test_parser_ocr_routing.py::test_image_only_page_requires_ocr_and_blocks_clean_text_claim | assert "ocr_required" in page_profile.risk_codes and assert document_quality.passed is False | benchmark.page_profile_summary.ocr_required_pages and benchmark.quality_failed_count | discovered |
| PF-008 | split_fallback_diagnostics | medium_quality_risk | Large PDF split fallback preserves extracted text but loses per-range page profiles, section diagnostics or parser error details. | Stress surrogate above the single-parser page cap with one OCR-risk page and one section gap in the second range. | tests/adversarial/test_parser_split_fallback_diagnostics.py::test_split_fallback_preserves_range_diagnostics | assert split_summary["page_profile_summary"]["page_count"] > 0 and assert split_summary["section_diagnostics"]["summary"]["section_count"] > 0 | benchmark.split_processed_count and benchmark.split_fallback_diagnostic_loss_count | discovered |

## Source Task Context

These seeds come from the TASK-024 through TASK-031 parser work:

- TASK-024 established the dirty-document benchmark and split fallback stress
  case.
- TASK-025 exposed metadata overclaim risk for nested document collections.
- TASK-026 added page profiling, OCR routing signals and diagnostic summaries.
- TASK-027 added recurring header/footer and section hierarchy diagnostics.
- TASK-028 added section-aware chunk metadata.
- TASK-029 added deterministic semantic unit candidates and TOC false-positive
  pressure.
- TASK-030 added table, figure and visual-risk candidates without OCR or vision.
- TASK-031 added review packet grouping and evidence fields.

## Lifecycle Rule

Move a fragility out of `discovered` only with evidence:

- `red_test_written`: include the failing command and failure reason.
- `fixed`: include the passing test command.
- `benchmarked`: include the benchmark command and signal delta.
- `accepted` or `known_limit`: include reviewer or product approval context.
