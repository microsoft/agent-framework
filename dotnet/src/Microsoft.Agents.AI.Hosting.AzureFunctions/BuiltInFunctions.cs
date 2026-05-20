// Copyright (c) Microsoft. All rights reserved.

using System.Net;
using System.Text.Json;
using System.Text.Json.Serialization;
using Microsoft.Agents.AI.DurableTask;
using Microsoft.Agents.AI.DurableTask.Workflows;
using Microsoft.Azure.Functions.Worker;
using Microsoft.Azure.Functions.Worker.Extensions.Mcp;
using Microsoft.Azure.Functions.Worker.Http;
using Microsoft.DurableTask;
using Microsoft.DurableTask.Client;
using Microsoft.DurableTask.Worker.Grpc;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.DependencyInjection;

namespace Microsoft.Agents.AI.Hosting.AzureFunctions;

internal static class BuiltInFunctions
{
    internal const string HttpPrefix = "http-";
    internal const string McpToolPrefix = "mcptool-";

    private const string WaitForResponseHeaderName = "x-ms-wait-for-response";

    internal static readonly string RunAgentHttpFunctionEntryPoint = $"{typeof(BuiltInFunctions).FullName!}.{nameof(RunAgentHttpAsync)}";
    internal static readonly string RunAgentEntityFunctionEntryPoint = $"{typeof(BuiltInFunctions).FullName!}.{nameof(InvokeAgentAsync)}";
    internal static readonly string RunAgentMcpToolFunctionEntryPoint = $"{typeof(BuiltInFunctions).FullName!}.{nameof(RunMcpToolAsync)}";
    internal static readonly string RunWorkflowOrchestrationHttpFunctionEntryPoint = $"{typeof(BuiltInFunctions).FullName!}.{nameof(RunWorkflowOrchestrationHttpTriggerAsync)}";
    internal static readonly string RunWorkflowOrchestrationFunctionEntryPoint = $"{typeof(BuiltInFunctions).FullName!}.{nameof(RunWorkflowOrchestration)}";
    internal static readonly string InvokeWorkflowActivityFunctionEntryPoint = $"{typeof(BuiltInFunctions).FullName!}.{nameof(InvokeWorkflowActivityAsync)}";
    internal static readonly string GetWorkflowStatusHttpFunctionEntryPoint = $"{typeof(BuiltInFunctions).FullName!}.{nameof(GetWorkflowStatusAsync)}";
    internal static readonly string RespondToWorkflowHttpFunctionEntryPoint = $"{typeof(BuiltInFunctions).FullName!}.{nameof(RespondToWorkflowAsync)}";
    internal static readonly string RunWorkflowMcpToolFunctionEntryPoint = $"{typeof(BuiltInFunctions).FullName!}.{nameof(RunWorkflowMcpToolAsync)}";

#pragma warning disable IL3000 // Avoid accessing Assembly file path when publishing as a single file - Azure Functions does not use single-file publishing
    internal static readonly string ScriptFile = Path.GetFileName(typeof(BuiltInFunctions).Assembly.Location);
#pragma warning restore IL3000

