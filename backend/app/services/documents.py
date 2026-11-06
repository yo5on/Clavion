"""Turn an uploaded file into plain text, locally: pypdf for PDF text layers, RapidOCR (ONNX, offline) for images
and for scanned PDF pages. Files are processed in memory; nothing is sent to any external service.

Pages are joined with a form feed ("\\f") so every extracted value can be traced back to its page and line
(see services/parsers.Line). Line numbers count every line of a page, blank ones included.
"""

import io
import logging
import re
from functools import lru_cache

log = logging.getLogger("clavion.documents")

MAX_UPLOAD_BYTES = 15 * 1024 * 1024
MAX_PDF_PAGES = 60  # OCR of a scanned page takes seconds; bound the work one upload can cause
MAX_IMAGE_PIXELS = 40_000_000  # decompression-bomb guard: a 15 MB PNG can otherwise expand to gigabytes
MIN_TEXT_LAYER_CHARS = 40  # a page with less text than this (e.g. only a stamp or header) is treated as scanned
LOW_OCR_CONFIDENCE = 0.80
PAGE_BREAK = "\f"
IMAGE_TYPES = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}
ALLOWED_TYPES = IMAGE_TYPES | {".pdf", ".txt"}
# File signatures: the extension alone is not trusted.
MAGIC = {".pdf": (b"%PDF-",), ".png": (b"\x89PNG\r\n\x1a\n",), ".jpg": (b"\xff\xd8\xff",), ".jpeg": (b"\xff\xd8\xff",),
         ".bmp": (b"BM",), ".tif": (b"II*\x00", b"MM\x00*"), ".tiff": (b"II*\x00", b"MM\x00*"), ".webp": (b"RIFF",)}


class DocumentError(ValueError):
    pass


@lru_cache(maxsize=1)
def _ocr_engine():
    from rapidocr_onnxruntime import RapidOCR  # imported lazily: model load takes a few seconds

    return RapidOCR()


def _open_image(data: bytes):
    from PIL import Image

    img = Image.open(io.BytesIO(data))
    if img.width * img.height > MAX_IMAGE_PIXELS:
        raise DocumentError(f"image is too large to process ({img.width} x {img.height} pixels)")
    return img.convert("RGB")


def ocr_image(data: bytes) -> tuple[str, float | None]:
    """OCR an image; returns (text, mean confidence). Text lines are rebuilt by grouping boxes that share a
    baseline, left to right."""
    import numpy as np

    img = np.array(_open_image(data))
    result, _ = _ocr_engine()(img)
    boxes, confs = [], []
    for box, text, conf in result or []:
        ys, xs = [p[1] for p in box], [p[0] for p in box]
        boxes.append(((min(ys) + max(ys)) / 2, max(ys) - min(ys), min(xs), text))
        confs.append(float(conf))
    boxes.sort()
    lines: list[list] = []
    for cy, h, x, text in boxes:
        if lines and abs(lines[-1][0] - cy) < max(h, lines[-1][1]) * 0.5:
            lines[-1][2].append((x, text))
        else:
            lines.append([cy, h, [(x, text)]])
    text = "\n".join("  ".join(t for _, t in sorted(parts)) for _, _, parts in lines)
    text = re.sub(r"(?<=\d), (?=\d{2,3}\b)", ",", text)  # OCR splits "5,100.00" into "5, 100.00"
    text = re.sub(r"(?<=[\d,])[oO](?=[\d,.%])", "0", text)  # OCR reads 0 as o inside numbers
    return text, (sum(confs) / len(confs) if confs else None)


def _ocr_warning(where: str, conf: float | None) -> list[str]:
    if conf is not None and conf < LOW_OCR_CONFIDENCE:
        return [f"{where}: low OCR confidence ({conf:.0%}); check every amount against the original"]
    return []


def _check_signature(ext: str, data: bytes):
    if ext == ".txt":
        if b"\x00" in data[:4096]:
            raise DocumentError("file is not plain text")
        return
    sigs = MAGIC[ext]
    head = data[:1024] if ext == ".pdf" else data  # some PDF writers put bytes before %PDF-
    if not any((head.find(s) != -1) if ext == ".pdf" else data.startswith(s) for s in sigs):
        raise DocumentError(f"file content does not match its '{ext}' extension")
    if ext == ".webp" and data[8:12] != b"WEBP":
        raise DocumentError("file content does not match its '.webp' extension")


