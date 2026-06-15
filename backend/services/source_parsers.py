import hashlib
import json
import re
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path
from typing import Dict, Iterable, List, Optional


REPO_ROOT = Path(__file__).resolve().parents[2]
SOURCES_DIR = REPO_ROOT / "sources"


@dataclass
class ParsedSource:
    path: Path
    title: str
    source_url: Optional[str]
    source_type: str
    document_date: Optional[str]
    text: str
    parser: str
    warnings: List[str] = field(default_factory=list)


@dataclass
class SourceChunk:
    chunk_id: str
    source: ParsedSource
    text: str
    ordinal: int


class _ArticleHTMLParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.title_parts: List[str] = []
        self.body_parts: List[str] = []
        self.links: Dict[str, str] = {}
        self.json_ld: List[str] = []
        self._tag_stack: List[str] = []
        self._capture_json_ld = False
        self._json_buffer: List[str] = []
        self._in_title = False
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs):
        attrs_dict = dict(attrs)
        self._tag_stack.append(tag)
        if tag in {"script", "style", "noscript"}:
            if tag == "script" and attrs_dict.get("type") == "application/ld+json":
                self._capture_json_ld = True
                self._json_buffer = []
            else:
                self._skip_depth += 1
        if tag == "title":
            self._in_title = True
        if tag == "link" and attrs_dict.get("rel") == "canonical" and attrs_dict.get("href"):
            self.links["canonical"] = attrs_dict["href"]
        if tag in {"p", "li", "h1", "h2", "h3", "h4", "td", "th"}:
            self.body_parts.append("\n")

    def handle_endtag(self, tag: str):
        if tag == "title":
            self._in_title = False
        if tag == "script" and self._capture_json_ld:
            self.json_ld.append("".join(self._json_buffer))
            self._capture_json_ld = False
            self._json_buffer = []
        elif tag in {"script", "style", "noscript"} and self._skip_depth:
            self._skip_depth -= 1
        if tag in {"p", "li", "h1", "h2", "h3", "h4", "tr"}:
            self.body_parts.append("\n")
        if self._tag_stack:
            self._tag_stack.pop()

    def handle_data(self, data: str):
        if self._capture_json_ld:
            self._json_buffer.append(data)
            return
        if self._skip_depth:
            return
        cleaned = _normalize_whitespace(data)
        if not cleaned:
            return
        if self._in_title:
            self.title_parts.append(cleaned)
        self.body_parts.append(cleaned)
        self.body_parts.append(" ")


def parse_sources(sources_dir: Path = SOURCES_DIR) -> List[ParsedSource]:
    parsed: List[ParsedSource] = []
    for path in sorted(sources_dir.iterdir()):
        if path.suffix.lower() == ".html":
            parsed.append(parse_html_source(path))
        elif path.suffix.lower() == ".pdf":
            parsed.append(parse_pdf_source(path))
    return parsed


def parse_html_source(path: Path) -> ParsedSource:
    raw_html = path.read_text(encoding="utf-8", errors="ignore")
    parser = _ArticleHTMLParser()
    parser.feed(raw_html)

    title = _clean_title(" ".join(parser.title_parts)) or path.stem
    document_date = _json_ld_date(parser.json_ld) or _reviewed_date(parser.body_parts)
    text = _clean_extracted_text("\n".join(parser.body_parts))

    return ParsedSource(
        path=path,
        title=title,
        source_url=parser.links.get("canonical"),
        source_type=_source_type_for(path, title),
        document_date=document_date,
        text=text,
        parser="html",
    )


def parse_pdf_source(path: Path) -> ParsedSource:
    warnings: List[str] = []
    text = ""
    parser_name = "pdf"
    try:
        from pypdf import PdfReader

        reader = PdfReader(str(path))
        extracted_pages = []
        for page in reader.pages:
            page_text = ""
            try:
                page_text = page.extract_text(extraction_mode="layout") or ""
            except TypeError:
                page_text = ""
            if not page_text.strip():
                page_text = page.extract_text() or ""
            extracted_pages.append(page_text)
        text = "\n".join(extracted_pages)
    except Exception as exc:
        warnings.append(f"PDF text extraction failed: {exc}")
        parser_name = "pdf_failed"

    text = _clean_extracted_text(text)
    if _looks_garbled(text):
        warnings.append("Extracted PDF text appears garbled; OCR or manual review is recommended.")
        parser_name = "pdf_garbled"

    title = _title_from_pdf_filename(path)
    return ParsedSource(
        path=path,
        title=title,
        source_url=_known_pdf_url(path),
        source_type=_source_type_for(path, title),
        document_date=_date_from_filename(path.name),
        text=text,
        parser=parser_name,
        warnings=warnings,
    )


