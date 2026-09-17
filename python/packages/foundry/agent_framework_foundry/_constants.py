# Copyright (c) Microsoft. All rights reserved.

FOUNDRY_HOSTED_AGENT_SESSION_ID_KEY = "foundry_hosted_agent_session_id"
"""``AgentSession.state`` key holding the Foundry hosted-agent session ID.

This is the hosted agent's runtime session, a VM-isolated sandbox with a persistent filesystem, sent as
``extra_body["agent_session_id"]``. It is distinct from ``AgentSession.service_session_id``, which continues the
model-side response or conversation chain. The value is server-owned; see
``RawFoundryAgent.service_session_state_keys``.
"""
