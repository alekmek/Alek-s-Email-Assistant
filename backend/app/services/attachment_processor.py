import base64
import io
from typing import Optional

from docx import Document
from openpyxl import load_workbook
from PIL import Image


class AttachmentProcessor:
    """Process email attachments for LLM analysis."""

    # Supported content types
    PDF_TYPES = ["application/pdf"]
    IMAGE_TYPES = ["image/png", "image/jpeg", "image/gif", "image/webp"]
    WORD_TYPES = [
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/msword",
    ]
    EXCEL_TYPES = [
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/vnd.ms-excel",
    ]
    TEXT_TYPES = ["text/plain", "text/csv", "text/html"]

    def process(self, data: bytes, content_type: str, filename: str) -> dict:
        """
        Process attachment and return content suitable for the LLM.

        Returns a dict with either:
        - {"type": "document", "source": {...}} for PDFs (native document input)
        - {"type": "image", "source": {...}} for images (vision input)
        - {"type": "text", "content": "..."} for extracted text
        """
        if content_type in self.PDF_TYPES:
            return self._process_pdf(data)
        elif content_type in self.IMAGE_TYPES:
            return self._process_image(data, content_type)
        elif content_type in self.WORD_TYPES:
            return self._process_word(data, filename)
        elif content_type in self.EXCEL_TYPES:
            return self._process_excel(data, filename)
        elif content_type in self.TEXT_TYPES:
            return self._process_text(data, filename)
        else:
            return {
                "type": "unsupported",
                "message": f"Cannot process attachment of type {content_type}. Filename: {filename}",
            }

    def _process_pdf(self, data: bytes) -> dict:
        """Process PDF for native document input."""
        return {
            "type": "document",
            "source": {
                "type": "base64",
                "media_type": "application/pdf",
                "data": base64.b64encode(data).decode("utf-8"),
            },
        }

    def _process_image(self, data: bytes, content_type: str) -> dict:
        """Process image for vision input."""
        return {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": content_type,
                "data": base64.b64encode(data).decode("utf-8"),
            },
        }

    def _process_word(self, data: bytes, filename: str) -> dict:
        """Extract text from Word document."""
        try:
            doc = Document(io.BytesIO(data))
            paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
            text = "\n\n".join(paragraphs)
            return {
                "type": "text",
                "content": f"Content of {filename}:\n\n{text}",
            }
        except Exception as e:
            return {
                "type": "error",
                "message": f"Failed to process Word document {filename}: {str(e)}",
            }

    def _process_excel(self, data: bytes, filename: str) -> dict:
        """Extract data from Excel spreadsheet."""
        try:
            wb = load_workbook(io.BytesIO(data), read_only=True)
            result_parts = [f"Content of {filename}:"]

            for sheet_name in wb.sheetnames:
                sheet = wb[sheet_name]
                result_parts.append(f"\n## Sheet: {sheet_name}\n")

                rows = []
                for row in sheet.iter_rows(max_row=100, values_only=True):
                    # Filter out completely empty rows
                    if any(cell is not None for cell in row):
                        row_text = " | ".join(
                            str(cell) if cell is not None else "" for cell in row
                        )
                        rows.append(row_text)

                result_parts.append("\n".join(rows))

            return {
                "type": "text",
                "content": "\n".join(result_parts),
            }
        except Exception as e:
            return {
                "type": "error",
                "message": f"Failed to process Excel file {filename}: {str(e)}",
            }

    def _process_text(self, data: bytes, filename: str) -> dict:
        """Process plain text files."""
        try:
            text = data.decode("utf-8")
            return {
                "type": "text",
                "content": f"Content of {filename}:\n\n{text}",
            }
        except UnicodeDecodeError:
            try:
                text = data.decode("latin-1")
                return {
                    "type": "text",
                    "content": f"Content of {filename}:\n\n{text}",
                }
            except Exception as e:
                return {
                    "type": "error",
                    "message": f"Failed to decode text file {filename}: {str(e)}",
                }


# Singleton instance
_processor: Optional[AttachmentProcessor] = None


def get_attachment_processor() -> AttachmentProcessor:
    global _processor
    if _processor is None:
        _processor = AttachmentProcessor()
    return _processor
