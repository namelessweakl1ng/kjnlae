# RAG integration

Use `RagGateway` with a host-created `TrustedSecurityContext`, `ResourceCatalog` and exact `ResourceGrant` objects. It checks tenant and current read grant **before** scanning a retrieved chunk. It scans each authorized chunk with the configured fine-tuned model, withholds blocked or incomplete content, and returns catalog-owned citation IDs. It rejects more than 256 chunks instead of silently leaving the tail unscanned. The local lexical title match is retrieval logic, never an injection detector.

```bash
python examples/rag.py benefits
kjnlae demo --scenario rag
```

The example uses synthetic handbook and HR chunks. The HR chunk is not passed to the scanner or answer for a principal without its grant. A document's prose cannot assert that it is a system message or grant access. Real RAG systems must enforce ACLs in the authoritative store as well, version citations, avoid cross-tenant cache entries and recheck access at output release. `POST /v2/rag/inspect` supplies only bounded inspection; it does **not** perform retrieval authorization for arbitrary API-supplied chunks.
