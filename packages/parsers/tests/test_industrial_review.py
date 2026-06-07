from parsers.industrial_review import build_review_packets, summarize_review_packets


def test_missing_metadata_review_packet() -> None:
    packets = build_review_packets(
        document_id="pop-qa-014",
        metadata={"gap_codes": ["missing_revision"]},
    )

    assert len(packets) == 1
    assert packets[0].packet_id == "pop-qa-014:missing_metadata:missing_revision"
    assert packets[0].reason_code == "missing_metadata"
    assert packets[0].severity == "high"
    assert packets[0].suggested_decision == "fill_missing_metadata"
    assert packets[0].evidence[0]["risk_code"] == "missing_revision"


def test_revision_conflict_packet() -> None:
    packets = build_review_packets(
        document_id="pop-qa-014",
        revision_conflicts=[
            {
                "document_code": "POP-QA-014",
                "revision": "04",
                "quote": "Rev. 04 aparece em duas familias.",
            }
        ],
    )

    assert packets[0].reason_code == "revision_family_conflict"
    assert packets[0].evidence[0]["quote"] == "Rev. 04 aparece em duas familias."


def test_ambiguous_section_packet() -> None:
    packets = build_review_packets(
        document_id="pop-qa-014",
        section_diagnostics={
            "risk_codes": ["ambiguous_section_heading"],
            "section_spans": [
                {
                    "section_path": "1.1",
                    "section_title": "Aplicacao",
                    "page_start": 2,
                    "risk_codes": ["section_hierarchy_gap"],
                }
            ],
        },
    )

    assert [packet.reason_code for packet in packets] == [
        "ambiguous_section_hierarchy",
        "ambiguous_section_hierarchy",
    ]
    localized = [packet for packet in packets if packet.section_path == "1.1"][0]
    assert localized.evidence[0]["page_number"] == 2


def test_low_confidence_semantic_units_are_grouped_by_section() -> None:
    packets = build_review_packets(
        document_id="pop-qa-014",
        semantic_candidates=[
            {
                "kind": "requirement",
                "confidence": 0.51,
                "evidence": {
                    "quote": "Deve validar.",
                    "section_path": "5",
                    "page_start": 4,
                },
            },
            {
                "kind": "procedure_step",
                "confidence": 0.55,
                "evidence": {
                    "quote": "1. Validar registro.",
                    "section_path": "5",
                    "page_start": 4,
                },
            },
        ],
    )

    assert len(packets) == 1
    assert packets[0].packet_id == "pop-qa-014:low_confidence_semantic_unit:5"
    assert len(packets[0].evidence) == 2


def test_table_figure_risk_packet() -> None:
    packets = build_review_packets(
        document_id="pop-qa-014",
        table_figure_candidates=[
            {
                "kind": "visual_risk",
                "page_number": 8,
                "quote": "page 8 contains visual content without extractable caption",
                "risk_codes": ["visual_content_without_caption"],
            }
        ],
    )

    assert packets[0].reason_code == "visual_table_figure_risk"
    assert packets[0].suggested_decision == "inspect_visual_evidence"


def test_summarizes_review_packets_by_reason() -> None:
    packets = build_review_packets(
        document_id="pop-qa-014",
        metadata={"gap_codes": ["missing_revision"]},
        table_figure_candidates=[
            {"kind": "visual_risk", "page_number": 8, "risk_codes": ["visual_content_without_caption"]}
        ],
    )

    summary = summarize_review_packets(packets)

    assert summary["total_packet_count"] == 2
    assert summary["reason_code_counts"] == {
        "missing_metadata": 1,
        "visual_table_figure_risk": 1,
    }
