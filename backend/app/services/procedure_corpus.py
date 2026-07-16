# Phase 4 Step 1 procedure corpus builder
# Manifest decides inclusion; chunks are deterministic; sources are preserved, not inferred.
# No embedding, vector index, or retrieval happens in this service.
from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path

from pydantic import ValidationError

from app.core.errors import (
    ProcedureCorpusInvalidError,
    ProcedureManifestInvalidError,
    ProcedureManualNotFoundError,
    ProcedureManualParseError,
    ProcedureManualSecurityError,
)
from app.core.logging import log_run_event
from app.schemas.actions import ActionType
from app.schemas.retrieval import (
    CORPUS_SCHEMA_VERSION,
    CorpusManifest,
    CorpusManifestEntry,
    CorpusManifestExcludedEntry,
    ProcedureChunk,
    ProcedureCorpusSnapshot,
    ProcedureDocumentDescriptor,
    ProcedureMetadata,
)

logger = logging.getLogger("ares.procedure_corpus")

DEFAULT_SOFT_MAX_CHUNK_CHARS = 1800
NON_OPERATIONAL_H2 = "Procedure metadata"

METADATA_JSON_FENCE_RE = re.compile(
    r"##\s+Procedure metadata\s*\n+(?:(?!##\s).|\n)*?```json\s*\n(.*?)\n```",
    re.DOTALL | re.IGNORECASE,
)
ATX_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
FENCE_OPEN_RE = re.compile(r"^(`{3,}|~{3,})(.*)$")
ORDERED_LIST_RE = re.compile(r"^(\s*)\d+[.)]\s+")
UNORDERED_LIST_RE = re.compile(r"^(\s*)[-*+]\s+")
HR_RE = re.compile(r"^(\*{3,}|-{3,}|_{3,})\s*$")


@dataclass(frozen=True, slots=True)
class _MarkdownBlock:
    text: str
    kind: str


@dataclass(frozen=True, slots=True)
class _SectionNode:
    path: tuple[str, ...]
    title: str
    blocks: tuple[_MarkdownBlock, ...]


# lowercase SHA-256 of UTF-8 bytes
def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# compact canonical JSON for deterministic hashing
def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )


# normalize manual text for deterministic parsing and hashing
def normalize_manual_text(raw: str) -> str:
    text = raw.replace("\r\n", "\n").replace("\r", "\n")
    lines = [line.rstrip(" \t") for line in text.split("\n")]
    while lines and lines[-1] == "":
        lines.pop()
    return "\n".join(lines)


# build deterministic embedding_text for a chunk
def format_embedding_text(
    *,
    procedure_title: str,
    procedure_id: str,
    section_path: tuple[str, ...],
    allowed_actions: tuple[ActionType, ...],
    content: str,
) -> str:
    section = " > ".join(section_path)
    actions = ", ".join(action.value for action in allowed_actions)
    return (
        f"Procedure: {procedure_title}\n"
        f"Procedure ID: {procedure_id}\n"
        f"Section: {section}\n"
        f"Allowed actions: {actions}\n"
        f"\n"
        f"{content}"
    )


# compute chunk_id from stable identity fields
def compute_chunk_id(
    *,
    schema_version: str,
    procedure_id: str,
    manual_path: str,
    section_path: tuple[str, ...],
    chunk_index: int,
    content_sha256: str,
) -> str:
    identity = {
        "schema_version": schema_version,
        "procedure_id": procedure_id,
        "manual_path": manual_path,
        "section_path": list(section_path),
        "chunk_index": chunk_index,
        "content_sha256": content_sha256,
    }
    return _sha256_text(_canonical_json(identity))


