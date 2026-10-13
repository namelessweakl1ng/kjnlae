"""Synthetic HTTP host chatbot: KJNLAE_CHAT_API_KEY=... uvicorn examples.chatbot_http:app.

Set KJNLAE_CHAT_KIND=hospital or enterprise. No live records or external tools.
"""

import os
import time

from kjnlae import Guard
from kjnlae.api.chatbot import create_chatbot_app
from kjnlae.guards.resources import HostAuthority, ResourceCatalog, ResourceGrant, ResourceRecord


def build_app():  # type: ignore[no-untyped-def]
    key = os.getenv("KJNLAE_CHAT_API_KEY", "")
    if len(key) < 32:
        raise ValueError("Set a 32+ character KJNLAE_CHAT_API_KEY")
    if not os.getenv("KJNLAE_MODEL_DIR") or not os.getenv("KJNLAE_MODEL_HASH"):
        raise ValueError("Configure the verified local fine-tuned model")
    kind = os.getenv("KJNLAE_CHAT_KIND", "hospital")
    if kind not in {"hospital", "enterprise"}:
        raise ValueError("KJNLAE_CHAT_KIND must be hospital or enterprise")
    if kind == "hospital":
        resource = "patient-1024"
        text = "Fictional patient 1024 has a routine follow-up appointment."
        tenant = "demo-hospital"
    else:
        resource = "policy-1024"
        text = "Fictional employee policy grants ten days of annual leave."
        tenant = "demo-enterprise"
    authority = HostAuthority(
        "demo-user",
        tenant,
        "Summarize one assigned fictional document",
        frozenset({"read_document"}),
        (ResourceGrant("demo-user", tenant, resource, "read_document", 1, time.time() + 86400),),
    )
    return create_chatbot_app(
        Guard(),
        {key: authority},
        ResourceCatalog((ResourceRecord(resource, tenant, "demo-owner", 1),)),
        {resource: text},
    )


app = build_app()
