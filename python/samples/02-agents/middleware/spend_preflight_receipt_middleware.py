# Copyright (c) Microsoft. All rights reserved.

import asyncio
import hashlib
import json
import math
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Annotated, Any

from agent_framework import (
    Agent,
    FunctionInvocationContext,
    FunctionMiddleware,
    MiddlewareTermination,
    tool,
)
from agent_framework.foundry import FoundryChatClient
from azure.identity.aio import AzureCliCredential
from dotenv import load_dotenv
from pydantic import BaseModel, Field

# Load environment variables from .env file
load_dotenv()

"""
Spend preflight and receipt middleware sample.

This sample demonstrates how to use FunctionMiddleware as the final execution-boundary
authority for a paid or otherwise irreversible tool. The middleware:

1. Builds a canonical spend envelope from the validated tool arguments before `call_next()`.
2. Binds a local authorization decision to that exact envelope hash.
3. Persists a non-reusable execution claim before calling the tool so the same authorization
   cannot be spent twice by retries or concurrent middleware invocations.
4. Returns a typed not-executed result for denied or approval-required decisions without
   entering the tool body.
5. Records a post-execution receipt that distinguishes succeeded, failed, and not-executed
   outcomes.

The tool uses `approval_mode="never_require"` intentionally. In this sample, the middleware is
the sole authority surface. Production systems can replace `authorize_spend` with their policy
service, approval queue, payment preflight, or receipt store.
"""

POLICY_VERSION = "paid-tool-preflight-v1"


@dataclass(frozen=True)
class SpendEnvelope:
    """Canonical authorization object for one paid tool invocation."""

    function_name: str
    call_id: str
    args_hash: str
    amount_usd: str
    payee: str
    resource: str
    policy_version: str
    expires_at: str

    def to_dict(self) -> dict[str, str]:
        """Return a JSON-serializable representation."""
        return {
            "function_name": self.function_name,
            "call_id": self.call_id,
            "args_hash": self.args_hash,
            "amount_usd": self.amount_usd,
            "payee": self.payee,
            "resource": self.resource,
            "policy_version": self.policy_version,
            "expires_at": self.expires_at,
        }

    def authorization_dict(self) -> dict[str, str]:
        """Return the stable fields that an authorization decision binds to."""
        return {
            "function_name": self.function_name,
            "call_id": self.call_id,
            "args_hash": self.args_hash,
            "amount_usd": self.amount_usd,
            "payee": self.payee,
            "resource": self.resource,
            "policy_version": self.policy_version,
        }