class ProcedureCorpusBuilder:
    # Manifest is the inclusion authority; deferred manuals produce zero chunks.
    def __init__(
        self,
        *,
        manifest_path: Path,
        manuals_root: Path,
        repository_root: Path | None = None,
        soft_max_chunk_chars: int = DEFAULT_SOFT_MAX_CHUNK_CHARS,
    ) -> None:
        if soft_max_chunk_chars <= 0:
            raise ProcedureCorpusInvalidError(
                "soft_max_chunk_chars must be a positive integer",
            )
        resolved_manifest = manifest_path.resolve()
        resolved_manuals = manuals_root.resolve()
        if not resolved_manifest.is_file():
            raise ProcedureManifestInvalidError(
                "procedure corpus manifest is missing or not a regular file",
            )
        if not resolved_manuals.is_dir():
            raise ProcedureCorpusInvalidError(
                "procedure manuals root is missing or not a directory",
            )
        self._manifest_path = resolved_manifest
        self._manuals_root = resolved_manuals
        self._repository_root = (
            repository_root.resolve() if repository_root is not None else None
        )
        self._soft_max_chunk_chars = soft_max_chunk_chars

    # build a deterministic in-memory corpus snapshot
    def build(self) -> ProcedureCorpusSnapshot:
        log_run_event(
            logger,
            logging.INFO,
            "procedure corpus build started",
            event="procedure_corpus_build_started",
        )
        manifest = self._load_manifest()
        manifest_sha256 = _sha256_text(
            _canonical_json(manifest.model_dump(mode="json", by_alias=True)),
        )
        log_run_event(
            logger,
            logging.INFO,
            "procedure corpus manifest validated",
            event="procedure_corpus_manifest_validated",
        )

        included: list[ProcedureDocumentDescriptor] = []
        excluded: list[ProcedureDocumentDescriptor] = []
        chunks: list[ProcedureChunk] = []

        for entry in manifest.active_candidates:
            document, doc_chunks = self._process_manual(entry, index_eligible=True)
            included.append(document)
            chunks.extend(doc_chunks)
            log_run_event(
                logger,
                logging.INFO,
                "procedure document included",
                event="procedure_document_included",
                procedure_id=document.procedure_id,
                status=document.status.value,
                chunk_count=len(doc_chunks),
            )

        for entry in manifest.excluded:
            document, doc_chunks = self._process_manual(entry, index_eligible=False)
            if doc_chunks:
                raise ProcedureCorpusInvalidError(
                    "excluded procedure produced chunks",
                )
            excluded.append(document)
            log_run_event(
                logger,
                logging.INFO,
                "procedure document excluded by approved status",
                event="procedure_document_excluded",
                procedure_id=document.procedure_id,
                status=document.status.value,
                chunk_count=0,
            )

        corpus_sha256 = self._compute_corpus_sha256_values(
            schema_version=CORPUS_SCHEMA_VERSION,
            manifest_sha256=manifest_sha256,
            included=included,
            excluded=excluded,
            chunks=chunks,
        )
        snapshot = ProcedureCorpusSnapshot(
            schema_version=CORPUS_SCHEMA_VERSION,
            manifest_sha256=manifest_sha256,
            corpus_sha256=corpus_sha256,
            included_documents=tuple(included),
            excluded_documents=tuple(excluded),
            chunks=tuple(chunks),
        )
        log_run_event(
            logger,
            logging.INFO,
            "procedure corpus build complete",
            event="procedure_corpus_build_complete",
            included_count=len(included),
            excluded_count=len(excluded),
            chunk_count=len(chunks),
            corpus_sha256=corpus_sha256,
        )
        return snapshot

    def _load_manifest(self) -> CorpusManifest:
        try:
            raw_bytes = self._manifest_path.read_bytes()
        except OSError as exc:
            raise ProcedureManifestInvalidError(
                "procedure corpus manifest could not be read",
            ) from exc
        try:
            text = raw_bytes.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ProcedureManifestInvalidError(
                "procedure corpus manifest is not valid UTF-8",
            ) from exc
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ProcedureManifestInvalidError(
                "procedure corpus manifest is not valid JSON",
            ) from exc
        try:
            return CorpusManifest.model_validate(payload)
        except ValidationError as exc:
            raise ProcedureManifestInvalidError(
                "procedure corpus manifest failed contract validation",
            ) from exc

    def _process_manual(
        self,
        entry: CorpusManifestEntry | CorpusManifestExcludedEntry,
        *,
        index_eligible: bool,
    ) -> tuple[ProcedureDocumentDescriptor, list[ProcedureChunk]]:
        path = self._resolve_manual_path(entry.filename)
        try:
            raw_bytes = path.read_bytes()
        except OSError as exc:
            raise ProcedureManualNotFoundError(
                "procedure manual could not be read",
                filename=entry.filename,
            ) from exc
        try:
            raw_text = raw_bytes.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ProcedureManualParseError(
                "procedure manual is not valid UTF-8",
                filename=entry.filename,
            ) from exc
        if raw_text.startswith("\ufeff"):
            raise ProcedureManualParseError(
                "procedure manual must not include a UTF-8 BOM",
                filename=entry.filename,
            )

        normalized = normalize_manual_text(raw_text)
        manual_sha256 = _sha256_text(normalized)
        metadata = self._extract_metadata(normalized, entry.filename)
        if metadata.procedure_id != entry.procedure_id:
            raise ProcedureCorpusInvalidError(
                "manifest procedure_id does not match manual metadata",
            )
        if metadata.filename != entry.filename:
            raise ProcedureCorpusInvalidError(
                "manifest filename does not match manual metadata",
            )

        manual_path = self._relative_manual_path(entry.filename)
        document = ProcedureDocumentDescriptor(
            procedure_id=metadata.procedure_id,
            title=metadata.title,
            manual_path=manual_path,
            status=metadata.status,
            index_eligible=index_eligible,
            primary_actions=metadata.primary_actions,
            supporting_actions=metadata.supporting_actions,
            prohibited_actions=metadata.prohibited_actions,
            source_classifications=metadata.source_classifications,
            evidence_references=metadata.evidence_references,
            manual_sha256=manual_sha256,
        )
        if not index_eligible:
            return document, []

        sections = self._parse_sections(normalized, filename=entry.filename)
        chunks = self._chunk_document(
            document=document,
            metadata=metadata,
            sections=sections,
        )
        return document, chunks

    def _resolve_manual_path(self, filename: str) -> Path:
        if Path(filename).is_absolute() or "/" in filename or "\\" in filename:
            raise ProcedureManualSecurityError(
                "procedure manual path must be a basename",
                filename=filename,
            )
        if ".." in filename or filename in {".", ""}:
            raise ProcedureManualSecurityError(
                "procedure manual path failed security checks",
                filename=filename,
            )
        candidate = self._manuals_root / filename
        if candidate.is_symlink():
            resolved = candidate.resolve()
            if not resolved.is_relative_to(self._manuals_root):
                raise ProcedureManualSecurityError(
                    "procedure manual symlink escapes manuals root",
                    filename=filename,
                )
            if not resolved.is_file() or resolved.is_symlink():
                raise ProcedureManualSecurityError(
                    "procedure manual symlink target is invalid",
                    filename=filename,
                )
            return resolved
        resolved = candidate.resolve()
        if not resolved.is_relative_to(self._manuals_root):
            raise ProcedureManualSecurityError(
                "procedure manual path escapes manuals root",
                filename=filename,
            )
        if resolved.is_dir():
            raise ProcedureManualSecurityError(
                "procedure manual path points to a directory",
                filename=filename,
            )
        if not resolved.is_file():
            raise ProcedureManualNotFoundError(
                "procedure manual not found",
                filename=filename,
            )
        return resolved

    def _relative_manual_path(self, filename: str) -> str:
        if self._repository_root is not None:
            relative_root = self._manuals_root.relative_to(self._repository_root)
            return f"{relative_root.as_posix()}/{filename}"
        return f"docs/procedures/manuals/{filename}"

    def _extract_metadata(self, text: str, filename: str) -> ProcedureMetadata:
        matches = list(METADATA_JSON_FENCE_RE.finditer(text))
        if not matches:
            raise ProcedureManualParseError(
                "procedure metadata JSON fence is missing",
                filename=filename,
            )
        if len(matches) > 1:
            raise ProcedureManualParseError(
                "procedure metadata JSON fence is ambiguous",
                filename=filename,
            )
        raw = matches[0].group(1)
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ProcedureManualParseError(
                "procedure metadata JSON is malformed",
                filename=filename,
            ) from exc
        try:
            return ProcedureMetadata.model_validate(payload)
        except ValidationError as exc:
            raise ProcedureManualParseError(
                "procedure metadata failed contract validation",
                filename=filename,
            ) from exc

    def _parse_sections(
        self,
        text: str,
        *,
        filename: str,
    ) -> list[_SectionNode]:
        lines = text.split("\n")
        sections: list[_SectionNode] = []
        stack: list[tuple[int, str]] = []
        current_path: tuple[str, ...] = ()
        current_title = ""
        current_lines: list[str] = []
        saw_heading = False

        def flush() -> None:
            nonlocal current_lines
            blocks = _tokenize_blocks(current_lines)
            if not saw_heading:
                if blocks:
                    sections.append(
                        _SectionNode(
                            path=("Preamble",),
                            title="Preamble",
                            blocks=tuple(blocks),
                        )
                    )
                current_lines = []
                return
            if current_title == NON_OPERATIONAL_H2:
                current_lines = []
                return
            if blocks:
                sections.append(
                    _SectionNode(
                        path=current_path,
                        title=current_title,
                        blocks=tuple(blocks),
                    )
                )
            current_lines = []

        for line in lines:
            heading = ATX_HEADING_RE.match(line)
            if heading is None:
                current_lines.append(line)
                continue
            flush()
            saw_heading = True
            level = len(heading.group(1))
            title = heading.group(2).strip()
            if not title:
                raise ProcedureManualParseError(
                    "procedure manual contains an empty heading",
                    filename=filename,
                )
            while stack and stack[-1][0] >= level:
                stack.pop()
            stack.append((level, title))
            current_path = tuple(item[1] for item in stack)
            current_title = title
        flush()
        return sections

    def _chunk_document(
        self,
        *,
        document: ProcedureDocumentDescriptor,
        metadata: ProcedureMetadata,
        sections: list[_SectionNode],
    ) -> list[ProcedureChunk]:
        allowed = tuple(
            sorted(
                set(metadata.primary_actions) | set(metadata.supporting_actions),
                key=lambda action: action.value,
            )
        )
        chunks: list[ProcedureChunk] = []
        chunk_index = 0
        for section in sections:
            for content in self._split_section_content(section.blocks):
                content_sha256 = _sha256_text(content)
                embedding_text = format_embedding_text(
                    procedure_title=document.title,
                    procedure_id=document.procedure_id,
                    section_path=section.path,
                    allowed_actions=allowed,
                    content=content,
                )
                chunk_id = compute_chunk_id(
                    schema_version=CORPUS_SCHEMA_VERSION,
                    procedure_id=document.procedure_id,
                    manual_path=document.manual_path,
                    section_path=section.path,
                    chunk_index=chunk_index,
                    content_sha256=content_sha256,
                )
                chunks.append(
                    ProcedureChunk(
                        schema_version=CORPUS_SCHEMA_VERSION,
                        chunk_id=chunk_id,
                        procedure_id=document.procedure_id,
                        procedure_title=document.title,
                        manual_path=document.manual_path,
                        section_path=section.path,
                        section_title=section.title,
                        chunk_index=chunk_index,
                        content=content,
                        embedding_text=embedding_text,
                        content_sha256=content_sha256,
                        manual_sha256=document.manual_sha256,
                        source_classifications=document.source_classifications,
                        evidence_references=document.evidence_references,
                        allowed_actions=allowed,
                        procedure_status=document.status,
                    )
                )
                chunk_index += 1
        return chunks

    def _split_section_content(self, blocks: tuple[_MarkdownBlock, ...]) -> list[str]:
        if not blocks:
            return []
        joined = "\n\n".join(block.text for block in blocks)
        if len(joined) <= self._soft_max_chunk_chars:
            return [joined]

        groups: list[str] = []
        current: list[str] = []
        current_len = 0
        for block in blocks:
            piece = block.text
            piece_len = len(piece)
            if not current:
                current = [piece]
                current_len = piece_len
                continue
            candidate_len = current_len + 2 + piece_len
            if candidate_len <= self._soft_max_chunk_chars:
                current.append(piece)
                current_len = candidate_len
                continue
            groups.append("\n\n".join(current))
            current = [piece]
            current_len = piece_len
        if current:
            groups.append("\n\n".join(current))
        return groups

    def _compute_corpus_sha256_values(
        self,
        *,
        schema_version: str,
        manifest_sha256: str,
        included: list[ProcedureDocumentDescriptor],
        excluded: list[ProcedureDocumentDescriptor],
        chunks: list[ProcedureChunk],
    ) -> str:
        identity = {
            "schema_version": schema_version,
            "manifest_sha256": manifest_sha256,
            "included_documents": [
                doc.model_dump(mode="json") for doc in included
            ],
            "excluded_documents": [
                doc.model_dump(mode="json") for doc in excluded
            ],
            "chunks": [
                {
                    "chunk_id": chunk.chunk_id,
                    "procedure_id": chunk.procedure_id,
                    "manual_path": chunk.manual_path,
                    "section_path": list(chunk.section_path),
                    "chunk_index": chunk.chunk_index,
                    "content_sha256": chunk.content_sha256,
                    "manual_sha256": chunk.manual_sha256,
                    "source_classifications": [
                        item.value for item in chunk.source_classifications
                    ],
                    "evidence_references": [
                        ref.model_dump(mode="json") for ref in chunk.evidence_references
                    ],
                    "allowed_actions": [item.value for item in chunk.allowed_actions],
                    "procedure_status": chunk.procedure_status.value,
                }
                for chunk in chunks
            ],
        }
        return _sha256_text(_canonical_json(identity))


