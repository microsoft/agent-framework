"""Chain two runs of a single agent inside a Durable Functions orchestration.

Components used in this sample:
- AzureOpenAIChatClient to construct the writer agent hosted by Agent Framework.
- AgentFunctionApp to surface HTTP and orchestration triggers via the Azure Functions extension.
- Durable Functions orchestration to run sequential agent invocations on the same conversation thread.

Prerequisites: configure `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_CHAT_DEPLOYMENT_NAME`, and either
`AZURE_OPENAI_API_KEY` or authenticate with Azure CLI before starting the Functions host."""

import json
import logging
import os
from typing import Any

import azure.durable_functions as df
import azure.functions as func
from agent_framework.azure import AzureOpenAIChatClient
from azure.durable_functions import DurableOrchestrationContext
from azure.identity import AzureCliCredential
from agent_framework.azurefunctions import AgentFunctionApp, get_agent

logger = logging.getLogger(__name__)

# 1. Define environment variable keys and the agent name used across the orchestration.
AZURE_OPENAI_ENDPOINT_ENV = "AZURE_OPENAI_ENDPOINT"
AZURE_OPENAI_DEPLOYMENT_ENV = "AZURE_OPENAI_CHAT_DEPLOYMENT_NAME"
AZURE_OPENAI_API_KEY_ENV = "AZURE_OPENAI_API_KEY"
WRITER_AGENT_NAME = "WriterAgent"


# 2. Build Azure OpenAI client options shared by the orchestration and agent.
def _build_client_kwargs() -> dict[str, Any]:
    """Construct Azure OpenAI client options."""

    endpoint = os.getenv(AZURE_OPENAI_ENDPOINT_ENV)
    if not endpoint:
        raise RuntimeError(f"{AZURE_OPENAI_ENDPOINT_ENV} environment variable is required.")

    deployment = os.getenv(AZURE_OPENAI_DEPLOYMENT_ENV)
    if not deployment:
        raise RuntimeError(f"{AZURE_OPENAI_DEPLOYMENT_ENV} environment variable is required.")

    logger.info("[SingleAgentOrchestration] Using deployment '%s' at '%s'", deployment, endpoint)

    client_kwargs: dict[str, Any] = {
        "endpoint": endpoint,
        "deployment_name": deployment,
    }

    api_key = os.getenv(AZURE_OPENAI_API_KEY_ENV)
    if api_key:
        client_kwargs["api_key"] = api_key
    else:
        client_kwargs["credential"] = AzureCliCredential()

    return client_kwargs


# 3. Create the writer agent that will be invoked twice within the orchestration.
def _create_writer_agent() -> Any:
    """Create the writer agent with the same persona as the C# sample."""

    instructions = (
        "You refine short pieces of text. When given an initial sentence you enhance it;\n"
        "when given an improved sentence you polish it further."
    )

    return AzureOpenAIChatClient(**_build_client_kwargs()).create_agent(
        name=WRITER_AGENT_NAME,
        instructions=instructions,
    )


# 4. Register the agent with AgentFunctionApp so HTTP and orchestration triggers are exposed.
app = AgentFunctionApp(agents=[_create_writer_agent()], enable_health_check=True)


# 5. Orchestration that runs the agent sequentially on a shared thread for chaining behaviour.
@app.orchestration_trigger(context_name="context")
def single_agent_orchestration(context: DurableOrchestrationContext):
    """Run the writer agent twice on the same thread to mirror chaining behaviour."""

    writer = get_agent(context, WRITER_AGENT_NAME)
    writer_thread = writer.get_new_thread()

    initial = yield writer.run(
        messages="Write a concise inspirational sentence about learning.",
        thread=writer_thread,
    )

    improved_prompt = (
        "Improve this further while keeping it under 25 words: "
        f"{initial.get('response', '').strip()}"
    )

    refined = yield writer.run(
        messages=improved_prompt,
        thread=writer_thread,
    )

    return refined.get("response", "")


# 6. HTTP endpoint to kick off the orchestration and return the status query URI.
@app.route(route="singleagent/run", methods=["POST"])
@app.durable_client_input(client_name="client")
async def start_single_agent_orchestration(
    req: func.HttpRequest,
    client: df.DurableOrchestrationClient,
) -> func.HttpResponse:
    """Start the orchestration and return status metadata."""

    instance_id = await client.start_new(
        orchestration_function_name="single_agent_orchestration",
    )

    logger.info("[HTTP] Started orchestration with instance_id: %s", instance_id)

    status_url = _build_status_url(req.url, instance_id, route="singleagent")

    payload = {
        "message": "Single-agent orchestration started.",
        "instanceId": instance_id,
        "statusQueryGetUri": status_url,
    }

    return func.HttpResponse(
        body=json.dumps(payload),
        status_code=202,
        mimetype="application/json",
    )


# 7. HTTP endpoint to fetch orchestration status using the original instance ID.
@app.route(route="singleagent/status/{instanceId}", methods=["GET"])
@app.durable_client_input(client_name="client")
async def get_orchestration_status(
    req: func.HttpRequest,
    client: df.DurableOrchestrationClient,
) -> func.HttpResponse:
    """Return orchestration runtime status."""

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


# 8. Helper to construct durable status URLs similar to the .NET sample implementation.
def _build_status_url(request_url: str, instance_id: str, *, route: str) -> str:
    """Construct the status query URI similar to DurableHttpApiExtensions in C#."""

    # Split once on /api/ to preserve host and scheme in local emulator and Azure.
    base_url, _, _ = request_url.partition("/api/")
    if not base_url:
        base_url = request_url.rstrip("/")
    return f"{base_url}/api/{route}/status/{instance_id}"


"""
Expected output when calling `POST /api/singleagent/run` and following the returned status URL:

HTTP/1.1 202 Accepted
{
    "message": "Single-agent orchestration started.",
    "instanceId": "<guid>",
    "statusQueryGetUri": "http://localhost:7071/api/singleagent/status/<guid>"
}

Subsequent `GET /api/singleagent/status/<guid>` after completion returns:

HTTP/1.1 200 OK
{
    "instanceId": "<guid>",
    "runtimeStatus": "Completed",
    "output": "Learning is a journey where curiosity turns effort into mastery."
}
"""
