"""Readonly Zulip MCP tools for Hermes Agent.

This module exposes stream/topic search, priority-context collection, and safe
attachment extraction through the FastMCP stdio server used by Hermes.
"""

from __future__ import annotations

import json
import logging
import os
import re
import tempfile
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urljoin, urlparse
from zoneinfo import ZoneInfo

import requests
import zulip
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from markitdown import MarkItDown
from mcp.server.fastmcp import FastMCP

logging.getLogger("pdfminer").setLevel(logging.ERROR)
logging.getLogger("pdfminer.pdffont").setLevel(logging.ERROR)
logging.getLogger("PIL").setLevel(logging.ERROR)

load_dotenv()

mcp = FastMCP("zulip-hermes-readonly")

ZULIP_SITE_URL = os.getenv("ZULIP_SITE_URL", "").rstrip("/")
ZULIP_BOT_EMAIL = os.getenv("ZULIP_BOT_EMAIL", "")
ZULIP_API_KEY = os.getenv("ZULIP_API_KEY", "")

DEFAULT_CHANNEL = os.getenv("ZULIP_DEFAULT_CHANNEL", "general")
DEFAULT_TOPIC = os.getenv("ZULIP_DEFAULT_TOPIC", "status")
DEFAULT_TIMEZONE = os.getenv("ZULIP_TIMEZONE", "America/Sao_Paulo")

MAX_DOWNLOAD_MB = int(os.getenv("ZULIP_MAX_ATTACHMENT_MB", "25"))
MAX_ATTACHMENT_FILES = int(os.getenv("ZULIP_MAX_ATTACHMENT_FILES", "5"))
MAX_CHARS_PER_FILE = int(os.getenv("ZULIP_MAX_CHARS_PER_FILE", "16000"))
MAX_TOTAL_CHARS = int(os.getenv("ZULIP_MAX_TOTAL_CHARS", "60000"))

OCR_MIN_TEXT_CHARS = int(os.getenv("ZULIP_OCR_MIN_TEXT_CHARS", "80"))
OCR_MAX_PDF_PAGES = int(os.getenv("ZULIP_OCR_MAX_PDF_PAGES", "10"))
OCR_MAX_GIF_FRAMES = int(os.getenv("ZULIP_OCR_MAX_GIF_FRAMES", "6"))
OCR_LANGUAGE = os.getenv("ZULIP_OCR_LANGUAGE", "eng+por")

# Common Windows path for UB Mannheim Tesseract.
TESSERACT_CMD = os.getenv(
    "TESSERACT_CMD",
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
)


@dataclass
class AttachmentCandidate:
    """Represent a safe Zulip upload candidate.

    Notes
    -----
    This class supports the Zulip Hermes integration internals.
    """

    url: str
    label: str
    source: str


def get_client() -> zulip.Client:
    """Create an authenticated Zulip API client.

    Returns
    -------
    zulip.Client
        Result produced by the helper.
    """
    if not ZULIP_SITE_URL or not ZULIP_BOT_EMAIL or not ZULIP_API_KEY:
        raise RuntimeError("Missing ZULIP_SITE_URL, ZULIP_BOT_EMAIL, or ZULIP_API_KEY in .env")

    return zulip.Client(
        site=ZULIP_SITE_URL,
        email=ZULIP_BOT_EMAIL,
        api_key=ZULIP_API_KEY,
    )


def html_to_text(value: str) -> str:
    """Convert Zulip HTML content to readable text.

    Parameters
    ----------
    value : str
        Input value.

    Returns
    -------
    str
        Text produced by the helper.
    """
    return BeautifulSoup(value or "", "html.parser").get_text(" ", strip=True)


def msg_topic(msg: dict) -> str:
    """Return the topic or subject for a Zulip message.

    Parameters
    ----------
    msg : dict
        Zulip message payload.

    Returns
    -------
    str
        Text produced by the helper.
    """
    return msg.get("subject") or msg.get("topic") or ""


def format_message(msg: dict, tz: ZoneInfo, include_id: bool = True) -> str:
    """Render a Zulip message for terminal or prompt context.

    Parameters
    ----------
    msg : dict
        Zulip message payload.
    tz : ZoneInfo
        Input value.
    include_id : bool
        Input value.

    Returns
    -------
    str
        Text produced by the helper.
    """
    ts = datetime.fromtimestamp(msg["timestamp"], tz)
    sender = msg.get("sender_full_name") or msg.get("sender_email") or "Unknown"
    topic = msg_topic(msg)
    content = html_to_text(msg.get("content", ""))

    prefix = f"message_id={msg.get('id')} | " if include_id else ""
    return f"- [{ts.strftime('%Y-%m-%d %H:%M')}] {prefix}{sender} | {topic}: {content}"


_USER_UPLOAD_LINK_RE = re.compile(r"\(((?:https?://[^()\s]+)?/user_uploads/[^()\s]+)\)")


def is_same_zulip_host(url: str) -> bool:
    """Check whether a URL belongs to the configured Zulip realm.

    Parameters
    ----------
    url : str
        URL or upload path to validate.

    Returns
    -------
    bool
        Whether the requested condition is true.
    """
    base = urlparse(ZULIP_SITE_URL)
    parsed = urlparse(url)
    return parsed.scheme in {"http", "https"} and parsed.netloc == base.netloc


def normalize_url(url: str) -> str:
    """Normalize a Zulip upload URL or path.

    Parameters
    ----------
    url : str
        URL or upload path to validate.

    Returns
    -------
    str
        Text produced by the helper.
    """
    return urljoin(ZULIP_SITE_URL + "/", url)


def extract_upload_paths(content: str) -> list[str]:
    """
    Return unique normalized Zulip /user_uploads/ paths in message order.

    Absolute URLs are reduced to paths before use, so authenticated download
    requests always target the configured Zulip realm rather than a host that
    appeared in user-controlled Markdown.
    """
    paths: list[str] = []
    seen: set[str] = set()

    for match in _USER_UPLOAD_LINK_RE.finditer(content or ""):
        target = match.group(1)
        path = target[target.find("/user_uploads/") :].split("?", 1)[0]
        if not is_valid_upload_path(path) or path in seen:
            continue
        seen.add(path)
        paths.append(path)

    return paths


