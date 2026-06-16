import pytest
from domain.industrial import ControlledDocumentMetadata, DocumentRelationship
from pydantic import ValidationError


def test_controlled_document_metadata_accepts_pop_revision() -> None:
    item = ControlledDocumentMetadata(
        document_code="POP-QA-014",
        document_type="POP",
        title="Controle de Nao Conformidades",
        revision="04",
        status="vigent",
        owner_area="Qualidade",
    )

    assert item.document_code == "POP-QA-014"
    assert item.document_type == "POP"
    assert item.revision == "04"
    assert item.status == "vigent"
    assert item.approvers == []
    assert item.allowed_audience == []


def test_controlled_document_metadata_normalizes_document_type_and_status() -> None:
    item = ControlledDocumentMetadata(
        document_code=" pop-qa-014 ",
        document_type="pop",
        title=" Controle de Nao Conformidades ",
        revision=" rev. 04 ",
        status="vigente",
        owner_area=" Qualidade ",
        confidentiality="INTERNAL",
    )

    assert item.document_code == "POP-QA-014"
    assert item.document_type == "POP"
    assert item.title == "Controle de Nao Conformidades"
    assert item.revision == "04"
    assert item.status == "vigent"
    assert item.owner_area == "Qualidade"
    assert item.confidentiality == "internal"


def test_controlled_document_metadata_rejects_unknown_document_type() -> None:
    with pytest.raises(ValidationError):
        ControlledDocumentMetadata(
            document_code="DOC-QA-014",
            document_type="spreadsheet",
            title="Controle de Nao Conformidades",
            revision="04",
            status="vigent",
            owner_area="Qualidade",
        )


def test_relationship_accepts_known_type_and_evidence() -> None:
    relation = DocumentRelationship(
        from_id="POP-QA-014",
        from_type="Document",
        to_id="FOR-QA-002",
        to_type="Form",
        relationship_type="uses_form",
        source_document_code="POP-QA-014",
        evidence_quote="Registrar a NC no formulario FOR-QA-002.",
    )

    assert relation.relationship_type == "uses_form"
    assert relation.source_document_code == "POP-QA-014"
    assert relation.evidence_quote == "Registrar a NC no formulario FOR-QA-002."


def test_relationship_rejects_unknown_type() -> None:
    with pytest.raises(ValidationError):
        DocumentRelationship(
            from_id="POP-QA-014",
            from_type="Document",
            to_id="FOR-QA-002",
            to_type="Form",
            relationship_type="references_randomly",
        )
