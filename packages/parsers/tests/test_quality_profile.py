from parsers.quality_profile import build_quality_profile, quality_profile_to_metadata


def test_detects_document_family_from_multiple_nested_identifiers() -> None:
    text = "\n".join([
        "Manual operacional consolidado",
        "POP 101 - Atendimento inicial",
        "1 Objetivo",
        "POP 102 - Encerramento",
        "2 Procedimento",
    ])

    profile = build_quality_profile(filename="manual-consolidado.txt", text=text)

    assert profile.document_family_candidate is True
    assert profile.nested_identifier_count == 2
    assert profile.unsafe_file_metadata_blocked is True
    assert profile.review_required is True
    assert profile.publication_blocking_risk is True
    assert [item.identifier for item in profile.nested_identifiers] == ["POP 101", "POP 102"]
    assert profile.risk_codes == ("document_family_candidate", "unsafe_file_metadata_blocked")


def test_quality_profile_metadata_is_stable_and_serializable() -> None:
    profile = build_quality_profile(
        filename="manual-consolidado.txt",
        text="POP 101 - Atendimento\nPOP 102 - Encerramento",
    )

    metadata = quality_profile_to_metadata(profile)

    assert metadata["document_family_candidate"] is True
    assert metadata["nested_identifier_count"] == 2
    assert metadata["unsafe_file_metadata_blocked"] is True
    assert metadata["review_required"] is True
    assert metadata["publication_blocking_risk"] is True
    assert metadata["risk_codes"] == [
        "document_family_candidate",
        "unsafe_file_metadata_blocked",
    ]
    assert metadata["nested_identifiers"][0]["identifier"] == "POP 101"
    assert metadata["nested_identifiers"][0]["line_number"] == 1
    assert metadata["nested_identifiers"][0]["quote"] == "POP 101 - Atendimento"