def is_valid_upload_path(path: str) -> bool:
    """Return whether path is a non-traversing Zulip upload path."""
    if not isinstance(path, str) or not path.startswith("/user_uploads/"):
        return False
    segments = unquote(path).split("/")
    return (
        len(segments) >= 4
        and segments[1] == "user_uploads"
        and all(segment not in {"", ".", ".."} for segment in segments[1:])
    )


def upload_filename(path: str) -> str:
    """Derive a safe display filename from a normalized upload path."""
    name = Path(unquote(path.rsplit("/", 1)[-1])).name
    return name or "attachment"


def upload_path_from_url(url: str) -> str | None:
    """Return a normalized upload path if url points at this Zulip server."""
    normalized = normalize_url(url)
    parsed = urlparse(normalized)
    if "/api/v1/user_uploads/" in parsed.path:
        path = parsed.path[7:]
    elif "/user_uploads/" in parsed.path:
        path = parsed.path[parsed.path.find("/user_uploads/") :]
    else:
        return None
    if not is_same_zulip_host(normalized) or not is_valid_upload_path(path):
        return None
    return path


def looks_like_upload_url(url: str) -> bool:
    """Check whether a value resembles a Zulip upload URL.

    Parameters
    ----------
    url : str
        URL or upload path to validate.

    Returns
    -------
    bool
        Whether the requested condition is true.
    """
    return upload_path_from_url(url) is not None


def safe_attachment_url(url: str) -> bool:
    """
    Security: only download files hosted by this Zulip server and under user_uploads.
    This avoids letting an arbitrary Zulip message make Hermes fetch internal/private URLs.
    """
    return upload_path_from_url(url) is not None


def extract_attachment_candidates_from_html(html: str) -> list[AttachmentCandidate]:
    """Find safe attachment candidates in rendered Zulip HTML.

    Parameters
    ----------
    html : str
        HTML fragment returned by Zulip.

    Returns
    -------
    list[AttachmentCandidate]
        Result produced by the helper.
    """
    soup = BeautifulSoup(html or "", "html.parser")
    candidates: list[AttachmentCandidate] = []

    def add_path(path: str, label: str, source: str) -> None:
        """Add a validated upload path to the candidate list.

        Parameters
        ----------
        path : str
            Local filesystem path.
        label : str
            Input value.
        source : str
            Input value.

        Returns
        -------
        None
            The operation completes through side effects.
        """
        full_url = normalize_url(path)
        candidates.append(
            AttachmentCandidate(
                url=full_url,
                label=unquote(label or upload_filename(path)),
                source=source,
            )
        )

    for tag in soup.find_all(["a", "img", "video", "audio", "source"]):
        raw_url = tag.get("href") or tag.get("src")
        if not raw_url:
            continue
        path = upload_path_from_url(raw_url)
        if not path:
            continue
        label = tag.get_text(" ", strip=True) or upload_filename(path)
        add_path(path, label, tag.name)

    # BeautifulSoup sees rendered HTML; keep a Markdown regex fallback for raw
    # content returned with apply_markdown=False.
    for path in extract_upload_paths(html):
        add_path(path, upload_filename(path), "markdown")

    # Deduplicate preserving order.
    seen = set()
    unique: list[AttachmentCandidate] = []
    for item in candidates:
        if item.url in seen:
            continue
        seen.add(item.url)
        unique.append(item)

    return unique


def extract_attachment_candidates_from_message(msg: dict) -> list[AttachmentCandidate]:
    """Find safe attachment candidates in a Zulip message.

    Parameters
    ----------
    msg : dict
        Zulip message payload.

    Returns
    -------
    list[AttachmentCandidate]
        Result produced by the helper.
    """
    return extract_attachment_candidates_from_html(msg.get("content", ""))


def filename_from_response(url: str, response: requests.Response) -> str:
    """Choose a safe filename for a downloaded attachment.

    Parameters
    ----------
    url : str
        URL or upload path to validate.
    response : requests.Response
        Completed HTTP response.

    Returns
    -------
    str
        Text produced by the helper.
    """
    content_disposition = response.headers.get("content-disposition", "")

    match = re.search(r'filename\*?=(?:UTF-8\'\')?"?([^";]+)"?', content_disposition)
    if match:
        return unquote(match.group(1)).strip()

    path_name = Path(urlparse(url).path).name
    path_name = unquote(path_name).strip()

    if path_name:
        return path_name

    return "zulip-attachment.bin"


def sanitize_filename(name: str) -> str:
    """Sanitize a filename for local filesystem use.

    Parameters
    ----------
    name : str
        Environment variable name.

    Returns
    -------
    str
        Text produced by the helper.
    """
    name = re.sub(r'[<>:"/\\|?*\x00-\x1F]', "_", name).strip()
    return name or "zulip-attachment.bin"


def download_attachment(candidate: AttachmentCandidate, target_dir: Path) -> Path:
    """Download a Zulip attachment through an authenticated URL.

    Parameters
    ----------
    candidate : AttachmentCandidate
        Validated attachment candidate.
    target_dir : Path
        Directory used for downloaded files.

    Returns
    -------
    Path
        Result produced by the helper.
    """
    upload_path = upload_path_from_url(candidate.url)
    if not upload_path:
        raise ValueError("Refusing to download non-Zulip upload URL")

    max_bytes = MAX_DOWNLOAD_MB * 1024 * 1024

    # Zulip upload links require an authenticated first hop to obtain a
    # short-lived signed URL. Keep the credential-bearing request pointed at the
    # configured Zulip realm, never at a host embedded in message Markdown.
    signed_response = requests.get(
        f"{ZULIP_SITE_URL}/api/v1{upload_path}",
        auth=(ZULIP_BOT_EMAIL, ZULIP_API_KEY),
        timeout=30,
    )
    signed_response.raise_for_status()
    signed_url = (signed_response.json() or {}).get("url", "")
    if not signed_url:
        raise ValueError("Zulip did not return a temporary upload URL")
    if signed_url.startswith("/"):
        signed_url = f"{ZULIP_SITE_URL}{signed_url}"

    with requests.get(signed_url, stream=True, timeout=60) as response:
        response.raise_for_status()

        content_length = response.headers.get("content-length")
        if content_length and int(content_length) > max_bytes:
            raise ValueError(f"Attachment too large: {int(content_length)} bytes > {max_bytes} bytes")

        filename = sanitize_filename(filename_from_response(signed_url, response))
        if filename == "zulip-attachment.bin":
            filename = sanitize_filename(upload_filename(upload_path))
        output_path = target_dir / filename

        total = 0
        with output_path.open("wb") as f:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if not chunk:
                    continue

                total += len(chunk)
                if total > max_bytes:
                    raise ValueError(f"Attachment exceeded max size while downloading: {MAX_DOWNLOAD_MB} MB")

                f.write(chunk)

    return output_path


