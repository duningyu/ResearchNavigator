import pytest

from research_navigator.documents.security import (
    DocumentSecurityError,
    validate_external_url,
    validate_pdf_upload,
)


def test_pdf_validation_requires_extension_mime_magic_and_size() -> None:
    data = b"%PDF-1.4\nminimal"
    result = validate_pdf_upload("paper.pdf", "application/pdf", data, max_bytes=100)
    assert result.sha256
    assert result.safe_filename == "paper.pdf"
    assert validate_pdf_upload(
        "../../private/paper.pdf", "application/pdf", data, max_bytes=100
    ).safe_filename == "paper.pdf"

    with pytest.raises(DocumentSecurityError, match="PDF extension"):
        validate_pdf_upload("paper.txt", "application/pdf", data, max_bytes=100)
    with pytest.raises(DocumentSecurityError, match="MIME"):
        validate_pdf_upload("paper.pdf", "text/html", data, max_bytes=100)
    with pytest.raises(DocumentSecurityError, match="signature"):
        validate_pdf_upload("paper.pdf", "application/pdf", b"<html>login</html>", max_bytes=100)
    with pytest.raises(DocumentSecurityError, match="size"):
        validate_pdf_upload("paper.pdf", "application/pdf", data * 20, max_bytes=20)


def test_external_url_rejects_private_and_non_http_destinations() -> None:
    for url in (
        "file:///etc/passwd",
        "http://127.0.0.1/internal",
        "http://localhost/admin",
        "http://10.0.0.2/private",
        "http://169.254.169.254/latest/meta-data",
    ):
        with pytest.raises(DocumentSecurityError):
            validate_external_url(url)

    assert validate_external_url("https://arxiv.org/pdf/2301.01234") == (
        "https://arxiv.org/pdf/2301.01234"
    )
