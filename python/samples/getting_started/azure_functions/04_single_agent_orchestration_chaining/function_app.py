"""Chain two runs of a single agent inside a Durable Functions orchestration.

Components used in this sample:
- AzureOpenAIChatClient to construct the writer agent hosted by Agent Framework.
- AgentFunctionApp to surface HTTP and orchestration triggers via the Azure Functions extension.
- Durable Functions orchestration to run sequential agent invocations on the same conversation thread.

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

# 1. Define the agent name used across the orchestration.
WRITER_AGENT_NAME = "WriterAgent"


# 2. Create the writer agent that will be invoked twice within the orchestration.
def _create_writer_agent() -> Any:
    """Create the writer agent with the same persona as the C# sample."""

    instructions = (
        "You refine short pieces of text. When given an initial sentence you enhance it;\n"
        "when given an improved sentence you polish it further."
    )

    return AzureOpenAIChatClient(credential=AzureCliCredential()).create_agent(
        name=WRITER_AGENT_NAME,
        instructions=instructions,
    )


# 3. Register the agent with AgentFunctionApp so HTTP and orchestration triggers are exposed.
app = AgentFunctionApp(agents=[_create_writer_agent()], enable_health_check=True)


# 4. Orchestration that runs the agent sequentially on a shared thread for chaining behaviour.
@app.orchestration_trigger(context_name="context")
def single_agent_orchestration(context: DurableOrchestrationContext):
    """Run the writer agent twice on the same thread to mirror chaining behaviour."""

    writer = app.get_agent(context, WRITER_AGENT_NAME)
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


# 5. HTTP endpoint to kick off the orchestration and return the status query URI.
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


# 6. HTTP endpoint to fetch orchestration status using the original instance ID.
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


# 7. Helper to construct durable status URLs similar to the .NET sample implementation.
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