    /// <summary>
    /// Starts a workflow orchestration in response to an HTTP request.
    /// The workflow name is derived from the function name by stripping the <see cref="HttpPrefix"/>.
    /// Callers can optionally provide a custom run ID via the <c>runId</c> query string parameter
    /// (e.g., <c>/api/workflows/MyWorkflow/run?runId=my-id</c>). If not provided, one is auto-generated.
    /// </summary>
    public static async Task<HttpResponseData> RunWorkflowOrchestrationHttpTriggerAsync(
        [HttpTrigger] HttpRequestData req,
        [DurableClient] DurableTaskClient client,
        FunctionContext context)
    {
        string workflowName = context.FunctionDefinition.Name.Replace(HttpPrefix, string.Empty);
        string orchestrationFunctionName = WorkflowNamingHelper.ToOrchestrationFunctionName(workflowName);
        string? inputMessage = await req.ReadAsStringAsync();

        if (string.IsNullOrEmpty(inputMessage))
        {
            return await CreateErrorResponseAsync(req, context, HttpStatusCode.BadRequest, "Workflow input cannot be empty.");
        }

        DurableWorkflowInput<string> orchestrationInput = new() { Input = inputMessage };

        // Allow users to provide a custom run ID via query string; otherwise, auto-generate one.
        string? instanceId = req.Query["runId"];
        StartOrchestrationOptions? options = instanceId is not null ? new StartOrchestrationOptions(instanceId) : null;
        string resolvedInstanceId = await client.ScheduleNewOrchestrationInstanceAsync(orchestrationFunctionName, orchestrationInput, options);

        if (ShouldWaitForResponse(req, defaultValue: false))
        {
            return await WaitForWorkflowCompletionAsync(req, client, context, resolvedInstanceId);
        }

        HttpResponseData response = req.CreateResponse(HttpStatusCode.Accepted);
        await response.WriteStringAsync($"Workflow orchestration started for {workflowName}. Orchestration runId: {resolvedInstanceId}");
        return response;
    }

    /// <summary>
    /// Returns the workflow status including any pending HITL requests.
    /// The run ID is extracted from the route parameter <c>{runId}</c>.
    /// </summary>
    public static async Task<HttpResponseData> GetWorkflowStatusAsync(
        [HttpTrigger] HttpRequestData req,
        [DurableClient] DurableTaskClient client,
        FunctionContext context)
    {
        string? runId = context.BindingContext.BindingData.TryGetValue("runId", out object? value) ? value?.ToString() : null;
        if (string.IsNullOrEmpty(runId))
        {
            return await CreateErrorResponseAsync(req, context, HttpStatusCode.BadRequest, "Run ID is required.");
        }

        OrchestrationMetadata? metadata = await client.GetInstanceAsync(runId, getInputsAndOutputs: true);
        if (metadata is null)
        {
            return await CreateErrorResponseAsync(req, context, HttpStatusCode.NotFound, $"Workflow run '{runId}' not found.");
        }

        // Parse HITL inputs the workflow is waiting for from the durable workflow status
        List<PendingRequestPortStatus>? waitingForInput = null;
        if (DurableWorkflowLiveStatus.TryParse(metadata.SerializedCustomStatus, out DurableWorkflowLiveStatus liveStatus)
            && liveStatus.PendingEvents.Count > 0)
        {
            waitingForInput = liveStatus.PendingEvents;
        }

        HttpResponseData response = req.CreateResponse(HttpStatusCode.OK);
        await response.WriteAsJsonAsync(new
        {
            runId,
            status = metadata.RuntimeStatus.ToString(),
            waitingForInput = waitingForInput?.Select(p => new { eventName = p.EventName, input = JsonDocument.Parse(p.Input).RootElement })
        });
        return response;
    }