# tokenize Markdown lines into indivisible blocks
def _tokenize_blocks(lines: list[str]) -> list[_MarkdownBlock]:
    blocks: list[_MarkdownBlock] = []
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]
        if line.strip() == "":
            i += 1
            continue
        fence = FENCE_OPEN_RE.match(line)
        if fence is not None:
            marker = fence.group(1)[0]
            fence_len = len(fence.group(1))
            start = i
            i += 1
            while i < n:
                close = FENCE_OPEN_RE.match(lines[i])
                if (
                    close is not None
                    and close.group(1)[0] == marker
                    and len(close.group(1)) >= fence_len
                    and close.group(2).strip() == ""
                ):
                    i += 1
                    break
                i += 1
            blocks.append(
                _MarkdownBlock(
                    text="\n".join(lines[start:i]).rstrip("\n"),
                    kind="fence",
                )
            )
            continue
        if HR_RE.match(line) and not line.strip().startswith("|"):
            blocks.append(_MarkdownBlock(text=line, kind="hr"))
            i += 1
            continue
        if line.lstrip().startswith(">"):
            start = i
            i += 1
            while i < n and (
                lines[i].lstrip().startswith(">") or lines[i].strip() == ""
            ):
                if lines[i].strip() == "" and (
                    i + 1 >= n or not lines[i + 1].lstrip().startswith(">")
                ):
                    break
                i += 1
            blocks.append(
                _MarkdownBlock(
                    text="\n".join(lines[start:i]).rstrip("\n"),
                    kind="quote",
                )
            )
            continue
        if line.lstrip().startswith("|"):
            start = i
            i += 1
            while i < n and lines[i].lstrip().startswith("|"):
                i += 1
            blocks.append(
                _MarkdownBlock(
                    text="\n".join(lines[start:i]).rstrip("\n"),
                    kind="table",
                )
            )
            continue
        if ORDERED_LIST_RE.match(line) or UNORDERED_LIST_RE.match(line):
            start = i
            i += 1
            while i < n:
                nxt = lines[i]
                if nxt.strip() == "":
                    if i + 1 < n and (
                        ORDERED_LIST_RE.match(lines[i + 1])
                        or UNORDERED_LIST_RE.match(lines[i + 1])
                        or lines[i + 1].startswith(" ")
                        or lines[i + 1].startswith("\t")
                    ):
                        i += 1
                        continue
                    break
                if (
                    ORDERED_LIST_RE.match(nxt)
                    or UNORDERED_LIST_RE.match(nxt)
                    or nxt.startswith(" ")
                    or nxt.startswith("\t")
                ):
                    i += 1
                    continue
                break
            blocks.append(
                _MarkdownBlock(
                    text="\n".join(lines[start:i]).rstrip("\n"),
                    kind="list",
                )
            )
            continue
        start = i
        i += 1
        while i < n:
            nxt = lines[i]
            if nxt.strip() == "":
                break
            if (
                ATX_HEADING_RE.match(nxt)
                or FENCE_OPEN_RE.match(nxt)
                or nxt.lstrip().startswith("|")
                or nxt.lstrip().startswith(">")
                or ORDERED_LIST_RE.match(nxt)
                or UNORDERED_LIST_RE.match(nxt)
                or HR_RE.match(nxt)
            ):
                break
            i += 1
        blocks.append(
            _MarkdownBlock(
                text="\n".join(lines[start:i]).rstrip("\n"),
                kind="paragraph",
            )
        )
    return blocks
