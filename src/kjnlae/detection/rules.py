"""Independent bounded patterns; matches describe evidence, never successful attacks."""

import re
from dataclasses import dataclass

from kjnlae.detection.inspection import View
from kjnlae.schemas import Finding


@dataclass(frozen=True)
class Rule:
    id: str
    category: str
    pattern: str
    severity: int
    explanation: str


RULES = (
    Rule(
        "override",
        "instruction-override",
        r"\b(?:ignore|disregard|override|forget)\b.{0,50}\b(?:previous|prior|above|system|developer)\b.{0,40}\b(?:instructions?|prompts?|rules?)\b",
        80,
        "Attempts to supersede higher-priority instructions.",
    ),
    Rule(
        "role-spoof",
        "role-spoofing",
        r"<\|(?:system|developer|assistant|im_start)\|>|\[INST\]|(?:^|\n)\s*(?:SYSTEM|DEVELOPER)\s*:",
        75,
        "Forged authority or conversation delimiter.",
    ),
    Rule(
        "prompt-disclosure",
        "prompt-disclosure",
        r"\b(?:reveal|print|show|disclose|repeat)\b.{0,50}\b(?:system|hidden|developer)\b.{0,30}\b(?:prompt|instructions?)\b",
        80,
        "Requests hidden application instructions.",
    ),
    Rule(
        "secret-request",
        "secret-access",
        r"\b(?:send|reveal|extract|print|upload|read|steal)\b.{0,80}"
        r"\b(?:secret|password|api[ _-]?key|token|credentials?)\b",
        90,
        "Requests potentially sensitive resources.",
    ),
    Rule(
        "exfiltration",
        "exfiltration",
        r'\b(?:send|upload|exfiltrate|forward)\b.{0,120}(?:https?://[^\s<>"\x27]{1,256}|[\w.+-]{1,64}@[\w.-]{1,128})',
        85,
        "Instruction includes an external destination; authorization must constrain it.",
    ),
    Rule(
        "control-bypass",
        "control-bypass",
        r"\b(?:disable|bypass|ignore|skip)\b.{0,40}\b(?:security|safety|approval|authorization|permission)\b",
        85,
        "Attempts to avoid an independent security control.",
    ),
    Rule(
        "concealment",
        "concealment",
        r"\b(?:do not|don\x27t|never)\s+(?:tell|inform|notify)\s+(?:the\s+)?user\b|"
        r"\bhide\b.{0,30}\b(?:action|activity)\b",
        75,
        "Requests concealment from the legitimate user.",
    ),
    Rule(
        "tool-directive",
        "tool-manipulation",
        r"\b(?:call|execute|invoke|run)\b.{0,50}\b(?:admin|privileged|tool|shell|command|function)\b",
        75,
        "Embedded content directs execution; tool permission is separate.",
    ),
)
COMPILED = [(r, re.compile(r.pattern, re.I | re.S)) for r in RULES]


def detect(original: str, views: list[View]) -> list[Finding]:
    results: list[Finding] = []
    seen: set[tuple[str, int, int]] = set()
    for view in views:
        for rule, pattern in COMPILED:
            for m in pattern.finditer(view.text):
                start = view.mapping[m.start()][0]
                end = view.mapping[m.end() - 1][1]
                key = (rule.id, start, end)
                if key in seen:
                    continue
                seen.add(key)
                results.append(
                    Finding(
                        rule_id=rule.id,
                        category=rule.category,
                        explanation=rule.explanation,
                        severity=rule.severity,
                        start=start,
                        end=end,
                        evidence=original[start:end],
                        view=view.name,
                    )
                )
    return results
