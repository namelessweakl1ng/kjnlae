"""Bounded, source-mapped input views. This module never classifies attacks."""

import base64
import binascii
import html
import re
import unicodedata
from dataclasses import dataclass


@dataclass(frozen=True)
class InspectionView:
    """A safe text transformation plus character-to-original offset mapping."""

    name: str
    text: str
    mapping: tuple[tuple[int, int], ...]


@dataclass(frozen=True)
class PreparedInput:
    """All bounded views and whether every supported transformation was covered."""

    views: tuple[InspectionView, ...]
    diagnostics: tuple[str, ...]
    complete: bool


# These patterns find encodings for model inspection; they never classify attacks.
_ENTITY = re.compile(r"&(?:\#[xX][0-9a-fA-F]{1,8}|\#[0-9]{1,8}|[a-zA-Z]{1,32});")
_BASE64 = re.compile(r"(?<![A-Za-z0-9+/])[A-Za-z0-9+/]{24,32768}={0,2}(?![A-Za-z0-9+/=])")


def _normalized(text: str) -> InspectionView:
    chars: list[str] = []
    offsets: list[tuple[int, int]] = []
    for index, char in enumerate(text):
        if unicodedata.category(char) == "Cf":
            continue
        converted = unicodedata.normalize("NFKC", char)
        chars.append(converted)
        offsets.extend(((index, index + 1),) * len(converted))
    return InspectionView("normalized", "".join(chars), tuple(offsets))


def _html_entities(text: str) -> InspectionView | None:
    parts: list[str] = []
    offsets: list[tuple[int, int]] = []
    cursor = 0
    for match in _ENTITY.finditer(text):
        parts.append(text[cursor : match.start()])
        offsets.extend((i, i + 1) for i in range(cursor, match.start()))
        decoded = html.unescape(match.group())
        parts.append(decoded)
        offsets.extend(((match.start(), match.end()),) * len(decoded))
        cursor = match.end()
    if not offsets and cursor == 0:
        return None
    parts.append(text[cursor:])
    offsets.extend((i, i + 1) for i in range(cursor, len(text)))
    transformed = "".join(parts)
    if transformed == text:
        return None
    return InspectionView("html-entities", transformed, tuple(offsets))


def prepare_views(text: str) -> PreparedInput:
    """Build bounded original/normalized/decoded views without executing text."""
    if not 1 <= len(text) <= 32768:
        raise ValueError("Input must contain 1..32768 characters")
    views = [InspectionView("original", text, tuple((i, i + 1) for i in range(len(text))))]
    normalized = _normalized(text)
    if normalized.text != text:
        views.append(normalized)
    entity_view = _html_entities(text)
    if entity_view is not None:
        views.append(entity_view)
    diagnostics: list[str] = []
    decoded_chars = 0
    candidates = list(_BASE64.finditer(text))
    if len(candidates) > 16:
        diagnostics.append("ENCODED_CANDIDATE_LIMIT")
    for match in candidates[:16]:
        if len(match.group()) > 4096:
            diagnostics.append("ENCODED_ITEM_LIMIT")
            continue
        try:
            decoded = base64.b64decode(match.group(), validate=True).decode("utf-8")
        except (ValueError, binascii.Error, UnicodeDecodeError):
            continue
        if not decoded or sum(c.isprintable() or c.isspace() for c in decoded) / len(decoded) < 0.9:
            continue
        decoded_chars += len(decoded)
        if decoded_chars > 8192 or len(views) >= 8:
            diagnostics.append("DERIVED_VIEW_LIMIT")
            break
        views.append(
            InspectionView(
                "base64",
                decoded,
                tuple(((match.start(), match.end()),) * len(decoded)),
            )
        )
    return PreparedInput(tuple(views), tuple(diagnostics), not diagnostics)