def chunk_source(source: ParsedSource, max_chars: int = 1400, overlap: int = 200) -> List[SourceChunk]:
    paragraphs = [paragraph.strip() for paragraph in re.split(r"\n{2,}", source.text) if paragraph.strip()]
    chunks: List[str] = []
    current = ""
    for paragraph in paragraphs:
        if len(current) + len(paragraph) + 2 <= max_chars:
            current = f"{current}\n\n{paragraph}".strip()
            continue
        if current:
            chunks.append(current)
        current = paragraph
    if current:
        chunks.append(current)

    if not chunks and source.text:
        chunks = [
            source.text[index : index + max_chars]
            for index in range(0, len(source.text), max_chars - overlap)
        ]

    return [
        SourceChunk(
            chunk_id=f"{_stable_id(source.path.name)}-{index:03d}",
            source=source,
            text=chunk,
            ordinal=index,
        )
        for index, chunk in enumerate(chunks, start=1)
    ]


def chunk_sources(sources: Iterable[ParsedSource]) -> List[SourceChunk]:
    chunks: List[SourceChunk] = []
    for source in sources:
        chunks.extend(chunk_source(source))
    return chunks


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _json_ld_date(json_ld_blocks: List[str]) -> Optional[str]:
    for block in json_ld_blocks:
        try:
            data = json.loads(block)
        except json.JSONDecodeError:
            continue
        graph = data.get("@graph", []) if isinstance(data, dict) else []
        for item in graph:
            if isinstance(item, dict) and item.get("datePosted"):
                return item["datePosted"][:10]
    return None


def _reviewed_date(parts: List[str]) -> Optional[str]:
    text = " ".join(parts)
    match = re.search(r"Page Last Reviewed or Updated:\s*([A-Za-z]+\s+\d{1,2},\s+\d{4})", text)
    return match.group(1) if match else None


def _source_type_for(path: Path, title: str) -> str:
    name = f"{path.name} {title}".lower()
    if path.suffix.lower() == ".html" and ("irs" in name or "internal revenue service" in name):
        return "irs_html"
    if "publication" in name or "irs" in name or "internal revenue service" in name:
        return "irs_pdf"
    if "georgia power" in name or "heip" in name:
        return "utility_rebate_pdf"
    if "hear" in name or "energy rebates" in name:
        return "state_rebate_pdf"
    return "source_document"


def _title_from_pdf_filename(path: Path) -> str:
    return re.sub(r"\s+", " ", path.stem.replace("_", " ")).strip()


def _known_pdf_url(path: Path) -> Optional[str]:
    lower_name = path.name.lower()
    if "hear" in lower_name:
        return "https://energyrebates.georgia.gov"
    if "heip" in lower_name:
        return "https://www.georgiapower.com/residential/save-money-and-energy/products-programs/home-energy-improvement.html"
    if "p5967" in lower_name or "p5886a" in lower_name:
        publication = re.search(r"p\d+[a-z]?", lower_name)
        if publication:
            return f"https://www.irs.gov/pub/irs-pdf/{publication.group(0)}.pdf"
    return None


def _date_from_filename(filename: str) -> Optional[str]:
    match = re.search(r"(\d{1,2})-(\d{4})", filename)
    if match:
        return f"{match.group(2)}-{int(match.group(1)):02d}"
    match = re.search(r"(\d{4})", filename)
    return match.group(1) if match else None


def _clean_title(title: str) -> str:
    return title.replace("| Internal Revenue Service", "").strip()


def _clean_extracted_text(text: str) -> str:
    text = text.replace("\x00", "")
    text = _repair_spaced_pdf_tokens(text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n[ \t]+", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _repair_spaced_pdf_tokens(text: str) -> str:
    text = re.sub(
        r"\$\s*((?:\d\s*){2,})",
        lambda match: "$" + re.sub(r"\s+", "", match.group(1)),
        text,
    )
    text = re.sub(
        r"((?:\d\s*){2,})%",
        lambda match: re.sub(r"\s+", "", match.group(1)) + "%",
        text,
    )
    text = re.sub(r"(\d)\s+%", r"\1%", text)
    text = re.sub(r"%\s+A\s+M\s+I", "% AMI", text)
    replacements = {
        "E N E R G Y S T A R": "ENERGY STAR",
        "A M I": "AMI",
        "D I Y": "DIY",
        "H E A R": "HEAR",
    }
    for spaced, repaired in replacements.items():
        text = text.replace(spaced, repaired)
    return text


def _normalize_whitespace(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _looks_garbled(text: str) -> bool:
    if not text:
        return True
    words = re.findall(r"[A-Za-z]{3,}", text)
    if not words:
        return True
    common_hits = sum(1 for word in words if word.lower() in {"the", "and", "for", "with", "must", "energy"})
    return common_hits / max(len(words), 1) < 0.01 and len(text) > 500


def _stable_id(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug[:80]
