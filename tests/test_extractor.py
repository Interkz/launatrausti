import json
import pytest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch, MagicMock

from src.extractor import (
    extract_text_from_pdf,
    parse_with_claude_v2,
    extract_from_pdf_v2,
    extract_batch,
    ExtractedData,
    ExtractedDataV2,
    _is_already_extracted,
    EXTRACTION_PROMPT_V2,
)


# --- test_extract_text_from_pdf ---

def test_extract_text_from_pdf(tmp_path):
    """Mock pdfplumber, verify text concatenation from multiple pages."""
    fake_pdf = tmp_path / "test.pdf"
    fake_pdf.touch()

    page1 = MagicMock()
    page1.extract_text.return_value = "Page one text"
    page2 = MagicMock()
    page2.extract_text.return_value = "Page two text"
    page3 = MagicMock()
    page3.extract_text.return_value = None  # Empty page

    mock_pdf = MagicMock()
    mock_pdf.pages = [page1, page2, page3]
    mock_pdf.__enter__ = MagicMock(return_value=mock_pdf)
    mock_pdf.__exit__ = MagicMock(return_value=False)

    with patch("src.extractor.pdfplumber.open", return_value=mock_pdf):
        result = extract_text_from_pdf(fake_pdf)

    assert "Page one text" in result
    assert "Page two text" in result
    # Pages joined with double newline
    assert result == "Page one text\n\nPage two text"


def test_extract_text_from_pdf_empty(tmp_path):
    """All pages return None — result should be empty string."""
    fake_pdf = tmp_path / "empty.pdf"
    fake_pdf.touch()

    page1 = MagicMock()
    page1.extract_text.return_value = None

    mock_pdf = MagicMock()
    mock_pdf.pages = [page1]
    mock_pdf.__enter__ = MagicMock(return_value=mock_pdf)
    mock_pdf.__exit__ = MagicMock(return_value=False)

    with patch("src.extractor.pdfplumber.open", return_value=mock_pdf):
        result = extract_text_from_pdf(fake_pdf)

    assert result == ""


# --- test_parse_with_claude_v2 ---

MOCK_CLAUDE_RESPONSE_V2 = {
    "company_name": "Test ehf.",
    "kennitala": "1234567890",
    "year": 2023,
    "launakostnadur": 150000000,
    "starfsmenn": 12.5,
    "tekjur": 500000000,
    "hagnadur": 45000000,
    "rekstrarkostnadur": 420000000,
    "eiginfjarhlufall": 0.38,
    "confidence": 0.92,
}


def test_parse_with_claude_v2():
    """Mock Claude client, verify extended fields parsed correctly."""
    mock_message = MagicMock()
    mock_message.content = [MagicMock(text=json.dumps(MOCK_CLAUDE_RESPONSE_V2))]

    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_message

    with patch("src.extractor.anthropic.Anthropic", return_value=mock_client):
        result = parse_with_claude_v2("Some annual report text", api_key="test-key")

    assert result["company_name"] == "Test ehf."
    assert result["year"] == 2023
    assert result["hagnadur"] == 45000000
    assert result["rekstrarkostnadur"] == 420000000
    assert result["eiginfjarhlufall"] == 0.38
    assert result["confidence"] == 0.92

    # Verify V2 prompt was used
    call_args = mock_client.messages.create.call_args
    prompt_content = call_args[1]["messages"][0]["content"]
    assert "hagnadur" in prompt_content
    assert "rekstrarkostnadur" in prompt_content
    assert "eiginfjarhlufall" in prompt_content


def test_parse_with_claude_v2_json_in_code_block():
    """Claude wraps response in ```json ... ``` — verify we still parse it."""
    wrapped = f"```json\n{json.dumps(MOCK_CLAUDE_RESPONSE_V2)}\n```"

    mock_message = MagicMock()
    mock_message.content = [MagicMock(text=wrapped)]

    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_message

    with patch("src.extractor.anthropic.Anthropic", return_value=mock_client):
        result = parse_with_claude_v2("text", api_key="test-key")

    assert result["launakostnadur"] == 150000000


def test_parse_with_claude_v2_no_api_key():
    """Should raise ValueError when no API key is provided."""
    with patch.dict("os.environ", {}, clear=True):
        with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
            parse_with_claude_v2("text", api_key=None)


