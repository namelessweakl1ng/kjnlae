# Security policy

kjnlae is a defense-in-depth development gateway, not a guarantee against all prompt injection. Supported security fixes target the latest release on `main`; no older-version support commitment is made yet.

## Reporting vulnerabilities

Use the repository's **Security → Advisories → Report a vulnerability** private reporting feature if enabled: https://github.com/namelessweakl1ng/kjnlae/security/advisories/new . If private reporting is unavailable, open a minimal issue requesting a private contact channel, without publishing a working exploit, credentials, private prompts or affected user data. There is no monitored security email promised by this project.

Include affected commit/version, environment, the violated trust boundary, minimal synthetic reproduction, expected/actual behavior and proposed mitigation if known. Never test against other users' accounts or infrastructure. Coordinate disclosure with maintainers; response timelines are best-effort and no SLA is claimed.

Detector false negatives are expected limitations; report bypasses with context and whether independent authorization or output protection was also bypassed. Authorization forgery, approval replay/substitution, exposed secrets, unsafe rendering, unsafe artifact loading and production authentication defects are especially relevant.

Run dependency audits and security tests before deployment. Do not disable TLS verification, install unreviewed model code, accept policies from model output or expose unauthenticated development endpoints. Reports and history are intentionally free of raw content, but callers must protect their own data and logs.