    /// <summary>
    /// Sends a response to a pending RequestPort, resuming the workflow.
    /// Expects a JSON body: <c>{ "eventName": "...", "response": { ... } }</c>.
    /// </summary>
    public static async Task<HttpResponseData> RespondToWorkflowAsync(
        [HttpTrigger] HttpRequestData req,
        [DurableClient] DurableTaskClient client,
        FunctionContext context)
    {
        string? runId = context.BindingContext.BindingData.TryGetValue("runId", out object? value) ? value?.ToString() : null;
        if (string.IsNullOrEmpty(runId))
        {
            return await CreateErrorResponseAsync(req, context, HttpStatusCode.BadRequest, "Run ID is required.");
        }

        WorkflowRespondRequest? request;
        try
        {
            request = await req.ReadFromJsonAsync<WorkflowRespondRequest>(context.CancellationToken);
        }
        catch (JsonException)
        {
            return await CreateErrorResponseAsync(req, context, HttpStatusCode.BadRequest, "Request body is not valid JSON.");
        }

        if (request is null || string.IsNullOrEmpty(request.EventName)
            || request.Response.ValueKind == JsonValueKind.Undefined)
        {
            return await CreateErrorResponseAsync(req, context, HttpStatusCode.BadRequest, "Body must contain a non-empty 'eventName' and a 'response' property.");
        }

        // Verify the orchestration exists and is in a valid state
        OrchestrationMetadata? metadata = await client.GetInstanceAsync(runId, getInputsAndOutputs: true);
        if (metadata is null)
        {
            return await CreateErrorResponseAsync(req, context, HttpStatusCode.NotFound, $"Workflow run '{runId}' not found.");
        }

        if (metadata.RuntimeStatus is OrchestrationRuntimeStatus.Completed
            or OrchestrationRuntimeStatus.Failed
            or OrchestrationRuntimeStatus.Terminated)
        {
            return await CreateErrorResponseAsync(req, context, HttpStatusCode.BadRequest,
                $"Workflow run '{runId}' is in terminal state '{metadata.RuntimeStatus}'.");
        }

        // Verify the workflow is waiting for the specified event.
        // If status can't be parsed (e.g., not yet set during early execution), allow the event through —
        // Durable Task safely queues it until the orchestration reaches WaitForExternalEvent.
        bool eventValidated = false;
        if (DurableWorkflowLiveStatus.TryParse(metadata.SerializedCustomStatus, out DurableWorkflowLiveStatus liveStatus))
        {
            if (!liveStatus.PendingEvents.Exists(p => string.Equals(p.EventName, request.EventName, StringComparison.Ordinal)))
            {
                return await CreateErrorResponseAsync(req, context, HttpStatusCode.BadRequest,
                    $"Workflow is not waiting for event '{request.EventName}'.");
            }

            eventValidated = true;
        }

        // Raise the external event to unblock the orchestration's WaitForExternalEvent call
        await client.RaiseEventAsync(runId, request.EventName, request.Response.GetRawText());

        HttpResponseData response = req.CreateResponse(HttpStatusCode.Accepted);
        await response.WriteAsJsonAsync(new
        {
            message = eventValidated
                ? "Response sent to workflow."
                : "Response sent to workflow. Event could not be validated against pending requests.",
            runId,
            eventName = request.EventName,
            validated = eventValidated,
        });
        return response;
    }

    /// <summary>
    /// Executes a workflow activity by looking up the registered executor and delegating to it.
    /// The executor name is derived from the activity function name via <see cref="WorkflowNamingHelper"/>.
    /// </summary>
    public static Task<string> InvokeWorkflowActivityAsync(
        [ActivityTrigger] string input,
        [DurableClient] DurableTaskClient durableTaskClient,
        FunctionContext functionContext)
    {
        ArgumentNullException.ThrowIfNull(input);
        ArgumentNullException.ThrowIfNull(durableTaskClient);
        ArgumentNullException.ThrowIfNull(functionContext);

        string activityFunctionName = functionContext.FunctionDefinition.Name;
        string executorName = WorkflowNamingHelper.ToWorkflowName(activityFunctionName);

        DurableOptions durableOptions = functionContext.InstanceServices.GetRequiredService<DurableOptions>();
        if (!durableOptions.Workflows.Executors.TryGetExecutor(executorName, out ExecutorRegistration? registration))
        {
            throw new InvalidOperationException($"Executor '{executorName}' not found in workflow options.");
        }

        return DurableActivityExecutor.ExecuteAsync(registration.Binding, input, functionContext.CancellationToken);
    }

    /// <summary>
    /// Runs a workflow orchestration by delegating to <see cref="WorkflowOrchestrator"/>
    /// via <see cref="GrpcOrchestrationRunner"/>.
    /// </summary>
    public static string RunWorkflowOrchestration(
        string encodedOrchestratorRequest,
        FunctionContext functionContext)
    {
        ArgumentNullException.ThrowIfNull(encodedOrchestratorRequest);
        ArgumentNullException.ThrowIfNull(functionContext);

        WorkflowOrchestrator orchestrator = new(functionContext.InstanceServices);
        return GrpcOrchestrationRunner.LoadAndRun(encodedOrchestratorRequest, orchestrator, functionContext.InstanceServices);
    }