def clean_extracted_text(text: str) -> str:
    """
    Light cleanup for PDF/document extraction.

    It does not try to fully reconstruct tables, but improves common PDF artifacts:
    - excessive blank lines
    - task keys split as AC-\n765
    - bracketed Jira keys split across lines
    """
    text = text or ""

    # Normalize newlines.
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    # Fix Jira keys split by PDF extraction.
    text = re.sub(r"\b([A-Z]+)-\s*\n\s*(\d+)\b", r"\1-\2", text)

    # Fix bracketed keys split as:
    # [
    # AC-12
    # ]
    text = re.sub(r"\[\s*\n\s*([A-Z]+-\d+)\s*\n\s*\]", r"[\1]", text)

    # Fix broken Markdown-ish links a little.
    text = re.sub(r"\|\s*\n\s*", "|", text)

    # Collapse 3+ blank lines into 2.
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()


def clean_pdf_markdown_noise(text: str) -> str:
    """
    Aggressive cleanup for noisy PDF/table Markdown extraction.
    Keeps useful task/status content and removes visual layout garbage.
    """
    text = text or ""

    text = text.replace("<br>", "\n")
    text = re.sub(r"\*\*==> picture \[[^\]]+\] intentionally omitted <==\*\*", "", text)
    text = re.sub(r"\*\*----- Start of picture text -----\*\*", "\n", text)
    text = re.sub(r"\*\*----- End of picture text -----\*\*", "\n", text)

    # Remove markdown table separator garbage.
    text = re.sub(r"\|{2,}", "\n", text)
    text = re.sub(r"(?m)^\s*\|?\s*-{3,}(\s*\|\s*-{3,})+\s*\|?\s*$", "", text)

    # Fix split Jira keys: AC-\n765 -> AC-765
    text = re.sub(r"\b([A-Z]+)-\s*\n\s*(\d+)\b", r"\1-\2", text)

    # Fix bracketed keys: [\nAC-12\n] -> [AC-12]
    text = re.sub(r"\[\s*\n\s*([A-Z]+-\d+)\s*\n\s*\]", r"[\1]", text)

    # Remove excessive bold markers but keep content.
    text = text.replace("**", "")

    # Normalize repeated whitespace/newlines.
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r"\n\s*\n\s*\n+", "\n\n", text)

    return text.strip()


def extract_relevant_daily_status_sections(text: str) -> str:
    """
    Daily-status PDFs are huge. This keeps the parts that matter most for prioritization.
    """
    cleaned = clean_pdf_markdown_noise(text)

    # Keep everything for now, but add a machine-readable hint at the top.
    header = """
# Daily Status extraction notes

This text came from a PDF report and may contain table-layout artifacts.
When analyzing it, prioritize:
- task keys like AC-123 / ACSEC-123
- statuses like TO DO, IN PROGRESS, IN QA, ON HOLD, ACCEPTANCE IN PROCESS
- assignees
- blockers/problems
- "Next Tasks"
- "Task Priorities Summary"

Do not rely on table column alignment.
""".strip()

    return header + "\n\n" + cleaned


def markdown_from_file(path: Path) -> str:
    """
    Generic document conversion through MarkItDown.

    Good for Office files, CSV, HTML, JSON, images metadata/OCR support, etc.
    For PDFs, extract_file_text() now tries dedicated PDF strategies first.
    """
    md = MarkItDown(enable_plugins=False)
    result = md.convert(str(path))

    text = getattr(result, "text_content", None)
    if text is None:
        text = getattr(result, "markdown", None)

    return clean_extracted_text(text or "")


def pdf_to_markdown_pymupdf4llm(path: Path) -> str:
    """
    Better PDF-to-Markdown extraction for layout-heavy PDFs.

    This is usually better than MarkItDown/pdfminer for reports with tables.
    """
    import pymupdf4llm

    text = pymupdf4llm.to_markdown(str(path))
    return clean_extracted_text(text)


def pdf_to_text_pymupdf(path: Path) -> str:
    """
    Fallback PDF text extraction using PyMuPDF with sorted text order.

    This often gives more readable text than pdfminer for some generated PDFs,
    though it may still not reconstruct tables perfectly.
    """
    import fitz

    doc = fitz.open(str(path))
    pages = []

    for page_index, page in enumerate(doc, start=1):
        text = page.get_text("text", sort=True)
        text = clean_extracted_text(text)

        if text:
            pages.append(f"# Page {page_index}\n\n{text}")

    return "\n\n".join(pages).strip()


def extract_pdf_text(path: Path) -> str:
    """
    PDF-specific extraction pipeline.

    Strategy order:
    1. PyMuPDF4LLM: best chance to preserve layout/markdown.
    2. MarkItDown: general converter.
    3. PyMuPDF sorted text: simpler but often stable.
    4. OCR fallback: for scanned/image PDFs.
    """
    attempts: list[tuple[str, str]] = []
    errors: list[str] = []

    try:
        text = pdf_to_markdown_pymupdf4llm(path)
        if text:
            attempts.append(("PyMuPDF4LLM extraction", text))
    except Exception as exc:
        errors.append(f"PyMuPDF4LLM error: {type(exc).__name__}: {exc}")

    try:
        text = markdown_from_file(path)
        if text:
            attempts.append(("MarkItDown extraction", text))
    except Exception as exc:
        errors.append(f"MarkItDown error: {type(exc).__name__}: {exc}")

    try:
        text = pdf_to_text_pymupdf(path)
        if text:
            attempts.append(("PyMuPDF sorted-text extraction", text))
    except Exception as exc:
        errors.append(f"PyMuPDF text error: {type(exc).__name__}: {exc}")

    # Pick the best non-OCR extraction.
    # Heuristic: prefer the first extractor that returns enough text.
    for label, text in attempts:
        if len(text.strip()) >= OCR_MIN_TEXT_CHARS:
            return f"## {label}\n{extract_relevant_daily_status_sections(text)}"

    # If all text extraction is weak, try OCR.
    try:
        ocr_text = ocr_pdf_file(path)
        if ocr_text:
            return "## OCR fallback extraction\n" + extract_relevant_daily_status_sections(ocr_text)
    except Exception as exc:
        errors.append(f"OCR error: {type(exc).__name__}: {exc}")

    if attempts:
        label, text = attempts[0]
        return f"## {label}\n{extract_relevant_daily_status_sections(text)}"

    if errors:
        return "\n".join(errors)

    return "No text could be extracted from this PDF."