# --- test_extract_from_pdf_v2 ---

def test_extract_from_pdf_v2(tmp_path):
    """Full extraction flow returning ExtractedDataV2."""
    fake_pdf = tmp_path / "4710080280_2023.pdf"
    fake_pdf.touch()

    with patch("src.extractor.extract_text_from_pdf", return_value="fake annual report text"), \
         patch("src.extractor.parse_with_claude_v2", return_value=MOCK_CLAUDE_RESPONSE_V2):
        result = extract_from_pdf_v2(fake_pdf, api_key="test-key", source_type="rikisreikningur")

    assert isinstance(result, ExtractedDataV2)
    assert result.company_name == "Test ehf."
    assert result.year == 2023
    assert result.launakostnadur == 150000000
    assert result.starfsmenn == 12.5
    assert result.tekjur == 500000000
    assert result.hagnadur == 45000000
    assert result.rekstrarkostnadur == 420000000
    assert result.eiginfjarhlufall == 0.38
    assert result.source_type == "rikisreikningur"
    assert result.confidence == 0.92


def test_extract_from_pdf_v2_missing_required_field(tmp_path):
    """Should raise ValueError when launakostnadur is missing."""
    fake_pdf = tmp_path / "bad.pdf"
    fake_pdf.touch()

    bad_response = {**MOCK_CLAUDE_RESPONSE_V2, "launakostnadur": None}

    with patch("src.extractor.extract_text_from_pdf", return_value="text"), \
         patch("src.extractor.parse_with_claude_v2", return_value=bad_response):
        with pytest.raises(ValueError, match="launakostnadur"):
            extract_from_pdf_v2(fake_pdf, api_key="test-key")


def test_extract_from_pdf_v2_kennitala_from_filename(tmp_path):
    """When Claude doesn't find kennitala, extract from filename."""
    fake_pdf = tmp_path / "4710080280_2023.pdf"
    fake_pdf.touch()

    response_no_kt = {**MOCK_CLAUDE_RESPONSE_V2, "kennitala": None}

    with patch("src.extractor.extract_text_from_pdf", return_value="text"), \
         patch("src.extractor.parse_with_claude_v2", return_value=response_no_kt):
        result = extract_from_pdf_v2(fake_pdf, api_key="test-key")

    assert result.kennitala == "4710080280"


def test_extract_from_pdf_v2_null_optional_fields(tmp_path):
    """Extended fields can be null without error."""
    fake_pdf = tmp_path / "test.pdf"
    fake_pdf.touch()

    response_minimal = {
        **MOCK_CLAUDE_RESPONSE_V2,
        "hagnadur": None,
        "rekstrarkostnadur": None,
        "eiginfjarhlufall": None,
    }

    with patch("src.extractor.extract_text_from_pdf", return_value="text"), \
         patch("src.extractor.parse_with_claude_v2", return_value=response_minimal):
        result = extract_from_pdf_v2(fake_pdf, api_key="test-key")

    assert result.hagnadur is None
    assert result.rekstrarkostnadur is None
    assert result.eiginfjarhlufall is None


# --- test_extract_batch ---

def test_extract_batch_skips_extracted(tmp_path):
    """Verify already-extracted PDFs are skipped via scrape_log check."""
    # Create two fake PDFs
    (tmp_path / "already_done.pdf").touch()
    (tmp_path / "new_one.pdf").touch()

    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value = mock_cursor

    # First call (already_done) returns a row -- skip it
    # Second call (new_one) returns None -- process it
    mock_cursor.fetchone.side_effect = [{"id": 1}, None]

    mock_data = ExtractedDataV2(
        company_name="New Corp",
        kennitala="9876543210",
        year=2023,
        launakostnadur=80000000,
        starfsmenn=8.0,
        tekjur=300000000,
        confidence=0.88,
        raw_text_snippet="text",
        hagnadur=20000000,
        rekstrarkostnadur=250000000,
        eiginfjarhlufall=0.42,
        source_type="pdf",
    )

    with patch("src.database.get_connection", return_value=mock_conn), \
         patch("src.extractor.extract_from_pdf_v2", return_value=mock_data) as mock_extract, \
         patch("src.database.get_or_create_company", return_value=1), \
         patch("src.database.save_annual_report", return_value=1), \
         patch("src.database.save_scrape_log", return_value=1):

        results = extract_batch(tmp_path, skip_extracted=True, api_key="test-key")

    # Only new_one should have been extracted
    assert len(results) == 1
    assert results[0].company_name == "New Corp"
    mock_extract.assert_called_once()