    // Exposed as an entity trigger via AgentFunctionsProvider
    public static Task<string> InvokeAgentAsync(
        [DurableClient] DurableTaskClient client,
        string encodedEntityRequest,
        FunctionContext functionContext)
    {
        // This should never be null except if the function trigger is misconfigured.
        ArgumentNullException.ThrowIfNull(client);
        ArgumentNullException.ThrowIfNull(encodedEntityRequest);
        ArgumentNullException.ThrowIfNull(functionContext);

        // Create a combined service provider that includes both the existing services
        // and the DurableTaskClient instance
        IServiceProvider combinedServiceProvider = new CombinedServiceProvider(functionContext.InstanceServices, client);

        // This method is the entry point for the agent entity.
        // It will be invoked by the Azure Functions runtime when the entity is called.
        AgentEntity entity = new(combinedServiceProvider, functionContext.CancellationToken);
        return GrpcEntityRunner.LoadAndRunAsync(encodedEntityRequest, entity, combinedServiceProvider);
    }

    public static async Task<HttpResponseData> RunAgentHttpAsync(
        [HttpTrigger] HttpRequestData req,
        [DurableClient] DurableTaskClient client,
        FunctionContext context)
    {
        // Parse request body - support both JSON and plain text
        string? message = null;
        string? threadIdFromBody = null;

        if (req.Headers.TryGetValues("Content-Type", out IEnumerable<string>? contentTypeValues) &&
            contentTypeValues.Any(ct => ct.Contains("application/json", StringComparison.OrdinalIgnoreCase)))
        {
            // Parse JSON body using POCO record
            AgentRunRequest? requestBody = await req.ReadFromJsonAsync<AgentRunRequest>(context.CancellationToken);
            if (requestBody != null)
            {
                message = requestBody.Message;
                threadIdFromBody = requestBody.ThreadId;
            }
        }
        else
        {
            // Plain text body
            message = await req.ReadAsStringAsync();
        }

        // The session ID can come from query string or JSON body
        string? threadIdFromQuery = req.Query["thread_id"];

        // Validate that if thread_id is specified in both places, they must match
        if (!string.IsNullOrEmpty(threadIdFromQuery) && !string.IsNullOrEmpty(threadIdFromBody) &&
            !string.Equals(threadIdFromQuery, threadIdFromBody, StringComparison.Ordinal))
        {
            return await CreateErrorResponseAsync(
                req,
                context,
                HttpStatusCode.BadRequest,
                "thread_id specified in both query string and request body must match.");
        }

        string? threadIdValue = threadIdFromBody ?? threadIdFromQuery;

        // The thread_id is treated as a session key (not a full session ID).
        // If no session key is provided, use the function invocation ID as the session key
        // to help correlate the session with the function invocation.
        string agentName = GetAgentName(context);
        AgentSessionId sessionId = string.IsNullOrEmpty(threadIdValue)
            ? new AgentSessionId(agentName, context.InvocationId)
            : new AgentSessionId(agentName, threadIdValue);

        if (string.IsNullOrWhiteSpace(message))
        {
            return await CreateErrorResponseAsync(
                req,
                context,
                HttpStatusCode.BadRequest,
                "Run request cannot be empty.");
        }

        // Check if we should wait for response (default is true)
        bool waitForResponse = ShouldWaitForResponse(req, defaultValue: true);

        AIAgent agentProxy = client.AsDurableAgentProxy(context, agentName);

        DurableAgentRunOptions options = new() { IsFireAndForget = !waitForResponse };

        if (waitForResponse)
        {
            AgentResponse agentResponse = await agentProxy.RunAsync(
                message: new ChatMessage(ChatRole.User, message),
                session: new DurableAgentSession(sessionId),
                options: options,
                cancellationToken: context.CancellationToken);

            return await CreateSuccessResponseAsync(
                req,
                context,
                HttpStatusCode.OK,
                sessionId.Key,
                agentResponse);
        }

        // Fire and forget - return 202 Accepted
        await agentProxy.RunAsync(
            message: new ChatMessage(ChatRole.User, message),
            session: new DurableAgentSession(sessionId),
            options: options,
            cancellationToken: context.CancellationToken);

        return await CreateAcceptedResponseAsync(
            req,
            context,
            sessionId.Key);
    }