def configure_tesseract() -> None:
    """Configure the optional Tesseract executable.

    Returns
    -------
    None
        The operation completes through side effects.
    """
    try:
        import pytesseract

        if TESSERACT_CMD and Path(TESSERACT_CMD).exists():
            pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD
    except Exception:
        pass


def ocr_image_file(path: Path) -> str:
    """Run OCR over an image file.

    Parameters
    ----------
    path : Path
        Local filesystem path.

    Returns
    -------
    str
        Text produced by the helper.
    """
    configure_tesseract()

    import pytesseract
    from PIL import Image

    image = Image.open(path)
    try:
        return pytesseract.image_to_string(image, lang=OCR_LANGUAGE).strip()
    except pytesseract.TesseractError:
        # Fallback for installs that only have English traineddata.
        return pytesseract.image_to_string(image, lang="eng").strip()


def ocr_gif_file(path: Path) -> str:
    """Run OCR over sampled GIF frames.

    Parameters
    ----------
    path : Path
        Local filesystem path.

    Returns
    -------
    str
        Text produced by the helper.
    """
    configure_tesseract()

    import pytesseract
    from PIL import Image, ImageSequence

    image = Image.open(path)
    lines = [f"# OCR from GIF: {path.name}"]

    for index, frame in enumerate(ImageSequence.Iterator(image)):
        if index >= OCR_MAX_GIF_FRAMES:
            break

        frame = frame.convert("RGB")
        try:
            text = pytesseract.image_to_string(frame, lang=OCR_LANGUAGE).strip()
        except pytesseract.TesseractError:
            text = pytesseract.image_to_string(frame, lang="eng").strip()

        if text:
            lines.append(f"\n## Frame {index + 1}\n{text}")

    return "\n".join(lines).strip()


def ocr_pdf_file(path: Path) -> str:
    """Render and OCR a bounded number of PDF pages.

    Parameters
    ----------
    path : Path
        Local filesystem path.

    Returns
    -------
    str
        Text produced by the helper.
    """
    configure_tesseract()

    import fitz  # PyMuPDF
    import pytesseract
    from PIL import Image

    doc = fitz.open(str(path))
    lines = [f"# OCR from PDF: {path.name}"]

    total_pages = min(len(doc), OCR_MAX_PDF_PAGES)

    for page_index in range(total_pages):
        page = doc.load_page(page_index)
        pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
        image = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

        try:
            text = pytesseract.image_to_string(image, lang=OCR_LANGUAGE).strip()
        except pytesseract.TesseractError:
            text = pytesseract.image_to_string(image, lang="eng").strip()

        if text:
            lines.append(f"\n## Page {page_index + 1}\n{text}")

    if len(doc) > total_pages:
        lines.append(
            f"\n[OCR truncated: processed {total_pages}/{len(doc)} pages. Increase ZULIP_OCR_MAX_PDF_PAGES if needed.]"
        )

    return "\n".join(lines).strip()


def fallback_ocr(path: Path) -> str:
    """Run an OCR fallback selected by file type.

    Parameters
    ----------
    path : Path
        Local filesystem path.

    Returns
    -------
    str
        Text produced by the helper.
    """
    ext = path.suffix.lower()

    image_exts = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}

    if ext in image_exts:
        return ocr_image_file(path)

    if ext == ".gif":
        return ocr_gif_file(path)

    if ext == ".pdf":
        return ocr_pdf_file(path)

    return ""


def extract_file_text(path: Path) -> str:
    """
    Convert attachment into Markdown/text.

    Strategy:
    - PDF: PyMuPDF4LLM -> MarkItDown -> PyMuPDF sorted text -> OCR.
    - Other files: MarkItDown -> OCR fallback for images/GIFs when needed.
    """
    ext = path.suffix.lower()

    if ext == ".pdf":
        return extract_pdf_text(path)

    markitdown_text = ""
    markitdown_error = ""

    try:
        markitdown_text = markdown_from_file(path)
    except Exception as exc:
        markitdown_error = f"{type(exc).__name__}: {exc}"

    should_ocr = len(markitdown_text.strip()) < OCR_MIN_TEXT_CHARS

    ocr_text = ""
    ocr_error = ""

    if should_ocr:
        try:
            ocr_text = fallback_ocr(path)
        except Exception as exc:
            ocr_error = f"{type(exc).__name__}: {exc}"

    parts = []

    if markitdown_text:
        parts.append("## MarkItDown extraction\n" + markitdown_text)

    if ocr_text and ocr_text not in markitdown_text:
        parts.append("## OCR fallback extraction\n" + clean_extracted_text(ocr_text))

    if not parts:
        errors = []
        if markitdown_error:
            errors.append(f"MarkItDown error: {markitdown_error}")
        if ocr_error:
            errors.append(f"OCR error: {ocr_error}")

        if errors:
            return "\n".join(errors)

        return "No text could be extracted from this file."

    return "\n\n".join(parts).strip()


def truncate_text(text: str, max_chars: int) -> str:
    """Truncate extracted text for prompt-safe output.

    Parameters
    ----------
    text : str
        Source text.
    max_chars : int
        Input value.

    Returns
    -------
    str
        Text produced by the helper.
    """
    text = text or ""
    if len(text) <= max_chars:
        return text

    return text[:max_chars].rstrip() + f"\n\n[Truncated to {max_chars} characters.]"


def get_message_by_id(message_id: int) -> dict:
    """Fetch a Zulip message by identifier.

    Parameters
    ----------
    message_id : int
        Zulip message identifier.

    Returns
    -------
    dict
        Normalized data produced by the helper.
    """
    url = f"{ZULIP_SITE_URL}/api/v1/messages/{message_id}"

    response = requests.get(
        url,
        auth=(ZULIP_BOT_EMAIL, ZULIP_API_KEY),
        timeout=30,
    )
    response.raise_for_status()

    data = response.json()

    if data.get("result") != "success":
        raise RuntimeError(f"Zulip API error: {data}")

    # Newer Zulip returns {"message": {...}}.
    if "message" in data:
        return data["message"]

    # Fallback if server shape differs.
    return data


