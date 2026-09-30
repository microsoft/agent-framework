import json
import uuid
from ube_foundation import TrustEngine, PqcKeyPair

class NTISecurityWrapper:
    """
    NTI Security Wrapper for Microsoft Agent Framework.
    Verifies message exchanges and tool calls with post-quantum signatures.
    """
    def __init__(self, agent_id: str):
        self.agent_id = agent_id
        self.engine = TrustEngine()
        self.pqc_key = PqcKeyPair.generate()

    def grant_capability(self, capability: str):
        self.engine.grant(self.agent_id, capability)

    def verify_message(self, capability: str, message: dict) -> bool:
        req = {
            "id": f"req-{uuid.uuid4()}",
            "actor": self.agent_id,
            "capability": capability,
            "action": "message_exchange",
            "input": message,
            "signature": None,
            "pqc_signature": None,
            "public_key": None,
            "pqc_public_key": None,
            "token": None,
            "identity_claim": None
        }
        req_bytes = json.dumps(req, sort_keys=True).encode('utf-8')
        req["pqc_signature"] = self.pqc_key.sign(req_bytes)
        req["pqc_public_key"] = self.pqc_key.public_key_hex()
        
        decision = json.loads(self.engine.evaluate(json.dumps(req)))
        return decision.get("decision") == "Allow"