    public static async Task<string?> RunMcpToolAsync(
        [McpToolTrigger("BuiltInMcpTool")] ToolInvocationContext context,
        [DurableClient] DurableTaskClient client,
        FunctionContext functionContext)
    {
        if (context.Arguments is null)
        {
            throw new ArgumentException("MCP Tool invocation is missing required arguments.");
        }

        if (!context.Arguments.TryGetValue("query", out object? queryObj) || queryObj is not string query)
        {
            throw new ArgumentException("MCP Tool invocation is missing required 'query' argument of type string.");
        }

        string agentName = context.Name;

        // Derive session id: try to parse provided threadId, otherwise create a new one.
        AgentSessionId sessionId = context.Arguments.TryGetValue("threadId", out object? threadObj) && threadObj is string threadId && !string.IsNullOrWhiteSpace(threadId)
            ? AgentSessionId.Parse(threadId)
            : new AgentSessionId(agentName, functionContext.InvocationId);

        AIAgent agentProxy = client.AsDurableAgentProxy(functionContext, agentName);

        AgentResponse agentResponse = await agentProxy.RunAsync(
            message: new ChatMessage(ChatRole.User, query),
            session: new DurableAgentSession(sessionId),
            options: null);

        return agentResponse.Text;
    }

    /// <summary>
    /// Runs a workflow via MCP tool trigger.
    /// Extracts the <c>input</c> argument, schedules a new orchestration, waits for completion, and returns the output.
    /// </summary>
    public static async Task<string?> RunWorkflowMcpToolAsync(
        [McpToolTrigger("BuiltInWorkflowMcpTool")] ToolInvocationContext context,
        [DurableClient] DurableTaskClient client,
        FunctionContext functionContext)
    {
        if (context.Arguments is null)
        {
            throw new ArgumentException("MCP Tool invocation is missing required arguments.");
        }

        if (!context.Arguments.TryGetValue("input", out object? inputObj) || inputObj is not string input)
        {
            throw new ArgumentException("MCP Tool invocation is missing required 'input' argument of type string.");
        }

        string workflowName = context.Name;
        string orchestrationFunctionName = WorkflowNamingHelper.ToOrchestrationFunctionName(workflowName);

        DurableWorkflowInput<string> orchestrationInput = new() { Input = input };
        string instanceId = await client.ScheduleNewOrchestrationInstanceAsync(orchestrationFunctionName, orchestrationInput);

        OrchestrationMetadata? metadata = await client.WaitForInstanceCompletionAsync(
            instanceId,
            getInputsAndOutputs: true,
            cancellation: functionContext.CancellationToken);

        if (metadata is null)
        {
            throw new InvalidOperationException($"Workflow orchestration '{instanceId}' returned no metadata.");
        }

        if (metadata.RuntimeStatus is OrchestrationRuntimeStatus.Failed)
        {
            string errorMessage = metadata.FailureDetails?.ErrorMessage ?? "Unknown error";
            throw new InvalidOperationException($"Workflow orchestration '{instanceId}' failed: {errorMessage}");
        }

        if (metadata.RuntimeStatus is not OrchestrationRuntimeStatus.Completed)
        {
            throw new InvalidOperationException($"Workflow orchestration '{instanceId}' ended with unexpected status '{metadata.RuntimeStatus}'.");
        }

        return metadata.ReadOutputAs<DurableWorkflowResult>()?.Result;
    }

