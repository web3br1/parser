from parsers.industrial_metadata import extract_metadata_candidates


def test_extracts_document_code_and_revision_from_filename() -> None:
    result = extract_metadata_candidates(
        filename="POP-QA-014 Rev. 04 Controle de NC.pdf",
        text="",
    )

    assert result.document_code == "POP-QA-014"
    assert result.document_type == "POP"
    assert result.revision == "04"
    assert result.gap_codes == []


def test_extracts_real_snvs_code_with_multi_segment_owner() -> None:
    result = extract_metadata_candidates(
        filename="pop-o-snvs-010-rev4.pdf",
        text=(
            "Numero:\n"
            "POP-O-SNVS-010\n"
            "Revisao:\n"
            "4\n"
            "Vigencia:\n"
            "12/02/2025\n"
            "Titulo: Gerenciamento de Documentos do SNVS.\n"
        ),
    )

    assert result.document_code == "POP-O-SNVS-010"
    assert result.document_type == "POP"
    assert result.revision == "04"
    assert result.status == "vigent"
    assert result.gap_codes == []


def test_extracts_real_compact_code_near_code_header() -> None:
    result = extract_metadata_candidates(
        filename="bluesun-blu002-kit-fotovoltaico.pdf",
        text=(
            "Procedimento Operacional Padrao\n"
            "CODIGO\n"
            "TITULO:\n"
            "DEPTO\n"
            "PAGINA\n"
            "BLU002\n"
            "Instalacao do KIT Fotovoltaico Bluesun\n"
            "REVISAO\n"
            "REV00 AGO/22\n"
        ),
    )

    assert result.document_code == "BLU002"
    assert result.document_type == "POP"
    assert result.revision == "00"
    assert result.owner_area is None
    assert result.gap_codes == []


def test_extracts_real_spaced_pop_code_from_stacked_label() -> None:
    result = extract_metadata_candidates(
        filename="cispar-pop-005-inspecao-concreto.pdf",
        text=(
            "ELABORACAO DE PROCEDIMENTO OPERACIONAL PADRAO\n"
            "Codigo\n"
            "POP 005\n"
            "Revisao\n"
            "00\n"
            "Data\n"
            "22/03/2023\n"
        ),
    )

    assert result.document_code == "POP 005"
    assert result.document_type == "POP"
    assert result.revision == "00"
    assert result.gap_codes == []


def test_extracts_real_protocol_code_with_dotted_and_dash_segments() -> None:
    result = extract_metadata_candidates(
        filename="hospitalregional-higienizacao-maos-figuras.pdf",
        text=(
            "PROTOCOLO\n"
            "PTC.DEPQI-SCIRAS.001\n"
            "Versao no.: \n"
            "1.0.0\n"
            "Codigo: \n"
            "PTC.DEPQI-SCIRAS.001\n"
            "Proxima Revisao:\n"
            "MAI/2025\n"
        ),
    )

    assert result.document_code == "PTC.DEPQI-SCIRAS.001"
    assert result.document_type == "PTC"
    assert result.revision == "1.0.0"
    assert result.gap_codes == []


def test_does_not_promote_table_of_contents_pop_section_to_document_code() -> None:
    result = extract_metadata_candidates(
        filename="ponte-pop-pmpr-fotos.pdf",
        text=(
            "Procedimento Operacional Padrao: POP\n"
            "Policia Militar de Goias\n"
            "Procedimento Operacional Padrao\n"
            "3 Edicao\n"
            "SUMARIO\n"
            "MODULO I ACOES POLICIAIS MILITARES........9\n"
            "POP 101 EQUIPAMENTOS DE USO INDIVIDUAL........11\n"
            "101.01 Montagem do cinto de guarnicao........11\n"
        ),
    )

    assert result.document_code is None
    assert "missing_document_code" in result.gap_codes