def extract_text(filename: str, data: bytes) -> tuple[str, str, list[str]]:
    """Returns (text, method, warnings). Pages of a PDF are separated by PAGE_BREAK."""
    ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in ALLOWED_TYPES:
        raise DocumentError(f"unsupported file type '{ext or filename}'; use PDF, PNG, JPG or TXT")
    if len(data) > MAX_UPLOAD_BYTES:
        raise DocumentError("file is larger than 15 MB")
    if not data:
        raise DocumentError("file is empty")
    _check_signature(ext, data)

    if ext == ".txt":
        try:
            return data.decode("utf-8-sig"), "plain-text", []
        except UnicodeDecodeError:
            return data.decode("utf-8", errors="replace"), "plain-text", [
                "text file is not valid UTF-8; unreadable characters were replaced"]
    if ext in IMAGE_TYPES:
        try:
            text, conf = ocr_image(data)
        except DocumentError:
            raise
        except Exception as e:  # PIL raises several types for corrupt images
            raise DocumentError(f"could not read image: {type(e).__name__}") from None
        return text, "image-ocr", (_ocr_warning("image", conf) if text.strip() else ["OCR found no text in the image"])
    return _extract_pdf(data)


def _extract_pdf(data: bytes) -> tuple[str, str, list[str]]:
    from pypdf import PdfReader

    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            raise DocumentError("PDF is password-protected; upload an unlocked copy")
        n_pages = len(reader.pages)
    except DocumentError:
        raise
    except Exception as e:  # pypdf raises many types (PdfReadError, KeyError, ValueError...) on malformed files
        raise DocumentError(f"could not read PDF: {type(e).__name__}") from None
    if n_pages == 0:
        raise DocumentError("PDF has no pages")
    if n_pages > MAX_PDF_PAGES:
        raise DocumentError(f"PDF has {n_pages} pages; the limit is {MAX_PDF_PAGES}")

    pages, warnings, ocr_used = [], [], False
    for n, page in enumerate(reader.pages, 1):
        try:
            text = page.extract_text(extraction_mode="layout") or ""
        except Exception as e:  # one broken page should not lose the rest of the document
            warnings.append(f"page {n}: text layer could not be read ({type(e).__name__})")
            text = ""
        if len(re.sub(r"\s", "", text)) < MIN_TEXT_LAYER_CHARS:  # scanned (or nearly empty) page: OCR its images
            parts, confs = [], []
            try:
                images = list(page.images)
            except Exception:
                images = []
            for img in images:
                try:
                    t, c = ocr_image(img.data)
                    parts.append(t)
                    if c is not None:
                        confs.append(c)
                except Exception as e:  # one unreadable embedded image should not fail the whole document
                    warnings.append(f"page {n}: an embedded image could not be read ({type(e).__name__})")
            ocr_text = "\n".join(parts)
            if len(ocr_text.strip()) > len(text.strip()):
                text, ocr_used = ocr_text, True
                warnings += _ocr_warning(f"page {n}", sum(confs) / len(confs) if confs else None)
            if not text.strip():
                warnings.append(f"page {n}: no text layer and OCR found no text")
        pages.append(text.replace(PAGE_BREAK, "\n"))
    return PAGE_BREAK.join(pages), "pdf-ocr" if ocr_used else "pdf-text", warnings


# Words that identify each document type. Used only to warn when a file looks like it was uploaded in the wrong
# slot; it never changes how a document is parsed.
TYPE_SIGNALS = {
    "bill": r"\bbill\s*no|in-?patient\s*bill|final\s*bill|grand\s*total|\bqty\b|date\s*of\s*admission|\bdischarge\b",
    "policy": r"policy\s*wording|sum\s*insured|\bexclusions?\b|\bclause\b|insured\s*person|the\s*company\s*will",
    "settlement": r"settlement|amount\s*approved|deductions?|claim\s*no|disallow|amount\s*paid",
}


def guess_type(text: str) -> str | None:
    """The document type whose signal words appear most often, or None if the text gives no clear signal."""
    scores = {t: len(re.findall(p, text, re.I)) for t, p in TYPE_SIGNALS.items()}
    best = max(scores, key=scores.get)
    ranked = sorted(scores.values(), reverse=True)
    return best if ranked[0] >= 3 and ranked[0] >= 2 * ranked[1] else None
