from research_navigator.documents.parser import ParsedDocument, ParsedPage, chunk_document


def test_chunk_document_recognizes_roman_numeral_section_heading() -> None:
    document = ParsedDocument(
        pages=(
            ParsedPage(
                page_number=3,
                text="III. FRAMEWORK\nThis section describes the model framework.",
            ),
        ),
    )

    chunks = chunk_document(document)

    assert chunks[0].section == "Framework"


def test_chunk_document_recognizes_heading_beyond_page_preamble() -> None:
    page = ParsedPage(
        page_number=2,
        text="\n".join(["running header"] * 9 + ["II. RELATED WORK", "Evidence text."]),
    )

    chunks = chunk_document(ParsedDocument(pages=(page,)), max_chars=500)

    assert chunks[0].section == "Related Work"
