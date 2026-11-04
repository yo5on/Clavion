"""Turn an uploaded file into plain text, locally: pypdf for PDF text layers, RapidOCR (ONNX, offline) for images
and for scanned PDF pages. Files are processed in memory and never written to disk."""

import io
import logging
import re
from functools import lru_cache

log = logging.getLogger("clavion.documents")

MAX_UPLOAD_BYTES = 15 * 1024 * 1024
IMAGE_TYPES = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}
ALLOWED_TYPES = IMAGE_TYPES | {".pdf", ".txt"}


class DocumentError(ValueError):
    pass


@lru_cache(maxsize=1)
def _ocr_engine():
    from rapidocr_onnxruntime import RapidOCR  # imported lazily: model load takes a few seconds

    return RapidOCR()


def ocr_image(data: bytes) -> str:
    """OCR an image and rebuild text lines by grouping boxes that share a baseline, left to right."""
    import numpy as np
    from PIL import Image

    img = np.array(Image.open(io.BytesIO(data)).convert("RGB"))
    result, _ = _ocr_engine()(img)
    boxes = []
    for box, text, _conf in result or []:
        ys, xs = [p[1] for p in box], [p[0] for p in box]
        boxes.append(((min(ys) + max(ys)) / 2, max(ys) - min(ys), min(xs), text))
    boxes.sort()
    lines: list[list] = []
    for cy, h, x, text in boxes:
        if lines and abs(lines[-1][0] - cy) < max(h, lines[-1][1]) * 0.5:
            lines[-1][2].append((x, text))
        else:
            lines.append([cy, h, [(x, text)]])
    text = "\n".join("  ".join(t for _, t in sorted(parts)) for _, _, parts in lines)
    text = re.sub(r"(?<=\d), (?=\d{2,3}\b)", ",", text)  # OCR splits "5,100.00" into "5, 100.00"
    return re.sub(r"(?<=[\d,])[oO](?=[\d,.%])", "0", text)  # OCR reads 0 as o inside numbers


def extract_text(filename: str, data: bytes) -> tuple[str, str, list[str]]:
    """Returns (text, method, warnings)."""
    ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in ALLOWED_TYPES:
        raise DocumentError(f"unsupported file type '{ext or filename}'; use PDF, PNG, JPG or TXT")
    if len(data) > MAX_UPLOAD_BYTES:
        raise DocumentError("file is larger than 15 MB")
    if not data:
        raise DocumentError("file is empty")

    if ext == ".txt":
        return data.decode("utf-8", errors="replace"), "plain-text", []
    if ext in IMAGE_TYPES:
        try:
            text = ocr_image(data)
        except Exception as e:  # PIL raises several types for corrupt images
            raise DocumentError(f"could not read image: {type(e).__name__}") from None
        return text, "image-ocr", [] if text.strip() else ["OCR found no text in the image"]

    from pypdf import PdfReader
    from pypdf.errors import PdfReadError

    try:
        reader = PdfReader(io.BytesIO(data))
        pages, warnings, ocr_used = [], [], False
        for n, page in enumerate(reader.pages, 1):
            text = page.extract_text(extraction_mode="layout") or ""
            if not text.strip():  # scanned page: OCR its embedded images
                parts = [ocr_image(img.data) for img in page.images]
                text = "\n".join(parts)
                ocr_used = True
                if not text.strip():
                    warnings.append(f"page {n}: no text layer and OCR found no text")
            pages.append(text)
    except PdfReadError as e:
        raise DocumentError(f"could not read PDF: {e}") from None
    return "\n".join(pages), "pdf-ocr" if ocr_used else "pdf-text", warnings
