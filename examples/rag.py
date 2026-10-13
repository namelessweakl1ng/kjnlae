"""Run a local, synthetic RAG boundary with the configured fine-tuned model."""

import argparse
import json
from time import time

from kjnlae import Guard
from kjnlae.context import TrustedSecurityContext
from kjnlae.guards.resources import ResourceCatalog, ResourceGrant, ResourceRecord
from kjnlae.integrations.rag import RagChunk, RagGateway


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("query", nargs="?", default="benefits")
    args = parser.parse_args()
    guard = Guard()
    chunks = (
        RagChunk("public-1", "handbook", "demo", "Benefits", "Employees receive leave."),
        RagChunk("private-1", "hr", "demo", "Benefits", "Private salary data."),
    )
    catalog = ResourceCatalog(
        (
            ResourceRecord("handbook", "demo", "company", 1, sensitive=False),
            ResourceRecord("hr", "demo", "hr", 1),
        )
    )
    grants = (ResourceGrant("demo-user", "demo", "handbook", "read_document", 1, time() + 60),)
    result = RagGateway(chunks, guard, catalog).retrieve(
        args.query, TrustedSecurityContext("demo-user", "demo", "summarize"), grants
    )
    print(
        json.dumps(
            {
                "citations": result.citations,
                "withheld": result.withheld,
                "answer": " ".join(c.text for c in result.chunks),
            },
            indent=2,
        )
    )
    guard.close()


if __name__ == "__main__":
    main()
