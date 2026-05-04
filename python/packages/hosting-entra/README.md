# agent-framework-hosting-entra

Microsoft Entra (Azure AD) identity-linking sidecar channel for
[agent-framework-hosting](../hosting). Owns the OAuth 2.0 Authorization Code
flow that binds a per-channel id (e.g. a Telegram chat id) to the user's
Entra object id, so multiple non-Entra channels can share a single
`entra:<oid>` isolation key.

## Usage

```python
from pathlib import Path
from agent_framework_hosting import AgentFrameworkHost
from agent_framework_hosting_entra import (
    EntraIdentityLinkChannel,
    EntraIdentityStore,
)

store = EntraIdentityStore(Path("./identity_links.json"))

host = AgentFrameworkHost(
    target=my_agent,
    channels=[
        EntraIdentityLinkChannel(
            store=store,
            tenant_id="<tenant id>",
            client_id="<entra app id>",
            client_secret="<entra app secret>",
            public_base_url="https://your.host",
        ),
        # ... other channels whose run hooks call store.lookup(...)
    ],
)
host.serve()
```

For tenants that disallow client secrets, pass `certificate_path=` (and
optionally `certificate_password=`) instead of `client_secret`. The PEM
layout matches the one used by `agent-framework-hosting-teams`.
