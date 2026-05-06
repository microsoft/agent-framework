# Inter-Agent Communication Protocol (IACP) Integration

IACP is a lightweight, open protocol (CC BY 4.0) for structured agent-to-agent communication with cryptographic identity. It complements Agent Framework's built-in [A2A protocol](https://github.com/microsoft/agent-framework/tree/main/python/packages/a2a) by adding identity verification and signed context transfer.

## Where IACP Fits

```
┌────────────────────────────────────────┐
│          Agent Framework Agent         │
│  ┌──────────┐  ┌──────────────────┐   │
│  │   A2A    │  │      IACP        │   │
│  │(discovery│  │(identity+trust)  │   │
│  │ +routing)│  │                  │   │
│  └──────────┘  └──────────────────┘   │
└────────────────────────────────────────┘
```

- **A2A** handles agent discovery, task routing, and message transport
- **IACP** adds cryptographic identity (Ed25519), capability manifests, and signed handoffs
- Together they form a complete enterprise agent communication stack

## Key Capabilities

### 1. Agent Identity (Ed25519)

Each agent gets a cryptographic keypair. The public key is the agent's permanent identifier. Before accepting work, agents verify each other's identity — no more trusting by name alone.

```python
from works_with_agents import IdentityProtocol

identity = IdentityProtocol.create_agent("my-agent")
# identity.public_key  → Ed25519 public key
# identity.fingerprint → stable hash for identification
```

### 2. Signed Handoff

When work transfers between agents, the sender signs a handoff token with context hash and timestamps. The receiver cryptographically verifies who sent the work and what context it carries.

### 3. Capability Manifest

Before delegating, an agent can request another agent's capability manifest — a signed document listing verified skills and tools. This enables trust-before-delegation.

## Comparison

| Concern | A2A | IACP |
|---------|-----|------|
| Agent discovery | Dynamic broadcast | Capability manifest |
| Identity | Agent card (string) | Ed25519 public key |
| Task transfer | A2A task send | Signed handoff token |
| Trust model | Implicit (same mesh) | Cryptographic (cross-org) |
| Audit trail | Event log | Immutable signed chain |
| Spec license | Apache 2.0 | CC BY 4.0 |

## Getting Started

The IACP specification and SDK are open source:

- **Spec:** https://workswithagents.com/specs/iacp.md
- **Identity Protocol:** https://workswithagents.com/specs/identity.md
- **Handoff Protocol:** https://workswithagents.com/specs/handoff.md
- **Python SDK:** `pip install works-with-agents`
- **Reference implementations:** 6 languages (Python, TypeScript, Go, C#, Rust, Shell)

## Further Reading

- [IACP Specification](https://workswithagents.com/specs/iacp.md)
- [Identity Protocol](https://workswithagents.com/specs/identity.md)
- [Handoff Protocol](https://workswithagents.com/specs/handoff.md) — Signed context transfer with verification
