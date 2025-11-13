"""Iterate on generated content with a human-in-the-loop Durable orchestration.

Components used in this sample:
- AzureOpenAIChatClient for a single writer agent that emits structured JSON.
- AgentFunctionApp with Durable orchestration, HTTP triggers, and activity triggers.
- External events that pause the workflow until a human decision arrives or times out.

Prerequisites: configure `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_CHAT_DEPLOYMENT_NAME`, and
either `AZURE_OPENAI_API_KEY` or sign in with Azure CLI before running `func start`."""

import json
import logging
from collections.abc import Mapping
from datetime import timedelta
from typing import Any

import azure.durable_functions as df
import azure.functions as func
from agent_framework.azure import AgentFunctionApp, AzureOpenAIChatClient
from azure.durable_functions import DurableOrchestrationContext
from azure.identity import AzureCliCredential
from pydantic import BaseModel, ValidationError

logger = logging.getLogger(__name__)

# 1. Define orchestration constants used throughout the workflow.
WRITER_AGENT_NAME = "WriterAgent"
HUMAN_APPROVAL_EVENT = "HumanApproval"


class ContentGenerationInput(BaseModel):
    topic: str
    max_review_attempts: int = 3
    approval_timeout_hours: float = 72


class GeneratedContent(BaseModel):
    title: str
    content: str


class HumanApproval(BaseModel):
    approved: bool
    feedback: str = ""


# 2. Create the writer agent that produces structured JSON responses.
def _create_writer_agent() -> Any:
    instructions = (
        "You are a professional content writer who creates high-quality articles on various topics. "
        "You write engaging, informative, and well-structured content that follows best practices for readability and accuracy. "
        "Return your response as JSON with 'title' and 'content' fields."
    )

    return AzureOpenAIChatClient(credential=AzureCliCredential()).create_agent(
        name=WRITER_AGENT_NAME,
        instructions=instructions,
    )


app = AgentFunctionApp(agents=[_create_writer_agent()], enable_health_check=True)


# 3. Activities encapsulate external work for review notifications and publishing.
@app.activity_trigger(input_name="content")
def notify_user_for_approval(content: dict) -> None:
    model = GeneratedContent.model_validate(content)
    logger.info("NOTIFICATION: Please review the following content for approval:")
    logger.info("Title: %s", model.title or "(untitled)")
    logger.info("Content: %s", model.content)
    logger.info("Use the approval endpoint to approve or reject this content.")


@app.activity_trigger(input_name="content")
def publish_content(content: dict) -> None:
    model = GeneratedContent.model_validate(content)
    logger.info("PUBLISHING: Content has been published successfully:")
    logger.info("Title: %s", model.title or "(untitled)")
    logger.info("Content: %s", model.content)


# 4. Orchestration loops until the human approves, times out, or attempts are exhausted.
@app.orchestration_trigger(context_name="context")
def content_generation_hitl_orchestration(context: DurableOrchestrationContext):
    payload_raw = context.get_input()
    if not isinstance(payload_raw, Mapping):
        raise ValueError("Content generation input is required")

    try:
        payload = ContentGenerationInput.model_validate(payload_raw)
    except ValidationError as exc:
        raise ValueError(f"Invalid content generation input: {exc}") from exc

    writer = app.get_agent(context, WRITER_AGENT_NAME)
    writer_thread = writer.get_new_thread()

    context.set_custom_status(f"Starting content generation for topic: {payload.topic}")

    initial_raw = yield writer.run(
        messages=f"Write a short article about '{payload.topic}'.",
        thread=writer_thread,
        response_format=GeneratedContent,
    )
    content = _coerce_generated_content(initial_raw)

    attempt = 0
    while attempt < payload.max_review_attempts:
        attempt += 1
        context.set_custom_status(
            f"Requesting human feedback. Iteration #{attempt}. Timeout: {payload.approval_timeout_hours} hour(s)."
        )

        yield context.call_activity("notify_user_for_approval", content.model_dump())

        approval_task = context.wait_for_external_event(HUMAN_APPROVAL_EVENT)
        timeout_task = context.create_timer(
            context.current_utc_datetime + timedelta(hours=payload.approval_timeout_hours)
        )

        winner = yield context.task_any([approval_task, timeout_task])

        if winner == approval_task:
            timeout_task.cancel()  # type: ignore[attr-defined]
            approval_payload = _parse_human_approval(approval_task.result)

            if approval_payload.approved:
                context.set_custom_status("Content approved by human reviewer. Publishing content...")
                yield context.call_activity("publish_content", content.model_dump())
                context.set_custom_status(
                    f"Content published successfully at {context.current_utc_datetime:%Y-%m-%dT%H:%M:%S}"
                )
                return {"content": content.content}

            context.set_custom_status(
                "Content rejected by human reviewer. Incorporating feedback and regenerating..."
            )
            rewrite_prompt = (
                "The content was rejected by a human reviewer. Please rewrite the article incorporating their feedback.\n\n"
                f"Human Feedback: {approval_payload.feedback or 'No feedback provided.'}"
            )
            rewritten_raw = yield writer.run(
                messages=rewrite_prompt,
                thread=writer_thread,
                response_format=GeneratedContent,
            )
            content = _coerce_generated_content(rewritten_raw)
        else:
            context.set_custom_status(
                f"Human approval timed out after {payload.approval_timeout_hours} hour(s). Treating as rejection."
            )
            raise TimeoutError(
                f"Human approval timed out after {payload.approval_timeout_hours} hour(s)."
            )

    raise RuntimeError(f"Content could not be approved after {payload.max_review_attempts} iteration(s).")


