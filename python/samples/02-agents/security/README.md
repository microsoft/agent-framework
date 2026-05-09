# Security samples

This folder contains runnable security samples. For FIDES architecture, security
model, middleware behavior, and API reference see
[FIDES_DEVELOPER_GUIDE.md](FIDES_DEVELOPER_GUIDE.md).

## What each sample demonstrates

| Sample | Focus | Demonstrates |
|--------|-------|--------------|
| `email_security_example.py` | Prompt injection defense | `SecureAgentConfig`, Foundry-backed email handling, `quarantined_llm`, and approval on policy violations |
| `repo_confidentiality_example.py` | Data exfiltration prevention | Confidentiality labels, Foundry-backed repository access, `max_allowed_confidentiality`, and approval before leaking private data |
| `hdp_provenance.py` | Delegation provenance | Cryptographic audit trail from authorising human to every agent action, verifiable offline with a single public key |

## Prerequisites

Run these samples from the `python/` directory with the repo development
environment available.

- Azure CLI authentication: `az login`
- `FOUNDRY_PROJECT_ENDPOINT` set in your environment
- `FOUNDRY_MODEL` set in your environment for the main agent deployment
- Local dev environment installed (for example, `uv sync --dev`)

Both samples use `FOUNDRY_MODEL` for the main agent and keep the quarantine
client pinned to `gpt-4o-mini`.

## Suppressing the experimental warning

The FIDES APIs in these samples are still experimental. Each sample includes a
short commented `warnings.filterwarnings(...)` snippet near the imports.
Uncomment it if you want to suppress the FIDES warning before using the
experimental APIs locally.

## Running the samples

### `email_security_example.py`

This sample simulates an inbox containing trusted and untrusted emails,
including prompt-injection attempts that try to force a privileged `send_email`
tool call.

Run it with:

```bash
uv run samples/02-agents/security/email_security_example.py --cli
uv run samples/02-agents/security/email_security_example.py --devui
```

What to look for:

- Untrusted email bodies are handled through the FIDES security flow
- `quarantined_llm` processes hidden content in isolation
- DevUI requests approval if the agent tries a blocked privileged action

### `repo_confidentiality_example.py`

This sample simulates a public issue that tries to trick the agent into reading
private repository secrets and posting them to a public channel.

Run it with:

```bash
uv run samples/02-agents/security/repo_confidentiality_example.py --cli
uv run samples/02-agents/security/repo_confidentiality_example.py --devui
```

What to look for:

- Reading public content keeps the context public
- Reading private content taints the context as private
- Posting private data to a public destination triggers an approval request

### `hdp_provenance.py`

This sample attaches HDP (Human Delegation Provenance) to an agent-framework `Agent`.
Every chat call is recorded as a signed Ed25519 hop; the full chain is verifiable
offline with a single public key.

Prerequisites:

```bash
pip install "agent-framework-foundry" "hdp-agent-framework" "azure-identity" python-dotenv
```

Generate a signing key once and export it:

```bash
python -c "
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
import base64; k = Ed25519PrivateKey.generate()
print('HDP_SIGNING_KEY=' + base64.urlsafe_b64encode(k.private_bytes_raw()).decode())
"
export HDP_SIGNING_KEY=<value>
```

Run it with:

```bash
uv run samples/02-agents/security/hdp_provenance.py
```

What to look for:

- `HDP chain valid: True` printed after the agent run
- `Hops recorded: N` showing how many agent turns were captured

References: [helixar.ai/about/labs/hdp/](https://helixar.ai/about/labs/hdp/) · [arXiv:2604.04522](https://arxiv.org/abs/2604.04522) · [PyPI](https://pypi.org/project/hdp-agent-framework/)

---

## Where to find the details

For the full FIDES design and API details, see
[FIDES_DEVELOPER_GUIDE.md](FIDES_DEVELOPER_GUIDE.md), which covers:

- integrity and confidentiality labels
- label propagation and auto-hiding behavior
- policy enforcement middleware
- security tools such as `quarantined_llm` and `inspect_variable`
- `SecureAgentConfig` and manual integration patterns
