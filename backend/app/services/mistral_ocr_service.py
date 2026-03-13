"""Mistral OCR service for high-quality PDF text extraction."""

import base64
import logging
from pathlib import Path

from mistralai import Mistral

logger = logging.getLogger(__name__)


def extract_with_mistral_ocr_sync(file_path: str, api_key: str) -> str:
    """Extract text from a PDF using Mistral's OCR API.

    Returns:
        Concatenated markdown text from all pages, or empty string on failure.
    """
    try:
        pdf_bytes = Path(file_path).read_bytes()
        b64 = base64.standard_b64encode(pdf_bytes).decode("utf-8")

        client = Mistral(api_key=api_key)
        result = client.ocr.process(
            model="mistral-ocr-latest",
            document={
                "type": "document_url",
                "document_url": f"data:application/pdf;base64,{b64}",
            },
            include_image_base64=False,
        )

        pages_md = [page.markdown for page in result.pages if page.markdown]
        text = "\n\n".join(pages_md)

        logger.info(
            "Mistral OCR extracted %d chars from %d pages (%s)",
            len(text), len(result.pages), file_path,
        )
        return text

    except Exception:
        logger.exception("Mistral OCR extraction failed for %s", file_path)
        return ""