    /// <summary>
    /// Waits for a workflow orchestration to complete and returns an appropriate HTTP response.
    /// </summary>
    private static async Task<HttpResponseData> WaitForWorkflowCompletionAsync(
        HttpRequestData req,
        DurableTaskClient client,
        FunctionContext context,
        string instanceId)
    {
        bool acceptsJson = AcceptsJson(req);

        OrchestrationMetadata? metadata = await client.WaitForInstanceCompletionAsync(
            instanceId,
            getInputsAndOutputs: true,
            cancellation: context.CancellationToken);

        if (metadata is null)
        {
            return await CreateErrorResponseAsync(req, context, HttpStatusCode.NotFound,
                $"No workflow orchestration with ID '{instanceId}' was found.", acceptsJson);
        }

        if (metadata.RuntimeStatus is OrchestrationRuntimeStatus.Failed)
        {
            string errorMessage = metadata.FailureDetails?.ErrorMessage ?? "Unknown error";
            HttpResponseData failedResponse = req.CreateResponse(HttpStatusCode.OK);

            if (acceptsJson)
            {
                await failedResponse.WriteAsJsonAsync(
                    new WorkflowRunResponse(instanceId, metadata.RuntimeStatus.ToString(), Result: null, Error: errorMessage),
                    context.CancellationToken);
            }
            else
            {
                failedResponse.Headers.Add("Content-Type", "text/plain");
                await failedResponse.WriteStringAsync(errorMessage, context.CancellationToken);
            }

            return failedResponse;
        }

        if (metadata.RuntimeStatus is not OrchestrationRuntimeStatus.Completed)
        {
            return await CreateErrorResponseAsync(req, context, HttpStatusCode.InternalServerError,
                $"Workflow orchestration '{instanceId}' ended with unexpected status '{metadata.RuntimeStatus}'.", acceptsJson);
        }

        string? result = metadata.ReadOutputAs<DurableWorkflowResult>()?.Result;

        HttpResponseData response = req.CreateResponse(HttpStatusCode.OK);

        if (acceptsJson)
        {
            JsonElement? resultElement = null;
            if (!string.IsNullOrEmpty(result))
            {
                try
                {
                    using JsonDocument doc = JsonDocument.Parse(result);
                    resultElement = doc.RootElement.Clone();
                }
                catch (JsonException)
                {
                    // Result is a plain string (not valid JSON) — serialize it as a JSON string element.
                    var buffer = new System.Buffers.ArrayBufferWriter<byte>();
                    using (var writer = new Utf8JsonWriter(buffer))
                    {
                        writer.WriteStringValue(result);
                    }

                    using JsonDocument fallbackDoc = JsonDocument.Parse(buffer.WrittenMemory);
                    resultElement = fallbackDoc.RootElement.Clone();
                }
            }

            await response.WriteAsJsonAsync(
                new WorkflowRunResponse(instanceId, metadata.RuntimeStatus.ToString(), resultElement),
                context.CancellationToken);
        }
        else
        {
            response.Headers.Add("Content-Type", "text/plain");
            await response.WriteStringAsync(result ?? string.Empty, context.CancellationToken);
        }

        return response;
    }

    /// <summary>
    /// Creates an error response with the specified status code and error message.
    /// </summary>
    /// <param name="req">The HTTP request data.</param>
    /// <param name="context">The function context.</param>
    /// <param name="statusCode">The HTTP status code.</param>
    /// <param name="errorMessage">The error message.</param>
    /// <param name="acceptsJson">Optional pre-computed value indicating whether the client accepts JSON. When <see langword="null"/>, the value is determined from the request's <c>Accept</c> header.</param>
    /// <returns>The HTTP response data containing the error.</returns>
    private static async Task<HttpResponseData> CreateErrorResponseAsync(
        HttpRequestData req,
        FunctionContext context,
        HttpStatusCode statusCode,
        string errorMessage,
        bool? acceptsJson = null)
    {
        HttpResponseData response = req.CreateResponse(statusCode);

        if (acceptsJson ?? AcceptsJson(req))
        {
            ErrorResponse errorResponse = new((int)statusCode, errorMessage);
            await response.WriteAsJsonAsync(errorResponse, context.CancellationToken);
        }
        else
        {
            response.Headers.Add("Content-Type", "text/plain");
            await response.WriteStringAsync(errorMessage, context.CancellationToken);
        }

        return response;
    }

