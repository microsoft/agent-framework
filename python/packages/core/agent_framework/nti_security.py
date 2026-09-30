# Copyright (c) Microsoft. All rights reserved.

import json
import uuid
from typing import Any

from agent_framework._experimental import experimental
from ube_foundation import TrustEngine, PqcKeyPair

@experimental
class NTISecurityWrapper:
    """
    NTI Security Wrapper for Microsoft Agent Framework.
    Verifies message exchanges and tool calls with post-quantum signatures.
    """
    def __init__(self, agent_id: str) -> None:
        self.agent_id = agent_id
        self.engine = TrustEngine()
        self.pqc_key = PqcKeyPair.generate()

    def grant_capability(self, capability: str) -> None:
        self.engine.grant(self.agent_id, capability)

    def verify_message(
        self, 
        capability: str, 
        message: dict[str, Any], 
        sender_public_key: str, 
        sender_signature: str
    ) -> bool:
        """
        Verifies an incoming message from a remote agent using their public key and signature.
        """
        req = {
            "id": f"req-{uuid.uuid4()}",
            "actor": self.agent_id,
            "capability": capability,
            "action": "message_exchange",
            "input": message,
            "signature": None,
            "pqc_signature": sender_signature,
            "public_key": None,
            "pqc_public_key": sender_public_key,
            "token": None,
            "identity_claim": None
        }
        
        decision = json.loads(self.engine.evaluate(json.dumps(req)))
        return decision.get("decision") == "Allow"
