// Copyright (c) Microsoft. All rights reserved.

using System.Net;
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
        // The session ID is an optional query string parameter.
        string? threadIdFromQuery = req.Query["threadId"];

        // If no session ID is provided, use a new one based on the function name and invocation ID.
        // This may be better than a random one because it can be correlated with the function invocation.
        // Specifying a session ID is how the caller correlates multiple calls to the same agent session.
        AgentSessionId sessionId = string.IsNullOrEmpty(threadIdFromQuery)
            ? new AgentSessionId(GetAgentName(context), context.InvocationId)
            : AgentSessionId.Parse(threadIdFromQuery);

        string? message = await req.ReadAsStringAsync();
        if (string.IsNullOrWhiteSpace(message))
        {
            HttpResponseData response = req.CreateResponse(HttpStatusCode.BadRequest);
            await response.WriteAsJsonAsync(
                new { error = "Run request cannot be empty." },
                context.CancellationToken);
            return response;
        }

        AIAgent agentProxy = client.AsDurableAgentProxy(context, GetAgentName(context));

        AgentRunResponse agentResponse = await agentProxy.RunAsync(
            message: new ChatMessage(ChatRole.User, message),
            thread: new DurableAgentThread(sessionId),
            options: null,
            cancellationToken: context.CancellationToken);

        HttpResponseData httpResponse = req.CreateResponse(HttpStatusCode.OK);
        httpResponse.Headers.Add("X-Agent-Thread", sessionId.ToString());

        // If the caller accepts JSON, return the entire response object as JSON.
        // TODO: Need to define a standard response schema for agent responses.
        //       https://github.com/Azure/durable-agent-framework/issues/113
        if (req.Headers.TryGetValues("Accept", out IEnumerable<string>? acceptValues) &&
            acceptValues.Contains("application/json", StringComparer.OrdinalIgnoreCase))
        {
            await httpResponse.WriteAsJsonAsync(
                new { response = agentResponse, threadId = sessionId },
                context.CancellationToken);
        }
        else
        {
            // The default is to return the response as text/plain.
            httpResponse.Headers.Add("Content-Type", "text/plain");
            await httpResponse.WriteStringAsync(agentResponse.Text, context.CancellationToken);
        }

        return httpResponse;
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