    /// <summary>
    /// Creates a successful agent run response with the agent's response.
    /// </summary>
    /// <param name="req">The HTTP request data.</param>
    /// <param name="context">The function context.</param>
    /// <param name="statusCode">The HTTP status code (typically 200 OK).</param>
    /// <param name="sessionId">The session ID for the conversation.</param>
    /// <param name="agentResponse">The agent's response.</param>
    /// <returns>The HTTP response data containing the success response.</returns>
    private static async Task<HttpResponseData> CreateSuccessResponseAsync(
        HttpRequestData req,
        FunctionContext context,
        HttpStatusCode statusCode,
        string sessionId,
        AgentResponse agentResponse)
    {
        HttpResponseData response = req.CreateResponse(statusCode);
        response.Headers.Add("x-ms-thread-id", sessionId);

        if (AcceptsJson(req))
        {
            AgentRunSuccessResponse successResponse = new((int)statusCode, sessionId, agentResponse);
            await response.WriteAsJsonAsync(successResponse, context.CancellationToken);
        }
        else
        {
            response.Headers.Add("Content-Type", "text/plain");
            await response.WriteStringAsync(agentResponse.Text, context.CancellationToken);
        }

        return response;
    }

    /// <summary>
    /// Creates an accepted (fire-and-forget) agent run response.
    /// </summary>
    /// <param name="req">The HTTP request data.</param>
    /// <param name="context">The function context.</param>
    /// <param name="sessionId">The session ID for the conversation.</param>
    /// <returns>The HTTP response data containing the accepted response.</returns>
    private static async Task<HttpResponseData> CreateAcceptedResponseAsync(
        HttpRequestData req,
        FunctionContext context,
        string sessionId)
    {
        HttpResponseData response = req.CreateResponse(HttpStatusCode.Accepted);
        response.Headers.Add("x-ms-thread-id", sessionId);

        if (AcceptsJson(req))
        {
            AgentRunAcceptedResponse acceptedResponse = new((int)HttpStatusCode.Accepted, sessionId);
            await response.WriteAsJsonAsync(acceptedResponse, context.CancellationToken);
        }
        else
        {
            response.Headers.Add("Content-Type", "text/plain");
            await response.WriteStringAsync("Request accepted.", context.CancellationToken);
        }

        return response;
    }

    /// <summary>
    /// Returns <see langword="true"/> when the caller has requested waiting for the workflow/agent to complete,
    /// as indicated by the <c>x-ms-wait-for-response</c> header. Falls back to <paramref name="defaultValue"/>
    /// when the header is absent or not a valid boolean.
    /// </summary>
    private static bool ShouldWaitForResponse(HttpRequestData req, bool defaultValue)
    {
        if (req.Headers.TryGetValues(WaitForResponseHeaderName, out IEnumerable<string>? values) &&
            bool.TryParse(values.FirstOrDefault(), out bool parsed))
        {
            return parsed;
        }

        return defaultValue;
    }

    /// <summary>
    /// Returns <see langword="true"/> when the request accepts the <c>application/json</c> media type.
    /// </summary>
    private static bool AcceptsJson(HttpRequestData req)
    {
        return req.Headers.TryGetValues("Accept", out IEnumerable<string>? acceptValues) &&
            acceptValues
                .SelectMany(v => v.Split(',', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries))
                .Select(v => v.Split(';', 2)[0].Trim())
                .Contains("application/json", StringComparer.OrdinalIgnoreCase);
    }

    private static string GetAgentName(FunctionContext context)
    {
        // Check if the function name starts with the HttpPrefix
        string functionName = context.FunctionDefinition.Name;
        if (!functionName.StartsWith(HttpPrefix, StringComparison.Ordinal))
        {
            // This should never happen because the function metadata provider ensures
            // that the function name starts with the HttpPrefix (http-).
            throw new InvalidOperationException(
                $"Built-in HTTP trigger function name '{functionName}' does not start with '{HttpPrefix}'.");
        }

        // Remove the HttpPrefix from the function name to get the agent name.
        return functionName[HttpPrefix.Length..];
    }