def test_code_label_window_stops_before_table_of_contents_sections() -> None:
    result = extract_metadata_candidates(
        filename="manual-pop-collection.pdf",
        text=(
            "Codigo\n"
            "SUMARIO\n"
            "MODULO I ACOES POLICIAIS MILITARES........9\n"
            "POP 101 EQUIPAMENTOS DE USO INDIVIDUAL........11\n"
        ),
    )

    assert result.document_code is None
    assert "missing_document_code" in result.gap_codes


def test_extracts_metadata_from_text_labels() -> None:
    result = extract_metadata_candidates(
        filename="controle-nc.pdf",
        text=(
            "Codigo: IT-PRD-002\n"
            "Revisao: 07\n"
            "Titulo: Setup de Linha\n"
            "Area dona: Producao\n"
            "Status: Vigente\n"
        ),
    )

    assert result.document_code == "IT-PRD-002"
    assert result.document_type == "IT"
    assert result.revision == "07"
    assert result.title == "Setup de Linha"
    assert result.owner_area == "Producao"
    assert result.status == "vigent"


def test_missing_revision_is_gap_candidate() -> None:
    result = extract_metadata_candidates(
        filename="POP-QA-014 Controle de NC.pdf",
        text="Controle de Nao Conformidades",
    )

    assert result.document_code == "POP-QA-014"
    assert "missing_revision" in result.gap_codes


def test_status_obsolete_is_normalized() -> None:
    result = extract_metadata_candidates(
        filename="POP-QA-014 Rev 03.pdf",
        text="Documento obsoleto substituido pela Rev. 04.",
    )

    assert result.status == "obsolete"


def test_prefers_header_code_over_referenced_form_code() -> None:
    result = extract_metadata_candidates(
        filename="FAQ-QA-001_duvidas_nc.txt",
        text=(
            "Codigo: FAQ-QA-001\n"
            "Revisao: 01\n"
            "Resposta: Registrar a ocorrencia no FOR-QA-002.\n"
        ),
    )

    assert result.document_code == "FAQ-QA-001"


def test_collection_keeps_nested_identifiers_without_file_level_code() -> None:
    candidate = extract_metadata_candidates(
        filename="manual-consolidado.txt",
        text="\n".join([
            "Manual operacional consolidado",
            "POP 101 - Atendimento inicial",
            "POP 102 - Encerramento",
        ]),
    )

    assert candidate.document_code is None
    assert "ambiguous_nested_document_codes" in candidate.gap_codes
    assert "document_family_candidate" in candidate.gap_codes
    assert [item["identifier"] for item in candidate.nested_identifiers] == ["POP 101", "POP 102"]
    assert candidate.quality_profile["document_family_candidate"] is True


def test_csv_register_rows_do_not_become_file_level_metadata() -> None:
    candidate = extract_metadata_candidates(
        filename="csv_register_like_rows.csv",
        text="\n".join([
            "registro,descricao,status",
            "REG 001,Registro de limpeza,ativo",
            "REG 002,Registro de inspecao,ativo",
        ]),
    )

    assert candidate.document_code is None
    assert "document_family_candidate" in candidate.gap_codes
    assert [item["identifier"] for item in candidate.nested_identifiers] == ["REG 001", "REG 002"]


def test_collection_labeled_code_does_not_become_file_level_metadata() -> None:
    candidate = extract_metadata_candidates(
        filename="manual-consolidado.txt",
        text="\n".join([
            "Codigo: POP 101",
            "POP 101 - Atendimento inicial",
            "POP 102 - Encerramento",
        ]),
    )

    assert candidate.document_code is None
    assert "document_family_candidate" in candidate.gap_codes
    assert "ambiguous_nested_document_codes" in candidate.gap_codes


def test_collection_filename_code_does_not_become_file_level_metadata() -> None:
    candidate = extract_metadata_candidates(
        filename="POP-101-manual-consolidado.txt",
        text="\n".join([
            "POP 101 - Atendimento inicial",
            "POP 102 - Encerramento",
        ]),
    )

    assert candidate.document_code is None
    assert "document_family_candidate" in candidate.gap_codes