# 5. HTTP endpoint that starts the human-in-the-loop orchestration.
@app.route(route="hitl/run", methods=["POST"])
@app.durable_client_input(client_name="client")
async def start_content_generation(
    req: func.HttpRequest,
    client: df.DurableOrchestrationClient,
) -> func.HttpResponse:
    try:
        body = req.get_json()
    except ValueError:
        body = None

    if not isinstance(body, Mapping):
        return func.HttpResponse(
            body=json.dumps({"error": "Request body must be valid JSON."}),
            status_code=400,
            mimetype="application/json",
        )

    try:
        payload = ContentGenerationInput.model_validate(body)
    except ValidationError as exc:
        return func.HttpResponse(
            body=json.dumps({"error": f"Invalid content generation input: {exc}"}),
            status_code=400,
            mimetype="application/json",
        )

    instance_id = await client.start_new(
        orchestration_function_name="content_generation_hitl_orchestration",
        client_input=payload.model_dump(),
    )

    status_url = _build_status_url(req.url, instance_id, route="hitl")

    payload_json = {
        "message": "HITL content generation orchestration started.",
        "topic": payload.topic,
        "instanceId": instance_id,
        "statusQueryGetUri": status_url,
    }

    return func.HttpResponse(
        body=json.dumps(payload_json),
        status_code=202,
        mimetype="application/json",
    )


# 6. Endpoint that delivers human approval or rejection back into the orchestration.
@app.route(route="hitl/approve/{instanceId}", methods=["POST"])
@app.durable_client_input(client_name="client")
async def send_human_approval(
    req: func.HttpRequest,
    client: df.DurableOrchestrationClient,
) -> func.HttpResponse:
    instance_id = req.route_params.get("instanceId")
    if not instance_id:
        return func.HttpResponse(
            body=json.dumps({"error": "Missing instanceId in route."}),
            status_code=400,
            mimetype="application/json",
        )

    try:
        body = req.get_json()
    except ValueError:
        body = None

    if not isinstance(body, Mapping):
        return func.HttpResponse(
            body=json.dumps({"error": "Approval response is required"}),
            status_code=400,
            mimetype="application/json",
        )

    try:
        approval = HumanApproval.model_validate(body)
    except ValidationError as exc:
        return func.HttpResponse(
            body=json.dumps({"error": f"Invalid approval payload: {exc}"}),
            status_code=400,
            mimetype="application/json",
        )

    await client.raise_event(instance_id, HUMAN_APPROVAL_EVENT, approval.model_dump())

    payload_json = {
        "message": "Human approval sent to orchestration.",
        "instanceId": instance_id,
        "approved": approval.approved,
    }

    return func.HttpResponse(
        body=json.dumps(payload_json),
        status_code=200,
        mimetype="application/json",
    )