def test_extract_batch_logs_failure(tmp_path):
    """Failed extractions should be logged with error message."""
    (tmp_path / "broken.pdf").touch()

    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value = mock_cursor
    mock_cursor.fetchone.return_value = None  # Not already extracted

    mock_log = MagicMock(return_value=1)

    with patch("src.database.get_connection", return_value=mock_conn), \
         patch("src.extractor.extract_from_pdf_v2", side_effect=ValueError("No text")), \
         patch("src.database.save_scrape_log", mock_log):

        results = extract_batch(tmp_path, skip_extracted=True, api_key="test-key")

    assert len(results) == 0

    # Should have 2 log calls: running + failed
    assert mock_log.call_count == 2
    failed_entry = mock_log.call_args_list[1][0][0]
    assert failed_entry.status == "failed"
    assert "No text" in failed_entry.error_message


def test_extract_batch_empty_dir(tmp_path):
    """No PDFs found should return empty list."""
    results = extract_batch(tmp_path, api_key="test-key")
    assert results == []


# --- test_laun_hlutfall_calculation ---

def test_laun_hlutfall_calculation():
    """Verify wage-to-revenue ratio is correctly derivable from ExtractedDataV2."""
    data = ExtractedDataV2(
        company_name="Test",
        kennitala="1234567890",
        year=2023,
        launakostnadur=200_000_000,
        starfsmenn=10.0,
        tekjur=500_000_000,
        confidence=0.9,
        raw_text_snippet="text",
        hagnadur=50_000_000,
        rekstrarkostnadur=400_000_000,
        eiginfjarhlufall=0.35,
    )

    # Wage-to-revenue ratio (this is what save_annual_report computes as laun_hlutfall_tekna)
    laun_hlutfall = data.launakostnadur / data.tekjur if data.tekjur and data.tekjur > 0 else None
    assert laun_hlutfall == pytest.approx(0.4)


def test_laun_hlutfall_no_tekjur():
    """When tekjur is None, ratio should be None."""
    data = ExtractedDataV2(
        company_name="Test",
        kennitala="1234567890",
        year=2023,
        launakostnadur=200_000_000,
        starfsmenn=10.0,
        tekjur=None,
        confidence=0.9,
        raw_text_snippet="text",
    )

    laun_hlutfall = data.launakostnadur / data.tekjur if data.tekjur and data.tekjur > 0 else None
    assert laun_hlutfall is None


# --- test ExtractedDataV2 inherits from ExtractedData ---

def test_extracted_data_v2_inherits():
    """ExtractedDataV2 is a subclass of ExtractedData."""
    assert issubclass(ExtractedDataV2, ExtractedData)

    data = ExtractedDataV2(
        company_name="Test",
        kennitala="1234567890",
        year=2023,
        launakostnadur=100_000_000,
        starfsmenn=5.0,
        tekjur=300_000_000,
        confidence=0.85,
        raw_text_snippet="text",
    )

    assert isinstance(data, ExtractedData)
    # V2 defaults
    assert data.hagnadur is None
    assert data.rekstrarkostnadur is None
    assert data.eiginfjarhlufall is None
    assert data.source_type == "pdf"


# --- test original extract_from_pdf still works ---

def test_original_extract_from_pdf_unchanged(tmp_path):
    """Original extract_from_pdf function still returns ExtractedData (not V2)."""
    from src.extractor import extract_from_pdf

    fake_pdf = tmp_path / "test.pdf"
    fake_pdf.touch()

    response_v1 = {
        "company_name": "Old Corp",
        "kennitala": "5555555555",
        "year": 2022,
        "launakostnadur": 60000000,
        "starfsmenn": 6.0,
        "tekjur": 200000000,
        "confidence": 0.8,
    }

    with patch("src.extractor.extract_text_from_pdf", return_value="text"), \
         patch("src.extractor.parse_with_claude", return_value=response_v1):
        result = extract_from_pdf(fake_pdf, api_key="test-key")

    assert isinstance(result, ExtractedData)
    assert not isinstance(result, ExtractedDataV2)
    assert result.company_name == "Old Corp"
    assert result.year == 2022
