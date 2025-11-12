// Copyright (c) Microsoft. All rights reserved.

using System.Net;
using System.Text.Json.Serialization;
using Microsoft.Agents.AI.DurableTask;
using Microsoft.Azure.Functions.Worker;
using Microsoft.Azure.Functions.Worker.Extensions.Mcp;
using Microsoft.Azure.Functions.Worker.Http;
using Microsoft.DurableTask.Client;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.DependencyInjection;

namespace Microsoft.Agents.AI.Hosting.AzureFunctions;

internal static class BuiltInFunctions
{
    internal const string HttpPrefix = "http-";
    internal const string McpToolPrefix = "mcptool-";

    internal static readonly string RunAgentHttpFunctionEntryPoint = $"{typeof(BuiltInFunctions).FullName!}.{nameof(RunAgentHttpAsync)}";
    internal static readonly string RunAgentEntityFunctionEntryPoint = $"{typeof(BuiltInFunctions).FullName!}.{nameof(InvokeAgentAsync)}";
    internal static readonly string RunAgentMcpToolFunctionEntryPoint = $"{typeof(BuiltInFunctions).FullName!}.{nameof(RunMcpToolAsync)}";

    // Exposed as an entity trigger via AgentFunctionsProvider
    public static async Task InvokeAgentAsync(
        [EntityTrigger] TaskEntityDispatcher dispatcher,
        [DurableClient] DurableTaskClient client,
        FunctionContext functionContext)
    {
        // This should never be null except if the function trigger is misconfigured.
        ArgumentNullException.ThrowIfNull(dispatcher);
        ArgumentNullException.ThrowIfNull(client);
        ArgumentNullException.ThrowIfNull(functionContext);

        // Create a combined service provider that includes both the existing services
        // and the DurableTaskClient instance
        IServiceProvider combinedServiceProvider = new CombinedServiceProvider(functionContext.InstanceServices, client);

        // This method is the entry point for the agent entity.
        // It will be invoked by the Azure Functions runtime when the entity is called.
        await dispatcher.DispatchAsync(new AgentEntity(combinedServiceProvider, functionContext.CancellationToken));
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

        // The thread ID can come from query string or JSON body
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

        // If no session ID is provided, use a new one based on the function name and invocation ID.
        // This may be better than a random one because it can be correlated with the function invocation.
        // Specifying a session ID is how the caller correlates multiple calls to the same agent session.
        AgentSessionId sessionId = string.IsNullOrEmpty(threadIdValue)
            ? new AgentSessionId(GetAgentName(context), context.InvocationId)
            : AgentSessionId.Parse(threadIdValue);

        if (string.IsNullOrWhiteSpace(message))
        {
            return await CreateErrorResponseAsync(
                req,
                context,
                HttpStatusCode.BadRequest,
                "Run request cannot be empty.");
        }

        // Check if we should wait for response (default is true)
        bool waitForResponse = true;
        if (req.Headers.TryGetValues("x-ms-wait-for-response", out IEnumerable<string>? waitForResponseValues))
        {
            string? waitForResponseValue = waitForResponseValues.FirstOrDefault();
            if (!string.IsNullOrEmpty(waitForResponseValue) && bool.TryParse(waitForResponseValue, out bool parsedValue))
            {
                waitForResponse = parsedValue;
            }
        }

        AIAgent agentProxy = client.AsDurableAgentProxy(context, GetAgentName(context));

        DurableAgentRunOptions options = new() { IsFireAndForget = !waitForResponse };

        if (waitForResponse)
        {
            AgentRunResponse agentResponse = await agentProxy.RunAsync(
                message: new ChatMessage(ChatRole.User, message),
                thread: new DurableAgentThread(sessionId),
                options: options,
                cancellationToken: context.CancellationToken);

            return await CreateSuccessResponseAsync(
                req,
                context,
                HttpStatusCode.OK,
                sessionId.ToString(),
                agentResponse);
        }

        // Fire and forget - return 202 Accepted
        await agentProxy.RunAsync(
            message: new ChatMessage(ChatRole.User, message),
            thread: new DurableAgentThread(sessionId),
            options: options,
            cancellationToken: context.CancellationToken);

        return await CreateAcceptedResponseAsync(
            req,
            context,
            sessionId.ToString());
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

        AgentRunResponse agentResponse = await agentProxy.RunAsync(
            message: new ChatMessage(ChatRole.User, query),
            thread: new DurableAgentThread(sessionId),
            options: null);

        return agentResponse.Text;
    }