# 7. Endpoint that mirrors Durable Functions status plus custom workflow messaging.
@app.route(route="hitl/status/{instanceId}", methods=["GET"])
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

    status = await client.get_status(
        instance_id,
        show_history=False,
        show_history_output=False,
        show_input=True,
    )
    
    # Check if status is None or if the instance doesn't exist (runtime_status is None)
    if status is None or getattr(status, "runtime_status", None) is None:
        return func.HttpResponse(
            body=json.dumps({"error": "Instance not found."}),
            status_code=404,
            mimetype="application/json",
        )

    response_data: dict[str, Any] = {
        "instanceId": getattr(status, "instance_id", None),
        "runtimeStatus": getattr(status.runtime_status, "name", None)
        if getattr(status, "runtime_status", None)
        else None,
        "workflowStatus": getattr(status, "custom_status", None),
    }

    if getattr(status, "input_", None) is not None:
        response_data["input"] = status.input_

    if getattr(status, "output", None) is not None:
        response_data["output"] = status.output

    failure_details = getattr(status, "failure_details", None)
    if failure_details is not None:
        response_data["failureDetails"] = failure_details

    return func.HttpResponse(
        body=json.dumps(response_data),
        status_code=200,
        mimetype="application/json",
    )


# 8. Helper utilities keep parsing logic deterministic.
def _build_status_url(request_url: str, instance_id: str, *, route: str) -> str:
    base_url, _, _ = request_url.partition("/api/")
    if not base_url:
        base_url = request_url.rstrip("/")
    return f"{base_url}/api/{route}/status/{instance_id}"


def _coerce_generated_content(result: Mapping[str, Any]) -> GeneratedContent:
    structured = result.get("structured_response") if isinstance(result, Mapping) else None
    if structured is not None:
        return GeneratedContent.model_validate(structured)

    response_text = result.get("response") if isinstance(result, Mapping) else None
    if isinstance(response_text, str) and response_text.strip():
        try:
            parsed = json.loads(response_text)
            if isinstance(parsed, Mapping):
                return GeneratedContent.model_validate(parsed)
        except json.JSONDecodeError:
            logger.warning("[HITL] Failed to parse agent JSON response; falling back to defaults.")

    raise ValueError("Agent response could not be parsed as GeneratedContent.")


def _parse_human_approval(raw: Any) -> HumanApproval:
    if isinstance(raw, Mapping):
        return HumanApproval.model_validate(raw)

    if isinstance(raw, str):
        stripped = raw.strip()
        if not stripped:
            return HumanApproval(approved=False, feedback="")
        try:
            parsed = json.loads(stripped)
            if isinstance(parsed, Mapping):
                return HumanApproval.model_validate(parsed)
        except json.JSONDecodeError:
            logger.debug(
                "[HITL] Approval payload is not valid JSON; using string heuristics.",
                exc_info=True,
            )

        affirmative = {"true", "yes", "approved", "y", "1"}
        negative = {"false", "no", "rejected", "n", "0"}
        lower = stripped.lower()
        if lower in affirmative:
            return HumanApproval(approved=True, feedback="")
        if lower in negative:
            return HumanApproval(approved=False, feedback="")
        return HumanApproval(approved=False, feedback=stripped)

    raise ValueError("Approval payload must be a JSON object or string.")


"""
Expected response from `POST /api/hitl/run`:

HTTP/1.1 202 Accepted
{
    "message": "HITL content generation orchestration started.",
    "topic": "Contoso launch",
    "instanceId": "<durable-instance-id>",
    "statusQueryGetUri": "http://localhost:7071/api/hitl/status/<durable-instance-id>"
}

Expected response after approving via `POST /api/hitl/approve/{instanceId}`:

HTTP/1.1 200 OK
{
    "message": "Human approval sent to orchestration.",
    "instanceId": "<durable-instance-id>",
    "approved": true
}

Expected response from `GET /api/hitl/status/{instanceId}` once published:

HTTP/1.1 200 OK
{
    "instanceId": "<durable-instance-id>",
    "runtimeStatus": "Completed",
    "workflowStatus": "Content published successfully at 2024-01-01T12:00:00",
    "output": {
        "content": "Thank you for joining the Contoso product launch..."
    }
}
"""
