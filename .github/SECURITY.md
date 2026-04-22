# Security Policy

## Reporting a Vulnerability

**Please do not open a public GitHub issue for security vulnerabilities.**

Use GitHub's private security advisory system instead:

1. Go to the [Security tab](https://github.com/nipreps/migas-server/security) of this repository.
2. Click **"Report a vulnerability"**.
3. Fill in the advisory form with as much detail as possible, including steps to reproduce and a proof-of-concept if available.

### Response Timeline

| Day | Milestone |
|-----|-----------|
| 0 | Report received |
| ≤ 2 | Acknowledgement sent |
| ≤ 14 | Severity assessment shared with reporter |
| ≤ 90 | Patch shipped and advisory published |

If a fix requires longer than 90 days, we will communicate that directly in the advisory thread.

---

## Scope

### In scope

- Authentication/authorization flaws (bearer token bypass, token hash comparison vulnerabilities)
- Injection vulnerabilities (SQL injection, command injection via user-supplied fields)
- Sensitive data exposure (telemetry PII, geolocation data leakage)
- Server-Side Request Forgery (SSRF) affecting the production server
- Dependency vulnerabilities **with a working proof-of-concept**
- The production deployment at `migas.nipreps.org`

### Out of scope

- Self-hosted deployments (security is the operator's responsibility)
- Rate-limit bypass on self-hosted instances
- DoS/DDoS attacks
- Social engineering of maintainers
- Theoretical vulnerabilities without a proof-of-concept
- Unconfirmed dependency CVEs (scanner output alone is not a valid report)
- The `allow_origins=['*']` CORS configuration — this is an accepted trade-off; telemetry clients are headless Python tools, not browsers

---

## Severity Classification

| Severity | Examples |
|----------|---------|
| **Critical** | Auth bypass, arbitrary code execution, full data exfiltration |
| **High** | SQL injection, token forgery, mass PII exposure |
| **Medium** | Partial data leak, privilege escalation within a project scope |
| **Low** | Information disclosure (e.g. stack traces in error responses), minor logic flaws |

---

## Safe Harbor

We support responsible security research. Researchers acting in good faith under this policy will not face legal action. Good faith means:

- Accessing only the data necessary to demonstrate the vulnerability
- Not disrupting the production service (`migas.nipreps.org`)
- Not disclosing the vulnerability publicly until a patch is shipped or the 90-day window has passed — whichever comes first
