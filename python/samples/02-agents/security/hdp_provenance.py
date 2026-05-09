# Copyright (c) Microsoft. All rights reserved.
# SPDX-License-Identifier: MIT
#
# This sample requires:
#   pip install "agent-framework-core" "hdp-agent-framework" python-dotenv
#
# Generate an Ed25519 signing key once:
#   python -c "
#   from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
#   import base64; k = Ed25519PrivateKey.generate()
#   print('HDP_SIGNING_KEY=' + base64.urlsafe_b64encode(k.private_bytes_raw()).decode())
#   "
#   export HDP_SIGNING_KEY=<value>
#
# Reference: https://helixar.ai/about/labs/hdp/
# Package:   https://pypi.org/project/hdp-agent-framework/

"""
HDP Delegation Provenance - agent-framework integration

Attaches a cryptographic audit trail to an agent-framework Agent.
Every chat call is recorded as a signed delegation hop verifiable
offline with a single public key.
"""

import asyncio
import base64
import os
import sys

from agent_framework import Agent
from agent_framework.foundry import FoundryChatClient
from azure.identity.aio import AzureCliCredential
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from dotenv import load_dotenv

# HDP middleware - pip install hdp-agent-framework
# Docs: https://helixar.ai/about/labs/hdp/
from hdp_agent_framework import HdpMiddleware, HdpPrincipal, ScopePolicy, verify_chain

load_dotenv()


def _load_signing_key() -> Ed25519PrivateKey:
    raw_b64 = os.getenv("HDP_SIGNING_KEY")
    if not raw_b64:
        print("ERROR: HDP_SIGNING_KEY not set. See comment at top of file.")
        sys.exit(1)
    return Ed25519PrivateKey.from_private_bytes(
        base64.urlsafe_b64decode(raw_b64 + "==")
    )


async def main() -> None:
    private_key = _load_signing_key()

    # 1. Declare what the human is authorising
    middleware = HdpMiddleware(
        signing_key=private_key.private_bytes_raw(),
        session_id="analysis-session-2026",
        principal=HdpPrincipal(id="analyst@example.com", id_type="email"),
        scope=ScopePolicy(
            intent="Analyse sales data and produce a written summary",
            authorized_tools=["fetch_data", "write_report"],
            max_hops=5,
        ),
    )

    # 2. Build agent as normal
    agent = Agent(
        client=FoundryChatClient(credential=AzureCliCredential()),
        name="sales_analyst",
        instructions="You are a sales analyst. Fetch data, then write a summary.",
    )

    # 3. Attach HDP - one line, zero agent changes
    middleware.configure(agent)

    # 4. Run
    result = await agent.run("Analyse Q1 EMEA sales and write a one-page summary.")
    print(result.text)

    # 5. Verify delegation chain offline
    token = middleware.export_token()
    verification = verify_chain(token, private_key.public_key())

    print(f"\nHDP chain valid: {verification.valid}")
    print(f"Hops recorded:   {verification.hop_count}")
    if verification.violations:
        print(f"Violations:      {verification.violations}")

    # Full spec: https://helixar.ai/about/labs/hdp/
    # arXiv paper: https://arxiv.org/abs/2604.04522


if __name__ == "__main__":
    asyncio.run(main())
