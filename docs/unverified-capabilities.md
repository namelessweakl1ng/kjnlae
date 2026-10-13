# Unverified capabilities

The public repository does not include the 257 MiB trained weights; current cloud workspace artifact location and manifest hash appear in [model evaluation](reports/v0.2-model-evaluation.md). Another machine must copy that directory lawfully or run the documented training pipeline before complete scans work. Artifact persistence beyond this cloud session has not been guaranteed.

Full AgentDojo and BIPIA benchmark suites were **not run**. The included BIPIA importer handles a pinned training-prompt file only. A real LLM agent, real hospital/enterprise system, distributed approval service, multi-user identity gateway and GPU DeBERTa training were not validated. Docker image and a clean Fedora machine require their own target-host checks. See [limitations](limitations.md) and [verification](verification.md) for the exact current boundaries.