def canonical_json(value: Mapping[str, Any]) -> str:
    """Serialize a mapping deterministically for hashing."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def sha256(value: str) -> str:
    """Return a hex SHA-256 digest."""
    return hashlib.sha256(value.encode()).hexdigest()


def arguments_to_dict(arguments: BaseModel | Mapping[str, Any]) -> dict[str, Any]:
    """Convert validated function arguments into a plain dict."""
    return arguments.model_dump() if isinstance(arguments, BaseModel) else dict(arguments)


def build_spend_envelope(context: FunctionInvocationContext) -> tuple[SpendEnvelope, str]:
    """Build the envelope and return it with its stable hash."""
    arguments = arguments_to_dict(context.arguments)
    args_hash = sha256(canonical_json(arguments))
    call_id = context.metadata.get("call_id")
    issued_at = datetime.now(timezone.utc)
    envelope = SpendEnvelope(
        function_name=context.function.name,
        call_id=call_id if isinstance(call_id, str) and call_id else f"direct:{args_hash[:12]}",
        args_hash=args_hash,
        amount_usd=str(arguments.get("amount_usd", "0")),
        payee=str(arguments.get("payee", "unknown")),
        resource=str(arguments.get("dataset_name", "unknown")),
        policy_version=POLICY_VERSION,
        expires_at=(issued_at + timedelta(minutes=5)).isoformat(),
    )
    return envelope, sha256(canonical_json(envelope.authorization_dict()))


def authorize_spend(envelope: SpendEnvelope, envelope_hash: str) -> dict[str, str]:
    """Return a local authorization decision for the sample.

    This placeholder keeps the sample deterministic:
    - amounts over 100 USD are denied;
    - amounts over 50 USD require human approval;
    - smaller spends are approved.
    """
    try:
        amount = float(envelope.amount_usd)
    except ValueError:
        amount = math.nan

    if not math.isfinite(amount) or amount < 0:
        verdict = "denied"
        reason = "amount must be finite and non-negative"
    elif amount > 100:
        verdict = "denied"
        reason = "amount exceeds the sample hard limit"
    elif amount > 50:
        verdict = "requires_approval"
        reason = "amount exceeds the sample auto-approval threshold"
    else:
        verdict = "approved"
        reason = "amount is inside the sample auto-approval threshold"

    return {
        "authorization_ref": f"auth:{envelope_hash[:16]}",
        "verdict": verdict,
        "reason": reason,
        "envelope_hash": envelope_hash,
        "policy_version": envelope.policy_version,
    }


class SpendPreflightReceiptMiddleware(FunctionMiddleware):
    """Authorizes paid tool calls before execution and records receipts afterwards."""

    def __init__(self) -> None:
        self._execution_claims: set[str] = set()
        self.receipts: list[dict[str, Any]] = []

    def _not_executed_result(
        self,
        *,
        envelope: SpendEnvelope,
        envelope_hash: str,
        authorization: dict[str, str],
    ) -> dict[str, Any]:
        return {
            "status": "not_executed",
            "verdict": authorization["verdict"],
            "reason": authorization["reason"],
            "authorization_ref": authorization["authorization_ref"],
            "envelope_hash": envelope_hash,
            "envelope": envelope.to_dict(),
        }

    def _record_receipt(
        self,
        *,
        envelope: SpendEnvelope,
        envelope_hash: str,
        authorization: dict[str, str],
        status: str,
        summary: str,
    ) -> None:
        self.receipts.append({
            "receipt_id": f"receipt:{len(self.receipts) + 1}",
            "status": status,
            "summary": summary,
            "authorization_ref": authorization["authorization_ref"],
            "envelope_hash": envelope_hash,
            "envelope": envelope.to_dict(),
            "recorded_at": datetime.now(timezone.utc).isoformat(),
        })

    async def process(
        self,
        context: FunctionInvocationContext,
        call_next: Callable[[], Awaitable[None]],
    ) -> None:
        if context.function.name != "buy_dataset_access":
            await call_next()
            return

        envelope, envelope_hash = build_spend_envelope(context)
        authorization = authorize_spend(envelope, envelope_hash)

        if authorization["verdict"] != "approved":
            result = self._not_executed_result(
                envelope=envelope,
                envelope_hash=envelope_hash,
                authorization=authorization,
            )
            context.result = result
            self._record_receipt(
                envelope=envelope,
                envelope_hash=envelope_hash,
                authorization=authorization,
                status="not_executed",
                summary=f"Tool was not entered because authorization was {authorization['verdict']}.",
            )
            raise MiddlewareTermination("Spend preflight did not authorize execution.", result=result)

        execution_claim = authorization["authorization_ref"]
        if execution_claim in self._execution_claims:
            result = {
                "status": "duplicate_no_effect",
                "reason": "authorization was already consumed",
                "authorization_ref": execution_claim,
                "envelope_hash": envelope_hash,
            }
            context.result = result
            self._record_receipt(
                envelope=envelope,
                envelope_hash=envelope_hash,
                authorization=authorization,
                status="duplicate_no_effect",
                summary="Duplicate invocation was blocked before the paid tool body ran.",
            )
            raise MiddlewareTermination("Spend authorization already consumed.", result=result)

        self._execution_claims.add(execution_claim)
        try:
            await call_next()
        except Exception:
            self._record_receipt(
                envelope=envelope,
                envelope_hash=envelope_hash,
                authorization=authorization,
                status="failed",
                summary="The tool body raised after authorization was consumed.",
            )
            raise

        self._record_receipt(
            envelope=envelope,
            envelope_hash=envelope_hash,
            authorization=authorization,
            status="succeeded",
            summary="The paid tool completed after envelope-bound authorization.",
        )
        context.metadata["spend_receipt"] = self.receipts[-1]


# NOTE: approval_mode="never_require" is intentional for this sample. The external preflight
# middleware is the sole authority surface; composing it with tool approval would demonstrate a
# different two-authority workflow.
@tool(approval_mode="never_require")
def buy_dataset_access(
    dataset_name: Annotated[str, Field(description="The dataset to purchase access for.")],
    payee: Annotated[str, Field(description="The provider receiving payment.")],
    amount_usd: Annotated[
        float,
        Field(
            ge=0,
            allow_inf_nan=False,
            description="The non-negative finite spend amount in USD.",
        ),
    ],
) -> str:
    """Purchase short-lived dataset access."""
    return f"Purchased access to {dataset_name} from {payee} for ${amount_usd:.2f}."


async def main() -> None:
    """Demonstrate paid-tool preflight middleware."""
    print("=== Spend Preflight and Receipt Middleware Example ===")

    spend_middleware = SpendPreflightReceiptMiddleware()

    # For authentication, run `az login` command in terminal or replace AzureCliCredential with
    # your preferred authentication option.
    async with (
        AzureCliCredential() as credential,
        Agent(
            client=FoundryChatClient(credential=credential),
            name="DatasetBuyer",
            instructions=(
                "You help purchase short-lived data access. Use buy_dataset_access when the "
                "user asks to buy a dataset."
            ),
            tools=buy_dataset_access,
            middleware=[spend_middleware],
        ) as agent,
    ):
        print("\n--- Approved spend ---")
        result = await agent.run("Buy the public benchmark dataset from Contoso Data for 25 USD.")
        print(f"Agent: {result.text if result.text else result}")

        print("\n--- Approval-required spend ---")
        result = await agent.run("Buy the market-risk dataset from Contoso Data for 75 USD.")
        print(f"Agent: {result.text if result.text else result}")

        print("\nReceipts:")
        for receipt in spend_middleware.receipts:
            print(json.dumps(receipt, indent=2))

    """
    Sample output:
    === Spend Preflight and Receipt Middleware Example ===

    --- Approved spend ---
    Agent: Purchased access to public benchmark dataset from Contoso Data for $25.00.

    --- Approval-required spend ---
    Agent: {'status': 'not_executed', 'verdict': 'requires_approval', ...}

    Receipts:
    {
      "receipt_id": "receipt:1",
      "status": "succeeded",
      "authorization_ref": "auth:...",
      "envelope_hash": "...",
      "recorded_at": "..."
    }
    """


if __name__ == "__main__":
    asyncio.run(main())
