"""Deterministic output checks for known secrets, destinations and structured fields."""

import base64
import html
import re
from html.parser import HTMLParser
from urllib.parse import urlsplit

from kjnlae.detection.preprocessing import prepare_views
from kjnlae.guards.resources import HostAuthority, ResourceCatalog
from kjnlae.schemas import OutputInspection


class _VisibleText(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self.parts.append(data)


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

    def inspect(self, text: str, structured: dict[str, str] | None = None) -> OutputInspection:
        if len(text) + sum(len(v) for v in (structured or {}).values()) > 32768:
            raise ValueError("Output exceeds inspection limit")
        values = [text, *(structured or {}).values()]
        violations: list[str] = []
        for value in values:
            if not value:
                continue
            # Tags and comments disappear in rendered text, potentially joining
            # fragments of a known secret. HTMLParser never executes content.
            visible = _VisibleText()
            visible.feed(value)
            rendered = "".join(visible.parts)
            for candidate in (value, rendered):
                if not candidate:
                    continue
                prepared = prepare_views(candidate)
                if not prepared.complete:
                    violations.append("Output inspection budget exceeded")
                if any(
                    secret in view.text or base64.b64encode(secret.encode()).decode() in candidate
                    for view in prepared.views
                    for secret in self.secrets
                ):
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
        return OutputInspection(
            decision="BLOCK" if violations else "ALLOW", violations=list(dict.fromkeys(violations))
        )

    def release(
        self,
        text: str,
        structured: dict[str, str] | None,
        recipient: str | None,
        resources: list[str],
        authority: HostAuthority,
        catalog: ResourceCatalog,
        *,
        controls_ready: bool = True,
    ) -> OutputInspection:
        """Authorize release using host-owned recipient and resource provenance.

        Request text cannot supply trusted grants. Incomplete model controls
        block resource release even if lexical output checks find no violation.
        """
        inspected = self.inspect(text, structured)
        violations = list(inspected.violations)
        if not controls_ready and (recipient is not None or resources):
            violations.append("Required model control unavailable for resource release")
        if not authority.principal or not authority.tenant:
            violations.append("Verified output principal and tenant required")
        if recipient is not None and recipient not in authority.destinations:
            violations.append("Output recipient denied")
        for resource in resources:
            record = catalog.resolve(resource)
            if record is None or record.tenant != authority.tenant:
                violations.append("Output resource denied")
                continue
            read_granted = any(
                grant.permits(
                    _read_action(authority.tenant, resource), authority.principal, record.version
                )
                for grant in authority.grants
            )
            if not read_granted:
                violations.append("Output resource access denied")
            if recipient is not None and not any(
                grant.permits(
                    _send_action(authority.tenant, resource, recipient),
                    authority.principal,
                    record.version,
                )
                for grant in authority.grants
            ):
                violations.append("Output recipient lacks exact export grant")
        return OutputInspection(
            decision="BLOCK" if violations else "ALLOW", violations=list(dict.fromkeys(violations))
        )


def _read_action(tenant: str, resource: str):  # type: ignore[no-untyped-def]
    from kjnlae.guards.resources import ProposedAction

    return ProposedAction(tool="read_document", tenant=tenant, resource=resource)


def _send_action(tenant: str, resource: str, recipient: str):  # type: ignore[no-untyped-def]
    from kjnlae.guards.resources import ProposedAction

    return ProposedAction(
        tool="send_email", tenant=tenant, resource=resource, destination=recipient
    )
