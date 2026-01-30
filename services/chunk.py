import json
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class Chunk:
    chunk_id: str
    article_id: Optional[str]
    title: str
    url: str
    heading_path: str
    is_toc: bool
    text: str  # final chunk text (already prepended with header)


_FRONT_MATTER_RE = re.compile(r"^---\s*$")
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*\S)\s*$")
_CODE_FENCE_RE = re.compile(r"^\s*```")
_TOC_LINE_RE = re.compile(r"^\s*[-*]\s+\[.+?\]\(#.+?\)\s*$")  # - [X](#Anchor)


def _parse_front_matter(md: str) -> Tuple[Dict[str, Any], str]:
    """
    Very small YAML-like front-matter parser for simple `key: value` lines.
    Returns (meta, body_without_front_matter).
    """
    lines = md.splitlines()
    if not lines or not _FRONT_MATTER_RE.match(lines[0]):
        return {}, md

    meta: Dict[str, Any] = {}
    i = 1
    while i < len(lines) and not _FRONT_MATTER_RE.match(lines[i]):
        line = lines[i].strip()
        if line and ":" in line:
            k, v = line.split(":", 1)
            k = k.strip()
            v = v.strip()
            # try parse JSON-ish lists like [a, b] or quoted strings in your files
            if v.startswith("[") and v.endswith("]"):
                try:
                    meta[k] = json.loads(v.replace("'", '"'))
                except Exception:
                    meta[k] = v
            else:
                # remove surrounding quotes if any
                if (v.startswith('"') and v.endswith('"')) or (v.startswith("'") and v.endswith("'")):
                    v = v[1:-1]
                meta[k] = v
        i += 1

    # skip closing ---
    if i < len(lines) and _FRONT_MATTER_RE.match(lines[i]):
        i += 1

    body = "\n".join(lines[i:]).lstrip("\n")
    return meta, body


def _extract_title_url(md_body: str, meta: Dict[str, Any]) -> Tuple[str, str]:
    title = str(meta.get("title") or "").strip()
    url = str(meta.get("url") or "").strip()

    # fallback title: first H1
    if not title:
        for line in md_body.splitlines():
            m = _HEADING_RE.match(line)
            if m and len(m.group(1)) == 1:
                title = m.group(2).strip()
                break

    # fallback url: first "Article URL:" line
    if not url:
        for line in md_body.splitlines():
            if line.lower().startswith("article url:"):
                url = line.split(":", 1)[1].strip()
                break

    return title or "Untitled", url or ""


def _detect_split_level(md_body: str) -> int:
    """
    Prefer splitting at H2 (##) if exists (outside code fences), otherwise H3 (###).
    """
    in_code = False
    has_h2 = False
    has_h3 = False

    for line in md_body.splitlines():
        if _CODE_FENCE_RE.match(line):
            in_code = not in_code
            continue
        if in_code:
            continue
        m = _HEADING_RE.match(line)
        if not m:
            continue
        level = len(m.group(1))
        if level == 2:
            has_h2 = True
        elif level == 3:
            has_h3 = True

    if has_h2:
        return 2
    if has_h3:
        return 3
    return 0  # fallback: size-based only


def _is_table_line(line: str) -> bool:
    # markdown tables typically start with |, and separator lines like | --- |
    s = line.lstrip()
    return s.startswith("|")


def _build_chunk_header(title: str, url: str, heading_path: str, meta: Dict[str, Any]) -> str:
    # Keep it short but useful for citations/debug
    updated = str(meta.get("updated_at") or "").strip()
    header_lines = [
        f"Title: {title}",
        f"Article URL: {url}" if url else "Article URL:",
        f"Section: {heading_path}" if heading_path else "Section:",
    ]
    if updated:
        header_lines.append(f"Updated At: {updated}")
    return "\n".join(header_lines) + "\n\n"