def get_recent_messages(
    channel: str,
    topic: str | None = None,
    limit: int = 200,
    today_only: bool = False,
    query: str | None = None,
    timezone: str = DEFAULT_TIMEZONE,
) -> list[dict]:
    """Fetch recent Zulip messages for a channel and topic window.

    Parameters
    ----------
    channel : str
        Zulip channel or stream name.
    topic : str | None
        Zulip topic name.
    limit : int
        Maximum output size.
    today_only : bool
        Input value.
    query : str | None
        Full-text search query.
    timezone : str
        Input value.

    Returns
    -------
    list[dict]
        Result produced by the helper.
    """
    tz = ZoneInfo(timezone)
    today = datetime.now(tz).date()

    client = get_client()

    narrow = [{"operator": "stream", "operand": channel}]

    if topic:
        narrow.append({"operator": "topic", "operand": topic})

    if query:
        narrow.append({"operator": "search", "operand": query})

    result = client.get_messages(
        {
            "anchor": "newest",
            "num_before": min(limit, 5000),
            "num_after": 0,
            "narrow": narrow,
        }
    )

    if result.get("result") != "success":
        raise RuntimeError(f"Zulip API error: {result}")

    messages = result.get("messages", [])

    if not today_only:
        return messages

    filtered = []
    for msg in messages:
        ts = datetime.fromtimestamp(msg["timestamp"], tz)
        if ts.date() == today:
            filtered.append(msg)

    return filtered


def render_attachment_summary_for_message(msg: dict) -> str:
    """Render attachment links for a message summary.

    Parameters
    ----------
    msg : dict
        Zulip message payload.

    Returns
    -------
    str
        Text produced by the helper.
    """
    candidates = extract_attachment_candidates_from_message(msg)

    if not candidates:
        return ""

    lines = [
        f"Attachments detected for message_id={msg.get('id')}:",
    ]

    for index, item in enumerate(candidates, start=1):
        lines.append(f"- attachment_{index}: {item.label} | {item.url}")

    return "\n".join(lines)


def extract_candidates_from_messages(messages: Iterable[dict]) -> list[tuple[dict, AttachmentCandidate]]:
    """Collect safe attachment candidates from messages.

    Parameters
    ----------
    messages : Iterable[dict]
        Zulip messages to process.

    Returns
    -------
    list[tuple[dict, AttachmentCandidate]]
        Result produced by the helper.
    """
    results: list[tuple[dict, AttachmentCandidate]] = []

    # Zulip commonly returns messages oldest -> newest for a window.
    # Reverse so "recent attachments" means newest attachments first.
    ordered_messages = sorted(
        list(messages),
        key=lambda msg: msg.get("timestamp", 0),
        reverse=True,
    )

    for msg in ordered_messages:
        for candidate in extract_attachment_candidates_from_message(msg):
            results.append((msg, candidate))

    return results


def convert_candidates_to_text(
    items: list[tuple[dict | None, AttachmentCandidate]],
    max_files: int = MAX_ATTACHMENT_FILES,
    max_chars_per_file: int = MAX_CHARS_PER_FILE,
    max_total_chars: int = MAX_TOTAL_CHARS,
) -> str:
    """Download attachments and convert them to text.

    Parameters
    ----------
    items : list[tuple[dict | None, AttachmentCandidate]]
        Input value.
    max_files : int
        Input value.
    max_chars_per_file : int
        Input value.
    max_total_chars : int
        Input value.

    Returns
    -------
    str
        Text produced by the helper.
    """
    if not items:
        return "No Zulip upload attachments found."

    lines = [
        "# Extracted Zulip attachments",
        "",
        "Only files hosted under this Zulip server's /user_uploads/ path are downloaded.",
        "",
    ]

    total_chars = 0

    with tempfile.TemporaryDirectory(prefix="zulip-attachments-") as tmp:
        tmp_dir = Path(tmp)

        for index, (msg, candidate) in enumerate(items[:max_files], start=1):
            header = [f"## Attachment {index}: {candidate.label}"]

            if msg:
                header.append(f"- message_id: {msg.get('id')}")
                header.append(f"- sender: {msg.get('sender_full_name') or msg.get('sender_email')}")
                header.append(f"- topic: {msg_topic(msg)}")

            header.append(f"- url: {candidate.url}")

            try:
                path = download_attachment(candidate, tmp_dir)
                extracted = extract_file_text(path)
                extracted = truncate_text(extracted, max_chars_per_file)

                block = "\n".join(header) + "\n\n" + extracted
            except Exception as exc:
                block = "\n".join(header) + f"\n\nFailed to extract attachment: {type(exc).__name__}: {exc}"

            remaining = max_total_chars - total_chars
            if remaining <= 0:
                lines.append("\n[Total output truncated.]")
                break

            block = truncate_text(block, remaining)
            total_chars += len(block)
            lines.append(block)

    if len(items) > max_files:
        lines.append(f"\n[Skipped {len(items) - max_files} attachment(s); max_files={max_files}.]")

    return "\n\n".join(lines)


_CHUNK_MARKER_RE = re.compile(r" \((\d+)/(\d+)\)\s*$")
_SEARCH_OPERATOR_RE = re.compile(
    r"\b(?:sender|from|stream|channel|topic|pm-with|dm|dm-including|has|is|near|id|group-id|streams|channels):\S+",
    re.IGNORECASE,
)
_CLIENT_SCAN_WINDOW = 200
_CLIENT_SCAN_MAX_PAGES = 3


def _content_needles_from_query(query: str | None) -> list[str]:
    """Extract literal text needles from a Zulip search query."""
    if not query or not str(query).strip():
        return []
    text = str(query).strip()
    needles: list[str] = []

    for match in re.finditer(r'"([^"]+)"', text):
        phrase = match.group(1).strip()
        if phrase:
            needles.append(phrase)

    text_no_quotes = re.sub(r'"[^"]*"', " ", text)
    text_no_ops = _SEARCH_OPERATOR_RE.sub(" ", text_no_quotes)
    for token in text_no_ops.split():
        token = token.strip()
        if token and token.lower() not in {"and", "or", "not", "-"}:
            needles.append(token)

    seen: set[str] = set()
    unique: list[str] = []
    for needle in needles:
        key = needle.casefold()
        if key in seen:
            continue
        seen.add(key)
        unique.append(needle)
    return unique


