"""Deterministic output checks for known secrets, destinations and structured fields."""

import html
import re
from urllib.parse import urlsplit

from kjnlae.schemas import OutputResult


class OutputGuard:
    def __init__(
        self,
        secrets: tuple[str, ...] = (),
        allowed_hosts: frozenset[str] = frozenset(),
        allowed_fields: frozenset[str] = frozenset({"summary"}),
    ) -> None:
        if any(not s for s in secrets):
            raise ValueError("Empty secret is invalid")
        self.secrets = secrets
        self.allowed_hosts = allowed_hosts
        self.allowed_fields = allowed_fields

    def inspect(self, text: str, structured: dict[str, str] | None = None) -> OutputResult:
        if len(text) > 32768 or (structured and sum(len(v) for v in structured.values()) > 32768):
            raise ValueError("Output exceeds inspection limit")
        values = [text, *(structured or {}).values()]
        violations: list[str] = []
        if any(secret in value for value in values for secret in self.secrets):
            violations.append("Known sensitive value would be disclosed")
        for value in values:
            decoded = html.unescape(value)
            links = re.findall(r'(?:https?://|javascript:|data:|//)[^\s<>"\x27)]+', decoded, re.I)
            links.extend(
                re.findall(r'(?:href|src)\s*=\s*["\x27]([^"\x27]{1,1024})["\x27]', decoded, re.I)
            )
            links.extend(re.findall(r"\]\(([^)\s]{1,1024})\)", decoded))
            for link in links:
                try:
                    url = urlsplit(link)
                    valid = (
                        url.scheme in {"http", "https"}
                        and url.hostname in self.allowed_hosts
                        and not url.username
                        and url.port in {None, 80, 443}
                    )
                    # Relative links stay on the rendering application's own origin.
                    valid = valid or (
                        not url.scheme
                        and not url.netloc
                        and link.startswith("/")
                        and not link.startswith("//")
                        and "\\" not in link
                    )
                except ValueError:
                    valid = False
                if not valid:
                    violations.append("Generated destination is outside the output allowlist")
        if structured is not None and set(structured) - self.allowed_fields:
            violations.append("Unexpected structured output fields")
        return OutputResult(
            decision="BLOCK" if violations else "ALLOW", violations=list(dict.fromkeys(violations))
        )