def chunk_markdown(
    md_text: str,
    *,
    target_chars: int = 2200,
    max_chars: int = 4200,
    overlap_chars: int = 200,
    include_toc_chunk: bool = True,
) -> List[Chunk]:
    """
    Chunk markdown with rules:
    - Split at H2 (##) if present, else at H3 (###) if present.
    - Never split inside fenced code blocks or markdown tables.
    - Optionally separate a TOC anchor list near top into its own (small) chunk.
    - If a section is too long, split further by paragraph boundaries with small overlap (prose only).
    """
    meta, body = _parse_front_matter(md_text)
    title, url = _extract_title_url(body, meta)
    article_id = str(meta.get("id") or "").strip() or None

    split_level = _detect_split_level(body)

    lines = body.splitlines()
    chunks: List[Chunk] = []

    in_code = False
    in_table = False

    # Track heading context
    current_h1 = ""
    current_split_heading = ""  # heading text at split_level
    current_heading_path = ""

    # Optional TOC extraction (only near top, outside code)
    toc_lines: List[str] = []
    toc_consumed_until = -1
    if include_toc_chunk:
        tmp_in_code = False
        for i, line in enumerate(lines[:200]):  # only scan early part
            if _CODE_FENCE_RE.match(line):
                tmp_in_code = not tmp_in_code
                continue
            if tmp_in_code:
                continue
            if _TOC_LINE_RE.match(line):
                toc_lines.append(line)
                toc_consumed_until = i
            elif toc_lines:
                # stop at first non-toc line after starting
                break

    def flush_section(section_lines: List[str], heading_path: str, is_toc: bool, section_index: int) -> None:
        nonlocal chunks
        if not section_lines:
            return

        # Remove trailing blank lines
        while section_lines and section_lines[-1].strip() == "":
            section_lines.pop()

        raw = "\n".join(section_lines).strip()
        if not raw:
            return

        # If too big, split further (paragraph-aware) but never inside code/table
        if len(raw) <= max_chars:
            header = _build_chunk_header(title, url, heading_path, meta)
            chunk_id = f"{article_id or 'article'}:{section_index:04d}:0"
            chunks.append(
                Chunk(
                    chunk_id=chunk_id,
                    article_id=article_id,
                    title=title,
                    url=url,
                    heading_path=heading_path,
                    is_toc=is_toc,
                    text=header + raw + "\n",
                )
            )
            return

        # Further splitting for long sections
        # We'll re-walk section_lines to find safe paragraph boundaries outside code/table.
        parts: List[List[str]] = []
        buf: List[str] = []
        buf_len = 0

        local_in_code = False
        local_in_table = False

        # Keep last safe split index inside buf
        last_safe_split_at: Optional[int] = None

        def mark_safe_split():
            nonlocal last_safe_split_at
            # safe split at current end of buf
            last_safe_split_at = len(buf)

        for ln in section_lines:
            if _CODE_FENCE_RE.match(ln):
                local_in_code = not local_in_code
            # table state: table if current line starts with '|'
            if not local_in_code:
                if _is_table_line(ln):
                    local_in_table = True
                elif local_in_table and ln.strip() == "":
                    local_in_table = False

            buf.append(ln)
            buf_len += len(ln) + 1

            # Safe boundary: blank line outside code/table
            if (not local_in_code) and (not local_in_table) and ln.strip() == "":
                mark_safe_split()

            # Need to split?
            if buf_len >= max_chars and (not local_in_code) and (not local_in_table):
                split_at = last_safe_split_at or len(buf)
                part = buf[:split_at]
                parts.append(part)

                # overlap (prose only): take last overlap_chars chars from part as prefix for next
                overlap_text = "\n".join(part).rstrip()
                overlap_prefix = ""
                if overlap_chars > 0 and overlap_text:
                    overlap_prefix = overlap_text[-overlap_chars:]
                    # make overlap start at line boundary for cleanliness
                    j = overlap_prefix.find("\n")
                    if j != -1:
                        overlap_prefix = overlap_prefix[j + 1 :]

                # reset buf
                remainder = buf[split_at:]
                buf = []
                buf_len = 0
                last_safe_split_at = None

                # re-seed with overlap + remainder
                if overlap_prefix:
                    buf.append(overlap_prefix)
                    buf_len += len(overlap_prefix) + 1
                buf.extend(remainder)
                buf_len += sum(len(x) + 1 for x in remainder)

        if buf:
            parts.append(buf)

        # Emit parts
        for pi, part_lines in enumerate(parts):
            part_raw = "\n".join(part_lines).strip()
            if not part_raw:
                continue
            header = _build_chunk_header(title, url, heading_path, meta)
            chunk_id = f"{article_id or 'article'}:{section_index:04d}:{pi}"
            chunks.append(
                Chunk(
                    chunk_id=chunk_id,
                    article_id=article_id,
                    title=title,
                    url=url,
                    heading_path=heading_path,
                    is_toc=is_toc,
                    text=header + part_raw + "\n",
                )
            )

    # Build sections
    section_lines: List[str] = []
    section_index = 0

    # Consume TOC into its own chunk (optional)
    start_idx = 0
    if include_toc_chunk and toc_lines:
        # We keep TOC as a chunk (you can choose not to embed it later by checking is_toc)
        flush_section(toc_lines, heading_path="TOC", is_toc=True, section_index=section_index)
        section_index += 1
        start_idx = toc_consumed_until + 1

    for i in range(start_idx, len(lines)):
        line = lines[i]

        # Track code/table state (global)
        if _CODE_FENCE_RE.match(line):
            in_code = not in_code

        if not in_code:
            if _is_table_line(line):
                in_table = True
            elif in_table and line.strip() == "":
                in_table = False

        # Capture heading context
        if (not in_code) and (not in_table):
            hm = _HEADING_RE.match(line)
            if hm:
                level = len(hm.group(1))
                heading_text = hm.group(2).strip()

                if level == 1:
                    current_h1 = heading_text

                # Boundary at split_level heading
                # Boundary at split_level heading (primary), plus optional H4 (secondary) when split_level==3
                is_primary = (split_level and level == split_level)

                # secondary boundary: if we split at H3, allow H4 to start a new chunk when current section is already large
                is_secondary_h4 = (
                    split_level == 3 and level == 4 and
                    (sum(len(x) + 1 for x in section_lines) >= int(target_chars * 0.9))
                )

                if (not in_code) and (not in_table) and (is_primary or is_secondary_h4):
                    if section_lines:
                        flush_section(section_lines, current_heading_path or "Intro", is_toc=False, section_index=section_index)
                        section_index += 1
                        section_lines = []

                    # Update heading path
                    if level == 3:
                        current_split_heading = heading_text
                        parent = current_h1 or title
                        current_heading_path = f"{parent} > {current_split_heading}"
                    elif level == 4:
                        # keep the current H3 as parent (if present), append H4
                        parent = current_heading_path or (current_h1 or title)
                        current_heading_path = f"{parent} > {heading_text}"


        section_lines.append(line)

    # flush last
    if section_lines:
        heading_path = current_heading_path or "Intro"
        flush_section(section_lines, heading_path, is_toc=False, section_index=section_index)

    return chunks
