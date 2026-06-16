from domain.industrial_revision import resolve_revision_family


def test_highest_revision_is_vigent_when_no_conflict() -> None:
    result = resolve_revision_family(
        [
            {
                "document_code": "POP-QA-014",
                "revision": "03",
                "status": "obsolete",
                "content_hash": "a",
            },
            {
                "document_code": "POP-QA-014",
                "revision": "04",
                "status": "approved",
                "content_hash": "b",
            },
        ],
    )

    assert result.family_key == "POP-QA-014"
    assert result.candidate_revision == "04"
    assert result.vigent_revision == "04"
    assert result.blocking_gap_codes == []


def test_document_code_is_normalized_before_grouping() -> None:
    result = resolve_revision_family(
        [
            {
                "document_code": " pop qa 014 ",
                "revision": "03",
                "status": "obsolete",
                "content_hash": "a",
            },
            {
                "document_code": "POP-QA-014",
                "revision": "04",
                "status": "approved",
                "content_hash": "b",
            },
        ],
    )

    assert result.family_key == "POP-QA-014"
    assert result.candidate_revision == "04"
    assert result.vigent_revision == "04"


def test_missing_revision_blocks_family() -> None:
    result = resolve_revision_family(
        [
            {
                "document_code": "POP-QA-014",
                "revision": "",
                "status": "approved",
                "content_hash": "a",
            },
        ],
    )

    assert result.vigent_revision is None
    assert "missing_revision" in result.blocking_gap_codes


def test_same_revision_different_hash_blocks() -> None:
    result = resolve_revision_family(
        [
            {
                "document_code": "POP-QA-014",
                "revision": "04",
                "status": "approved",
                "content_hash": "a",
            },
            {
                "document_code": "POP-QA-014",
                "revision": "04",
                "status": "approved",
                "content_hash": "b",
            },
        ],
    )

    assert result.vigent_revision is None
    assert "duplicate_revision_conflict" in result.blocking_gap_codes


def test_multiple_approved_revisions_without_obsolete_block_as_ambiguous() -> None:
    result = resolve_revision_family(
        [
            {
                "document_code": "POP-QA-014",
                "revision": "03",
                "status": "approved",
                "content_hash": "a",
            },
            {
                "document_code": "POP-QA-014",
                "revision": "04",
                "status": "approved",
                "content_hash": "b",
            },
        ],
    )

    assert result.candidate_revision == "04"
    assert result.vigent_revision is None
    assert "ambiguous_vigent_revision" in result.blocking_gap_codes