def _content_matches_needles(content: str, needles: list[str]) -> bool:
    """Check whether message content contains every search term.

    Parameters
    ----------
    content : str
        Zulip message content.
    needles : list[str]
        Normalized search terms.

    Returns
    -------
    bool
        Whether the requested condition is true.
    """
    if not needles:
        return True
    haystack = (content or "").casefold()
    return all(needle.casefold() in haystack for needle in needles)


def _parse_chunk_marker(content: str) -> tuple[str, int, int] | None:
    """Parse a trailing Hermes chunk marker.

    Parameters
    ----------
    content : str
        Zulip message content.

    Returns
    -------
    tuple[str, int, int] | None
        Result produced by the helper.
    """
    if not content:
        return None
    match = _CHUNK_MARKER_RE.search(content)
    if not match:
        return None
    index = int(match.group(1))
    total = int(match.group(2))
    if index < 1 or total < 2 or index > total:
        return None
    return content[: match.start()], index, total


def _format_raw_search_message(msg: dict[str, Any]) -> dict[str, Any]:
    """Normalize a raw Zulip message for search output.

    Parameters
    ----------
    msg : dict[str, Any]
        Zulip message payload.

    Returns
    -------
    dict[str, Any]
        Result produced by the helper.
    """
    return {
        "id": msg.get("id"),
        "sender": msg.get("sender_full_name") or msg.get("sender_email", "?"),
        "sender_email": msg.get("sender_email") or "",
        "timestamp": msg.get("timestamp", 0),
        "content": (msg.get("content") or "").strip(),
        "is_bot": msg.get("sender_email") == ZULIP_BOT_EMAIL,
    }


