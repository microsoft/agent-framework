"""Fan out concurrent runs across two agents inside a Durable Functions orchestration.

Components used in this sample:
- AzureOpenAIChatClient to create domain-specific agents hosted by Agent Framework.
- AgentFunctionApp to expose orchestration and HTTP triggers.
- Durable Functions orchestration that executes agent calls in parallel and aggregates results.

Prerequisites: configure `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_CHAT_DEPLOYMENT_NAME`, and either
`AZURE_OPENAI_API_KEY` or authenticate with Azure CLI before starting the Functions host."""

import json
import logging
from typing import Any

import azure.durable_functions as df
import azure.functions as func
from agent_framework.azure import AgentFunctionApp, AzureOpenAIChatClient
from azure.durable_functions import DurableOrchestrationContext
from azure.identity import AzureCliCredential

logger = logging.getLogger(__name__)

# 1. Define agent names shared across the orchestration.
PHYSICIST_AGENT_NAME = "PhysicistAgent"
CHEMIST_AGENT_NAME = "ChemistAgent"


# 2. Instantiate both agents that the orchestration will run concurrently.
def _create_agents() -> list[Any]:
    chat_client = AzureOpenAIChatClient(credential=AzureCliCredential())

    physicist = chat_client.create_agent(
        name=PHYSICIST_AGENT_NAME,
        instructions="You are an expert in physics. You answer questions from a physics perspective.",
    )

    chemist = chat_client.create_agent(
        name=CHEMIST_AGENT_NAME,
        instructions="You are an expert in chemistry. You answer questions from a chemistry perspective.",
    )

    return [physicist, chemist]


# 3. Register both agents with AgentFunctionApp and selectively enable HTTP endpoints.
agents = _create_agents()
app = AgentFunctionApp(enable_health_check=True, enable_http_endpoints=False)
app.add_agent(agents[0], enable_http_endpoint=True)
app.add_agent(agents[1])


# 4. Durable Functions orchestration that runs both agents in parallel.
@app.orchestration_trigger(context_name="context")
def multi_agent_concurrent_orchestration(context: DurableOrchestrationContext):
    """Fan out to two domain-specific agents and aggregate their responses."""

    prompt = context.get_input()
    if not prompt or not str(prompt).strip():
        raise ValueError("Prompt is required")

    physicist = app.get_agent(context, PHYSICIST_AGENT_NAME)
    chemist = app.get_agent(context, CHEMIST_AGENT_NAME)

    physicist_thread = physicist.get_new_thread()
    chemist_thread = chemist.get_new_thread()

    physicist_task = physicist.run(messages=str(prompt), thread=physicist_thread)
    chemist_task = chemist.run(messages=str(prompt), thread=chemist_thread)

    results = yield context.task_all([physicist_task, chemist_task])

    return {
        "physicist": results[0].get("response", ""),
        "chemist": results[1].get("response", ""),
    }


# 5. HTTP endpoint to accept prompts and start the concurrent orchestration.
@app.route(route="multiagent/run", methods=["POST"])
@app.durable_client_input(client_name="client")
async def start_multi_agent_concurrent_orchestration(
    req: func.HttpRequest,
    client: df.DurableOrchestrationClient,
) -> func.HttpResponse:
    """Kick off the orchestration with a plain text prompt."""

    body_bytes = req.get_body() or b""
    prompt = body_bytes.decode("utf-8", errors="replace").strip()
    if not prompt:
        return func.HttpResponse(
            body=json.dumps({"error": "Prompt is required"}),
            status_code=400,
            mimetype="application/json",
        )

    instance_id = await client.start_new(
        orchestration_function_name="multi_agent_concurrent_orchestration",
        client_input=prompt,
    )

    logger.info("[HTTP] Started orchestration with instance_id: %s", instance_id)

    status_url = _build_status_url(req.url, instance_id, route="multiagent")

    payload = {
        "message": "Multi-agent concurrent orchestration started.",
        "prompt": prompt,
        "instanceId": instance_id,
        "statusQueryGetUri": status_url,
    }

    return func.HttpResponse(
        body=json.dumps(payload),
        status_code=202,
        mimetype="application/json",
    )


# 6. HTTP endpoint to retrieve orchestration status and aggregated outputs.
@app.route(route="multiagent/status/{instanceId}", methods=["GET"])
@app.durable_client_input(client_name="client")
async def get_orchestration_status(
    req: func.HttpRequest,
    client: df.DurableOrchestrationClient,
) -> func.HttpResponse:
    instance_id = req.route_params.get("instanceId")
    if not instance_id:
        return func.HttpResponse(
            body=json.dumps({"error": "Missing instanceId"}),
            status_code=400,
            mimetype="application/json",
        )

    status = await client.get_status(instance_id)
    if status is None:
        return func.HttpResponse(
            body=json.dumps({"error": "Instance not found"}),
            status_code=404,
            mimetype="application/json",
        )

    response_data: dict[str, Any] = {
        "instanceId": status.instance_id,
        "runtimeStatus": status.runtime_status.name if status.runtime_status else None,
        "createdTime": status.created_time.isoformat() if status.created_time else None,
        "lastUpdatedTime": status.last_updated_time.isoformat() if status.last_updated_time else None,
    }

    if status.input_ is not None:
        response_data["input"] = status.input_

    if status.output is not None:
        response_data["output"] = status.output

    return func.HttpResponse(
        body=json.dumps(response_data),
        status_code=200,
        mimetype="application/json",
    )


# 7. Helper to construct durable status URLs.
def _build_status_url(request_url: str, instance_id: str, *, route: str) -> str:
    base_url, _, _ = request_url.partition("/api/")
    if not base_url:
        base_url = request_url.rstrip("/")
    return f"{base_url}/api/{route}/status/{instance_id}"


"""
Expected output when calling `POST /api/multiagent/run` with a plain-text prompt:

HTTP/1.1 202 Accepted
{
    "message": "Multi-agent concurrent orchestration started.",
    "prompt": "What is temperature?",
    "instanceId": "<guid>",
    "statusQueryGetUri": "http://localhost:7071/api/multiagent/status/<guid>"
}

Polling `GET /api/multiagent/status/<guid>` after completion returns:

HTTP/1.1 200 OK
{
    "instanceId": "<guid>",
    "runtimeStatus": "Completed",
    "output": {
        "physicist": "Temperature measures the average kinetic energy of particles in a system.",
        "chemist": "Temperature reflects how molecular motion influences reaction rates and equilibria."
    }
}
"""