    /// <summary>
    /// Creates an error response with the specified status code and error message.
    /// </summary>
    /// <param name="req">The HTTP request data.</param>
    /// <param name="context">The function context.</param>
    /// <param name="statusCode">The HTTP status code.</param>
    /// <param name="errorMessage">The error message.</param>
    /// <returns>The HTTP response data containing the error.</returns>
    private static async Task<HttpResponseData> CreateErrorResponseAsync(
        HttpRequestData req,
        FunctionContext context,
        HttpStatusCode statusCode,
        string errorMessage)
    {
        HttpResponseData response = req.CreateResponse(statusCode);
        bool acceptsJson = req.Headers.TryGetValues("Accept", out IEnumerable<string>? acceptValues) &&
            acceptValues.Contains("application/json", StringComparer.OrdinalIgnoreCase);

        if (acceptsJson)
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
    /// <param name="threadId">The thread ID for the conversation.</param>
    /// <param name="agentResponse">The agent's response.</param>
    /// <returns>The HTTP response data containing the success response.</returns>
    private static async Task<HttpResponseData> CreateSuccessResponseAsync(
        HttpRequestData req,
        FunctionContext context,
        HttpStatusCode statusCode,
        string threadId,
        AgentRunResponse agentResponse)
    {
        HttpResponseData response = req.CreateResponse(statusCode);
        response.Headers.Add("x-ms-thread-id", threadId);

        bool acceptsJson = req.Headers.TryGetValues("Accept", out IEnumerable<string>? acceptValues) &&
            acceptValues.Contains("application/json", StringComparer.OrdinalIgnoreCase);

        if (acceptsJson)
        {
            AgentRunSuccessResponse successResponse = new((int)statusCode, threadId, agentResponse);
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
    /// <param name="threadId">The thread ID for the conversation.</param>
    /// <returns>The HTTP response data containing the accepted response.</returns>
    private static async Task<HttpResponseData> CreateAcceptedResponseAsync(
        HttpRequestData req,
        FunctionContext context,
        string threadId)
    {
        HttpResponseData response = req.CreateResponse(HttpStatusCode.Accepted);
        response.Headers.Add("x-ms-thread-id", threadId);

        bool acceptsJson = req.Headers.TryGetValues("Accept", out IEnumerable<string>? acceptValues) &&
            acceptValues.Contains("application/json", StringComparer.OrdinalIgnoreCase);

        if (acceptsJson)
        {
            AgentRunAcceptedResponse acceptedResponse = new((int)HttpStatusCode.Accepted, threadId);
            await response.WriteAsJsonAsync(acceptedResponse, context.CancellationToken);
        }
        else
        {
            response.Headers.Add("Content-Type", "text/plain");
            await response.WriteStringAsync("Request accepted.", context.CancellationToken);
        }

        return response;
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
    /// <param name="ThreadId">The optional thread ID to continue a conversation.</param>
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
    /// <param name="ThreadId">The thread ID for the conversation.</param>
    /// <param name="Response">The agent response.</param>
    private sealed record AgentRunSuccessResponse(
        [property: JsonPropertyName("status")] int Status,
        [property: JsonPropertyName("thread_id")] string ThreadId,
        [property: JsonPropertyName("response")] AgentRunResponse Response);

    /// <summary>
    /// Represents an accepted (fire-and-forget) agent run response.
    /// </summary>
    /// <param name="Status">The HTTP status code.</param>
    /// <param name="ThreadId">The thread ID for the conversation.</param>
    private sealed record AgentRunAcceptedResponse(
        [property: JsonPropertyName("status")] int Status,
        [property: JsonPropertyName("thread_id")] string ThreadId);

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