def _merge_messages_by_id(primary: list[dict[str, Any]], extra: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Merge message lists while preserving one item per message ID.

    Parameters
    ----------
    primary : list[dict[str, Any]]
        Input value.
    extra : list[dict[str, Any]]
        Input value.

    Returns
    -------
    list[dict[str, Any]]
        Result produced by the helper.
    """
    by_id: dict[Any, dict[str, Any]] = {}
    for msg in extra:
        if msg.get("id") is not None:
            by_id[msg["id"]] = msg
    for msg in primary:
        if msg.get("id") is not None:
            by_id[msg["id"]] = msg
    return list(by_id.values())


def _client_content_scan(
    client: Any,
    *,
    scope_narrow: list[dict[str, str]] | None,
    needles: list[str],
    anchor: Any,
    window: int = _CLIENT_SCAN_WINDOW,
    max_pages: int = _CLIENT_SCAN_MAX_PAGES,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Fetch recent history and keep messages whose raw body contains needles."""
    meta: dict[str, Any] = {"scanned": False, "pages": 0, "found_oldest": None, "found_newest": None}
    if not needles:
        return [], meta

    hits: list[dict[str, Any]] = []
    seen_ids: set[Any] = set()
    page_anchor: Any = anchor if anchor not in (None, "") else "newest"

    for _ in range(max_pages):
        result = client.get_messages(
            {
                "anchor": page_anchor,
                "num_before": window,
                "num_after": 0,
                "narrow": scope_narrow or None,
                "apply_markdown": False,
            }
        )
        if result.get("result") != "success":
            break
        meta["scanned"] = True
        meta["pages"] += 1
        meta["found_oldest"] = result.get("found_oldest")
        meta["found_newest"] = result.get("found_newest")
        page_messages = list(result.get("messages") or [])
        if not page_messages:
            break

        for raw in page_messages:
            mid = raw.get("id")
            if mid is None or mid in seen_ids:
                continue
            seen_ids.add(mid)
            if _content_matches_needles(raw.get("content") or "", needles):
                hits.append(raw)

        oldest = min((m.get("id") for m in page_messages if m.get("id") is not None), default=None)
        if oldest is None or result.get("found_oldest") or hits:
            break
        page_anchor = oldest

    return hits, meta


def _expand_partial_hermes_chunks(
    client: Any,
    messages: list[dict[str, Any]],
    *,
    narrow: list[dict[str, str]] | None,
    max_expansions: int = 5,
) -> list[dict[str, Any]]:
    """Expand partial long-reply chunks into complete groups.

    Parameters
    ----------
    client : Any
        Authenticated Zulip API client.
    messages : list[dict[str, Any]]
        Zulip messages to process.
    narrow : list[dict[str, str]] | None
        Input value.
    max_expansions : int
        Input value.

    Returns
    -------
    list[dict[str, Any]]
        Result produced by the helper.
    """
    by_id = {m["id"]: m for m in messages if m.get("id") is not None}
    expansions = 0
    for msg in list(by_id.values()):
        if expansions >= max_expansions:
            break
        parsed = _parse_chunk_marker(msg.get("content") or "")
        if not parsed:
            continue
        _, index, total = parsed
        sender = msg.get("sender_email") or msg.get("sender") or ""
        have = sum(
            1
            for other in by_id.values()
            if (other.get("sender_email") or other.get("sender") or "") == sender
            and (p := _parse_chunk_marker(other.get("content") or ""))
            and p[2] == total
        )
        if have >= total:
            continue
        result = client.get_messages(
            {
                "anchor": msg["id"],
                "num_before": min(max(0, index - 1) + 2, 20),
                "num_after": min(max(0, total - index) + 2, 20),
                "narrow": narrow or None,
                "apply_markdown": False,
            }
        )
        if result.get("result") != "success":
            continue
        expansions += 1
        for raw in result.get("messages") or []:
            if raw.get("id") is not None and raw.get("id") not in by_id:
                by_id[raw["id"]] = _format_raw_search_message(raw)
    return list(by_id.values())


def _reassemble_hermes_chunks(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Merge complete '(i/n)' chunk series from the same sender into one item."""
    if len(messages) < 2:
        return messages
    ordered = sorted(
        messages,
        key=lambda m: (m.get("id") is None, m.get("id") or 0, m.get("timestamp") or 0),
    )
    out: list[dict[str, Any]] = []
    i = 0
    while i < len(ordered):
        msg = ordered[i]
        parsed = _parse_chunk_marker(msg.get("content") or "")
        if parsed is None or parsed[1] != 1:
            out.append(msg)
            i += 1
            continue

        body, _, total = parsed
        sender_key = msg.get("sender_email") or msg.get("sender") or ""
        group = [(msg, body)]
        j = i + 1
        expected = 2
        while j < len(ordered) and expected <= total:
            nxt = ordered[j]
            if (nxt.get("sender_email") or nxt.get("sender") or "") != sender_key:
                break
            nxt_parsed = _parse_chunk_marker(nxt.get("content") or "")
            if not nxt_parsed:
                break
            nxt_body, nxt_index, nxt_total = nxt_parsed
            if nxt_total != total or nxt_index != expected:
                break
            group.append((nxt, nxt_body))
            expected += 1
            j += 1

        if len(group) != total:
            out.extend(piece for piece, _ in group)
            i = j
            continue

        first = group[0][0]
        last = group[-1][0]
        out.append(
            {
                "id": first.get("id"),
                "sender": first.get("sender"),
                "sender_email": first.get("sender_email", ""),
                "timestamp": first.get("timestamp", 0),
                "content": "\n".join(part_body for _, part_body in group),
                "is_bot": first.get("is_bot", False),
                "chunk_ids": [piece.get("id") for piece, _ in group],
                "chunk_count": total,
                "newest_chunk_id": last.get("id"),
            }
        )
        i = j

    out.sort(key=lambda m: (m.get("id") is None, m.get("id") or 0))
    return out


@mcp.tool()
def zulip_search_messages(
    channel: str | None = None,
    stream: str | None = None,
    topic: str | None = None,
    query: str | None = None,
    anchor: str | int | None = None,
    num_before: int = 20,
    num_after: int = 0,
) -> str:
    """
    Search Zulip message history with stream/topic filters, text query, anchor pagination,
    client-side fallback scanning, and reassembly of long chunked Hermes replies.
    """
    if not ZULIP_SITE_URL or not ZULIP_BOT_EMAIL or not ZULIP_API_KEY:
        return json.dumps({"error": "Zulip credentials are not configured"})

    try:
        num_before = max(0, min(int(num_before), 5000))
        num_after = max(0, min(int(num_after), 5000))
    except (TypeError, ValueError):
        return json.dumps({"error": "num_before and num_after must be integers"})

    channel = channel or stream

    scope_narrow: list[dict[str, str]] = []
    if channel:
        scope_narrow.append({"operator": "stream", "operand": channel})
    if topic:
        scope_narrow.append({"operator": "topic", "operand": topic})

    fts_text = (query or "").strip() or None
    fts_narrow = list(scope_narrow)
    if fts_text:
        fts_narrow.append({"operator": "search", "operand": fts_text})

    anchor_value: Any = anchor if anchor not in (None, "") else "newest"
    client = get_client()

    try:
        result = client.get_messages(
            {
                "anchor": anchor_value,
                "num_before": num_before,
                "num_after": num_after,
                "narrow": fts_narrow or None,
                "apply_markdown": False,
            }
        )
    except Exception as exc:
        return json.dumps({"error": f"Zulip API error: {type(exc).__name__}: {exc}"})

    if result.get("result") != "success":
        return json.dumps({"error": result.get("msg", "Unknown Zulip error")})

    messages = list(result.get("messages") or [])
    found_oldest = result.get("found_oldest", False)
    found_newest = result.get("found_newest", False)
    used_client_scan = False

    needles = _content_needles_from_query(fts_text)
    if needles:
        try:
            scanned, meta = _client_content_scan(
                client,
                scope_narrow=scope_narrow or None,
                needles=needles,
                anchor=anchor_value,
            )
        except Exception:
            scanned, meta = [], {"scanned": False}
        used_client_scan = bool(scanned) or bool(meta.get("scanned"))
        if scanned:
            messages = _merge_messages_by_id(messages, scanned)
            if meta.get("found_oldest") is not None:
                found_oldest = meta["found_oldest"]
            if meta.get("found_newest") is not None:
                found_newest = meta["found_newest"]

    formatted = [_format_raw_search_message(msg) for msg in messages]
    formatted = _expand_partial_hermes_chunks(client, formatted, narrow=scope_narrow or None)
    formatted = _reassemble_hermes_chunks(formatted)

    if needles:
        filtered = [m for m in formatted if _content_matches_needles(m.get("content") or "", needles)]
        if filtered or used_client_scan:
            formatted = filtered

    for entry in formatted:
        entry.pop("sender_email", None)

    oldest_id = min((m["id"] for m in formatted if m.get("id") is not None), default=None)
    newest_id = max((m["id"] for m in formatted if m.get("id") is not None), default=None)

    payload: dict[str, Any] = {
        "messages": formatted,
        "count": len(formatted),
        "requested_before": num_before,
        "requested_after": num_after,
        "oldest_message_id": oldest_id,
        "newest_message_id": newest_id,
        "found_oldest": found_oldest,
        "found_newest": found_newest,
        "pagination_hint": (
            f"To get older messages, call again with anchor={oldest_id}, num_before={num_before}, num_after=0. "
            f"To get newer messages, call with anchor={newest_id}, num_before=0, num_after={num_after or 20}."
            if formatted
            else ""
        ),
        "client_content_scan": used_client_scan,
    }
    if used_client_scan:
        payload["note"] = (
            "Results include a client-side content scan because Zulip full-text search can lag or miss long bot replies."
        )
    if not formatted:
        payload["note"] = "No messages matched the search criteria."
    return json.dumps(payload)


@mcp.tool()
def zulip_list_topics(channel_id: int = 202) -> str:
    """
    List topics in a Zulip channel by channel/stream ID.

    Use this when the user asks which topics exist in a channel or when the topic name is unclear.
    This tool is read-only.
    """
    client = get_client()
    result = client.get_stream_topics(channel_id)

    if result.get("result") != "success":
        return f"Zulip API error: {result}"

    topics = result.get("topics", [])

    if not topics:
        return f"No topics found for channel_id={channel_id}."

    lines = [f"# Zulip topics for channel_id={channel_id}"]

    for topic in topics:
        lines.append(f"- {topic['name']} | max_id={topic.get('max_id')}")

    return "\n".join(lines)


@mcp.tool()
def zulip_read_messages(
    channel: str = DEFAULT_CHANNEL,
    topic: str | None = None,
    limit: int = 200,
    today_only: bool = False,
    query: str | None = None,
    timezone: str = DEFAULT_TIMEZONE,
) -> str:
    """
    Read recent messages from a Zulip channel or topic.

    This includes message IDs and detected Zulip upload attachment URLs.
    Use message_id with zulip_extract_message_attachments to extract attachments.

    This tool is read-only.
    """
    tz = ZoneInfo(timezone)

    try:
        messages = get_recent_messages(
            channel=channel,
            topic=topic,
            limit=limit,
            today_only=today_only,
            query=query,
            timezone=timezone,
        )
    except Exception as exc:
        return f"Zulip API error: {type(exc).__name__}: {exc}"

    today = datetime.now(tz).date()

    lines = [
        "# Zulip messages",
        f"Channel: {channel}",
    ]

    if topic:
        lines.append(f"Topic: {topic}")

    if today_only:
        lines.append(f"Date filter: {today.isoformat()}")

    if query:
        lines.append(f"Search query: {query}")

    lines.append("")

    count = 0

    for msg in messages:
        content = html_to_text(msg.get("content", ""))
        if not content:
            continue

        lines.append(format_message(msg, tz))

        attachment_summary = render_attachment_summary_for_message(msg)
        if attachment_summary:
            lines.append(attachment_summary)

        count += 1

    if count == 0:
        lines.append("No messages matched this filter.")

    return "\n".join(lines)


@mcp.tool()
def zulip_priority_context(
    channel: str = DEFAULT_CHANNEL,
    topic: str = DEFAULT_TOPIC,
    hours_back: int = 24,
    limit: int = 500,
    timezone: str = DEFAULT_TIMEZONE,
    include_attachment_links: bool = True,
) -> str:
    """
    Read Zulip context optimized for extracting priorities, blockers, owners,
    decisions, and follow-ups.

    Default target is the configured status channel/topic.
    This tool includes attachment links but does not extract attachment contents.
    Use zulip_extract_recent_attachments or zulip_extract_message_attachments for file contents.

    This tool is read-only.
    """
    tz = ZoneInfo(timezone)
    now = datetime.now(tz)
    cutoff = now - timedelta(hours=hours_back)

    try:
        messages = get_recent_messages(
            channel=channel,
            topic=topic,
            limit=limit,
            today_only=False,
            query=None,
            timezone=timezone,
        )
    except Exception as exc:
        return f"Zulip API error: {type(exc).__name__}: {exc}"

    lines = [
        "# Zulip priority context",
        f"Channel: {channel}",
        f"Topic: {topic}",
        f"Window: last {hours_back} hours",
        "",
        "Use these messages to extract:",
        "- priorities",
        "- blockers",
        "- owners",
        "- decisions",
        "- questions addressed to the user",
        "- messages that need a reply",
        "",
    ]

    count = 0

    for msg in messages:
        ts = datetime.fromtimestamp(msg["timestamp"], tz)

        if ts < cutoff:
            continue

        content = html_to_text(msg.get("content", ""))
        if not content:
            continue

        lines.append(format_message(msg, tz))

        if include_attachment_links:
            attachment_summary = render_attachment_summary_for_message(msg)
            if attachment_summary:
                lines.append(attachment_summary)

        count += 1

    if count == 0:
        lines.append("No recent messages found in this window.")

    return "\n".join(lines)


@mcp.tool()
def zulip_extract_recent_attachments(
    channel: str = DEFAULT_CHANNEL,
    topic: str | None = None,
    limit: int = 200,
    today_only: bool = False,
    query: str | None = None,
    max_files: int = MAX_ATTACHMENT_FILES,
    max_chars_per_file: int = MAX_CHARS_PER_FILE,
    timezone: str = DEFAULT_TIMEZONE,
) -> str:
    """
    Find recent Zulip upload attachments in a channel/topic, download them,
    and extract their contents.

    Uses MarkItDown first, then Tesseract OCR fallback for images/GIFs/PDFs when needed.

    This only downloads files hosted by this Zulip server under /user_uploads/.
    This tool is read-only.
    """
    try:
        messages = get_recent_messages(
            channel=channel,
            topic=topic,
            limit=limit,
            today_only=today_only,
            query=query,
            timezone=timezone,
        )
    except Exception as exc:
        return f"Zulip API error: {type(exc).__name__}: {exc}"

    items = extract_candidates_from_messages(messages)

    return convert_candidates_to_text(
        items=items,
        max_files=max_files,
        max_chars_per_file=max_chars_per_file,
        max_total_chars=MAX_TOTAL_CHARS,
    )


@mcp.tool()
def zulip_extract_message_attachments(
    message_id: int,
    max_files: int = MAX_ATTACHMENT_FILES,
    max_chars_per_file: int = MAX_CHARS_PER_FILE,
) -> str:
    """
    Download and extract all Zulip upload attachments from a specific message ID.

    Use this after zulip_read_messages returns a message_id with attachment links.

    Uses MarkItDown first, then Tesseract OCR fallback for images/GIFs/PDFs when needed.
    This only downloads files hosted by this Zulip server under /user_uploads/.
    This tool is read-only.
    """
    try:
        msg = get_message_by_id(message_id)
    except Exception as exc:
        return f"Failed to fetch message_id={message_id}: {type(exc).__name__}: {exc}"

    items = [(msg, candidate) for candidate in extract_attachment_candidates_from_message(msg)]

    return convert_candidates_to_text(
        items=items,
        max_files=max_files,
        max_chars_per_file=max_chars_per_file,
        max_total_chars=MAX_TOTAL_CHARS,
    )


@mcp.tool()
def zulip_extract_attachment_url(
    url: str,
    max_chars: int = MAX_CHARS_PER_FILE,
) -> str:
    """
    Download and extract a specific Zulip upload URL.

    The URL must belong to this Zulip server and be under /user_uploads/.
    Uses MarkItDown first, then Tesseract OCR fallback for images/GIFs/PDFs when needed.

    This tool is read-only.
    """
    full_url = normalize_url(url)

    if not safe_attachment_url(full_url):
        return "Refusing to download this URL. Only this Zulip server's /user_uploads/ URLs are allowed."

    candidate = AttachmentCandidate(url=full_url, label=Path(urlparse(full_url).path).name, source="manual")

    text = convert_candidates_to_text(
        items=[(None, candidate)],
        max_files=1,
        max_chars_per_file=max_chars,
        max_total_chars=max_chars + 2000,
    )

    return text


if __name__ == "__main__":
    mcp.run()
