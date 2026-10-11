"""Bounded derived views with offsets into the unchanged original input."""

import base64
import binascii
import html
import re
import unicodedata
from dataclasses import dataclass

from kjnlae.schemas import Finding


@dataclass(frozen=True)
class View:
    text: str
    mapping: list[tuple[int, int]]
    name: str


def normalize(text: str, name: str = "normalized") -> View:
    chars: list[str] = []
    mapping: list[tuple[int, int]] = []
    for i, c in enumerate(text):
        # Removing invisible format controls allows inspection without modifying source.
        if unicodedata.category(c) == "Cf":
            continue
        normalized = unicodedata.normalize("NFKC", c)
        chars.extend(normalized)
        mapping.extend([(i, i + 1)] * len(normalized))
    return View("".join(chars), mapping, name)


def inspect(text: str) -> tuple[list[View], list[Finding], bool]:
    if not text or len(text) > 32768:
        raise ValueError("Input must contain 1..32768 characters")
    views = [normalize(text)]
    findings: list[Finding] = []
    for m in re.finditer(
        r"[\x00-\x08\x0b\x0c\x0e-\x1f\u200b-\u200f\u202a-\u202e\u2060-\u2069]", text
    ):
        findings.append(
            Finding(
                rule_id="unicode-control",
                category="obfuscation",
                explanation="Control character can obscure instructions.",
                severity=30,
                start=m.start(),
                end=m.end(),
                evidence=m.group(),
            )
        )
    for m in re.finditer(
        r"<!--[\s\S]*?-->|<[^>]{0,1024}(?:hidden|display\s*:\s*none|aria-hidden)[^>]{0,1024}>",
        text,
        re.I,
    ):
        findings.append(
            Finding(
                rule_id="hidden-html",
                category="hidden-content",
                explanation="Hidden HTML remains untrusted data.",
                severity=25,
                start=m.start(),
                end=m.end(),
                evidence=m.group(),
            )
        )
    # Decode HTML entities with a source span for each resulting character.
    parts: list[str] = []
    maps: list[tuple[int, int]] = []
    cursor = 0
    for m in re.finditer(r"&(?:#[xX][0-9a-fA-F]{1,8}|#[0-9]{1,8}|[a-zA-Z]{1,32});", text):
        parts.append(text[cursor : m.start()])
        maps.extend((i, i + 1) for i in range(cursor, m.start()))
        decoded = html.unescape(m.group())
        parts.append(decoded)
        maps.extend([(m.start(), m.end())] * len(decoded))
        cursor = m.end()
    parts.append(text[cursor:])
    maps.extend((i, i + 1) for i in range(cursor, len(text)))
    if "".join(parts) != text:
        views.append(View("".join(parts), maps, "html-entities"))
    complete = True
    candidates = list(
        re.finditer(r"(?<![A-Za-z0-9+/])[A-Za-z0-9+/]{24,32768}={0,2}(?![A-Za-z0-9+/=])", text)
    )
    if len(candidates) > 16:
        complete = False
    for m in candidates[:16]:
        if len(m.group()) > 4096:
            complete = False
            continue
        try:
            decoded = base64.b64decode(m.group(), validate=True).decode("utf-8")
        except (ValueError, binascii.Error, UnicodeDecodeError):
            continue
        if not decoded or sum(c.isprintable() or c.isspace() for c in decoded) / len(decoded) < 0.9:
            continue
        n = normalize(decoded)
        views.append(View(n.text, [(m.start(), m.end())] * len(n.text), "base64"))
    return views, findings, complete