    /// <summary>
    /// Represents a request to run an agent.
    /// </summary>
    /// <param name="Message">The message to send to the agent.</param>
    /// <param name="ThreadId">The optional session ID to continue a conversation.</param>
    private sealed record AgentRunRequest(
        [property: JsonPropertyName("message")] string? Message,
        [property: JsonPropertyName("thread_id")] string? ThreadId);

    /// <summary>
    /// Represents an error response.
    /// </summary>
    /// <param name="Status">The HTTP status code.</param>
    /// <param name="Error">The error message.</param>
    private sealed record ErrorResponse(
        [property: JsonPropertyName("status")] int Status,
        [property: JsonPropertyName("error")] string Error);

    /// <summary>
    /// Represents a successful agent run response.
    /// </summary>
    /// <param name="Status">The HTTP status code.</param>
    /// <param name="ThreadId">The session ID for the conversation.</param>
    /// <param name="Response">The agent response.</param>
    private sealed record AgentRunSuccessResponse(
        [property: JsonPropertyName("status")] int Status,
        [property: JsonPropertyName("thread_id")] string ThreadId,
        [property: JsonPropertyName("response")] AgentResponse Response);

    /// <summary>
    /// Represents an accepted (fire-and-forget) agent run response.
    /// </summary>
    /// <param name="Status">The HTTP status code.</param>
    /// <param name="ThreadId">The session ID for the conversation.</param>
    private sealed record AgentRunAcceptedResponse(
        [property: JsonPropertyName("status")] int Status,
        [property: JsonPropertyName("thread_id")] string ThreadId);

    /// <summary>
    /// Represents a request to respond to a pending RequestPort in a workflow.
    /// </summary>
    /// <param name="EventName">The name of the event to raise (the RequestPort ID).</param>
    /// <param name="Response">The response payload to send to the workflow.</param>
    private sealed record WorkflowRespondRequest(
        [property: JsonPropertyName("eventName")] string? EventName,
        [property: JsonPropertyName("response")] JsonElement Response);

    /// <summary>
    /// Represents a workflow run response when waiting for completion.
    /// </summary>
    /// <param name="RunId">The orchestration run ID.</param>
    /// <param name="WorkflowStatus">The orchestration runtime status (e.g., "Completed", "Failed").</param>
    /// <param name="Result">The workflow result as a JSON element so POCOs serialize as nested objects rather than escaped strings.</param>
    /// <param name="Error">An optional error message when the workflow has failed.</param>
    private sealed record WorkflowRunResponse(
        [property: JsonPropertyName("runId")] string RunId,
        [property: JsonPropertyName("workflowStatus")] string WorkflowStatus,
        [property: JsonPropertyName("result")] JsonElement? Result,
        [property: JsonPropertyName("error"), JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)] string? Error = null);

    /// <summary>
    /// A service provider that combines the original service provider with an additional DurableTaskClient instance.
    /// </summary>
    private sealed class CombinedServiceProvider(IServiceProvider originalProvider, DurableTaskClient client)
        : IServiceProvider, IKeyedServiceProvider
    {
        private readonly IServiceProvider _originalProvider = originalProvider;
        private readonly DurableTaskClient _client = client;

        public object? GetKeyedService(Type serviceType, object? serviceKey)
        {
            if (this._originalProvider is IKeyedServiceProvider keyedProvider)
            {
                return keyedProvider.GetKeyedService(serviceType, serviceKey);
            }

            return null;
        }

        public object GetRequiredKeyedService(Type serviceType, object? serviceKey)
        {
            if (this._originalProvider is IKeyedServiceProvider keyedProvider)
            {
                return keyedProvider.GetRequiredKeyedService(serviceType, serviceKey);
            }

            throw new InvalidOperationException("The original service provider does not support keyed services.");
        }

        public object? GetService(Type serviceType)
        {
            // If the requested service is DurableTaskClient, return our instance
            if (serviceType == typeof(DurableTaskClient))
            {
                return this._client;
            }

            // Otherwise try to get the service from the original provider
            return this._originalProvider.GetService(serviceType);
        }
    }
}
