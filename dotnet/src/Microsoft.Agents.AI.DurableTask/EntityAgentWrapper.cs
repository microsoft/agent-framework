// Copyright (c) Microsoft. All rights reserved.

using System.Runtime.CompilerServices;
using Microsoft.Agents.AI;
using Microsoft.DurableTask.Entities;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.DependencyInjection;

namespace Microsoft.Agents.AI.DurableTask;

internal sealed class EntityAgentWrapper(
    AIAgent innerAgent,
    TaskEntityContext entityContext,
    RunRequest runRequest,
    IServiceProvider? entityScopedServices = null) : DelegatingAIAgent(innerAgent)
{
    private readonly TaskEntityContext _entityContext = entityContext;
    private readonly RunRequest _runRequest = runRequest;
    private readonly IServiceProvider? _entityScopedServices = entityScopedServices;

    // The ID of the agent is always the entity ID.
    public override string Id => this._entityContext.Id.ToString();

    public override async Task<AgentRunResponse> RunAsync(
        IEnumerable<ChatMessage> messages,
        AgentThread? thread = null,
        AgentRunOptions? options = null,
        CancellationToken cancellationToken = default)
    {
        AgentRunResponse response = await base.RunAsync(
            messages,
            thread,
            this.GetAgentEntityRunOptions(options),
            cancellationToken);

        response.AgentId = this.Id;
        return response;
    }

    public override async IAsyncEnumerable<AgentRunResponseUpdate> RunStreamingAsync(
        IEnumerable<ChatMessage> messages,
        AgentThread? thread = null,
        AgentRunOptions? options = null,
        [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        await foreach (AgentRunResponseUpdate update in base.RunStreamingAsync(
            messages,
            thread,
            this.GetAgentEntityRunOptions(options),
            cancellationToken))
        {
            update.AgentId = this.Id;
            yield return update;
        }
    }

    // Override the GetService method to provide entity-scoped services.
    public override object? GetService(Type serviceType, object? serviceKey = null)
    {
        object? result = null;
        if (this._entityScopedServices is not null)
        {
            result = (serviceKey is not null && this._entityScopedServices is IKeyedServiceProvider keyedServiceProvider)
                ? keyedServiceProvider.GetKeyedService(serviceType, serviceKey)
                : this._entityScopedServices.GetService(serviceType);
        }

        return result ?? base.GetService(serviceType, serviceKey);
    }

    private AgentRunOptions GetAgentEntityRunOptions(AgentRunOptions? options = null)
    {
        // Copied/modified from FunctionInvocationDelegatingAgent.cs in microsoft/agent-framework.
        if (options is null || options.GetType() == typeof(AgentRunOptions))
        {
            options = new ChatClientAgentRunOptions();
        }

        if (options is not ChatClientAgentRunOptions chatAgentRunOptions)
        {
            throw new NotSupportedException($"Function Invocation Middleware is only supported without options or with {nameof(ChatClientAgentRunOptions)}.");
        }

        Func<IChatClient, IChatClient>? originalFactory = chatAgentRunOptions.ChatClientFactory;

        chatAgentRunOptions.ChatClientFactory = chatClient =>
        {
            ChatClientBuilder builder = chatClient.AsBuilder();
            if (originalFactory is not null)
            {
                builder.Use(originalFactory);
            }

            // Update the run options based on the run request.
            // NOTE: Function middleware can go here if needed in the future.
            return builder.ConfigureOptions(
                newOptions =>
                {
                    // Update the response format if requested by the caller.
                    if (this._runRequest.ResponseFormat is not null)
                    {
                        newOptions.ResponseFormat = this._runRequest.ResponseFormat;
                    }

                    // Update the tools if requested by the caller.
                    if (this._runRequest.EnableToolCalls)
                    {
                        IList<AITool>? tools = chatAgentRunOptions.ChatOptions?.Tools;
                        if (tools is not null && this._runRequest.EnableToolNames?.Count > 0)
                        {
                            // Filter tools to only include those with matching names
                            newOptions.Tools = [.. tools.Where(tool => this._runRequest.EnableToolNames.Contains(tool.Name))];
                        }
                    }
                    else
                    {
                        newOptions.Tools = null;
                    }
                })
                .Build();
        };

        return options;
    }
}
