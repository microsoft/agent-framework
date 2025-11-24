// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json;
using Microsoft.Agents.AI.DevUI.Entities;
using Microsoft.Agents.AI.Workflows;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.DevUI;

/// <summary>
/// Provides extension methods for mapping entity discovery and management endpoints to an <see cref="IEndpointRouteBuilder"/>.
/// </summary>
internal static class EntitiesApiExtensions
{
    /// <summary>
    /// Maps HTTP API endpoints for entity discovery and management.
    /// </summary>
    /// <param name="endpoints">The <see cref="IEndpointRouteBuilder"/> to add the routes to.</param>
    /// <returns>The <see cref="IEndpointRouteBuilder"/> for method chaining.</returns>
    /// <remarks>
    /// This extension method registers the following endpoints:
    /// <list type="bullet">
    /// <item><description>GET /v1/entities - List all registered entities (agents and workflows)</description></item>
    /// <item><description>GET /v1/entities/{entityId}/info - Get detailed information about a specific entity</description></item>
    /// </list>
    /// The endpoints are compatible with the Python DevUI frontend and automatically discover entities
    /// from the registered <see cref="AIAgent">agents</see> and <see cref="Workflow">workflows</see> in the dependency injection container.
    /// </remarks>
    public static IEndpointConventionBuilder MapEntities(this IEndpointRouteBuilder endpoints)
    {
        var registeredAIAgents = GetRegisteredEntities<AIAgent>(endpoints.ServiceProvider);
        var registeredWorkflows = GetRegisteredEntities<Workflow>(endpoints.ServiceProvider);

        var group = endpoints.MapGroup("/v1/entities")
            .WithTags("Entities");

        // List all entities
        group.MapGet("", (CancellationToken cancellationToken)
                => ListEntitiesAsync(registeredAIAgents, registeredWorkflows, cancellationToken))
            .WithName("ListEntities")
            .WithSummary("List all registered entities (agents and workflows)")
            .Produces<DiscoveryResponse>(StatusCodes.Status200OK, contentType: "application/json");

        // Get detailed entity information
        group.MapGet("{entityId}/info", (string entityId, string? type, CancellationToken cancellationToken)
                => GetEntityInfoAsync(entityId, type, registeredAIAgents, registeredWorkflows, cancellationToken))
            .WithName("GetEntityInfo")
            .WithSummary("Get detailed information about a specific entity")
            .Produces<EntityInfo>(StatusCodes.Status200OK, contentType: "application/json")
            .Produces(StatusCodes.Status404NotFound);

        return group;
    }

    private static async Task<IResult> ListEntitiesAsync(
        IEnumerable<AIAgent> agents,
        IEnumerable<Workflow> workflows,
        CancellationToken cancellationToken)
    {
        try
        {
            var entities = new Dictionary<string, EntityInfo>();

            // Discover agents
            foreach (var agentInfo in DiscoverAgents(agents, entityIdFilter: null))
            {
                entities[agentInfo.Id] = agentInfo;
            }

            // Discover workflows
            foreach (var workflowInfo in DiscoverWorkflows(workflows, entityIdFilter: null))
            {
                entities[workflowInfo.Id] = workflowInfo;
            }

            return Results.Json(new DiscoveryResponse([.. entities.Values.OrderBy(e => e.Id)]), EntitiesJsonContext.Default.DiscoveryResponse);
        }
        catch (Exception ex)
        {
            return Results.Problem(
                detail: ex.Message,
                statusCode: StatusCodes.Status500InternalServerError,
                title: "Error listing entities");
        }
    }

    private static async Task<IResult> GetEntityInfoAsync(
        string entityId,
        string? type,
        IEnumerable<AIAgent> agents,
        IEnumerable<Workflow> workflows,
        CancellationToken cancellationToken)
    {
        try
        {
            if (type is null || string.Equals(type, "workflow", StringComparison.OrdinalIgnoreCase))
            {
                foreach (var workflowInfo in DiscoverWorkflows(workflows, entityId))
                {
                    return Results.Json(workflowInfo, EntitiesJsonContext.Default.EntityInfo);
                }
            }

            if (type is null || string.Equals(type, "agent", StringComparison.OrdinalIgnoreCase))
            {
                foreach (var agentInfo in DiscoverAgents(agents, entityId))
                {
                    return Results.Json(agentInfo, EntitiesJsonContext.Default.EntityInfo);
                }
            }

            return Results.NotFound(new { error = new { message = $"Entity '{entityId}' not found.", type = "invalid_request_error" } });
        }
        catch (Exception ex)
        {
            return Results.Problem(
                detail: ex.Message,
                statusCode: StatusCodes.Status500InternalServerError,
                title: "Error getting entity info");
        }
    }

    private static IEnumerable<EntityInfo> DiscoverAgents(IEnumerable<AIAgent> agents, string? entityIdFilter)
    {
        foreach (var agent in agents)
        {
            // If filtering by entity ID, skip non-matching agents
            if (entityIdFilter is not null &&
                !string.Equals(agent.Name, entityIdFilter, StringComparison.OrdinalIgnoreCase) &&
                !string.Equals(agent.Id, entityIdFilter, StringComparison.OrdinalIgnoreCase))
            {
                continue;
            }

            yield return CreateAgentEntityInfo(agent);

            // If we found the entity we're looking for, we're done
            if (entityIdFilter is not null)
            {
                yield break;
            }
        }
    }

    private static IEnumerable<EntityInfo> DiscoverWorkflows(IEnumerable<Workflow> workflows, string? entityIdFilter)
    {
        foreach (var workflow in workflows)
        {
            var workflowId = workflow.Name ?? workflow.StartExecutorId;

            // If filtering by entity ID, skip non-matching workflows
            if (entityIdFilter is not null && !string.Equals(workflowId, entityIdFilter, StringComparison.OrdinalIgnoreCase))
            {
                continue;
            }

            yield return CreateWorkflowEntityInfo(workflow);

            // If we found the entity we're looking for, we're done
            if (entityIdFilter is not null)
            {
                yield break;
            }
        }
    }

    private static EntityInfo CreateAgentEntityInfo(AIAgent agent)
    {
        var entityId = agent.Name ?? agent.Id;

        // Extract tools and other metadata using GetService
        List<string> tools = [];
        var metadata = new Dictionary<string, JsonElement>();

        // Try to get ChatOptions from the agent which may contain tools
        if (agent.GetService<ChatOptions>() is { Tools: { Count: > 0 } agentTools })
        {
            tools = agentTools
                .Where(tool => !string.IsNullOrWhiteSpace(tool.Name))
                .Select(tool => tool.Name!)
                .Distinct()
                .ToList();
        }

        // Extract agent-specific fields (top-level properties for compatibility with Python)
        string? instructions = null;
        string? modelId = null;
        string? chatClientType = null;

        // Get instructions from ChatClientAgent
        if (agent is ChatClientAgent chatAgent && !string.IsNullOrWhiteSpace(chatAgent.Instructions))
        {
            instructions = chatAgent.Instructions;
        }

        // Get IChatClient to extract metadata
        IChatClient? chatClient = agent.GetService<IChatClient>();
        if (chatClient != null)
        {
            // Get chat client type
            chatClientType = chatClient.GetType().Name;

            // Get model ID from ChatClientMetadata
            if (chatClient.GetService<ChatClientMetadata>() is { } chatClientMetadata)
            {
                modelId = chatClientMetadata.DefaultModelId;

                // Add additional metadata for compatibility
                if (!string.IsNullOrWhiteSpace(chatClientMetadata.ProviderName))
                {
                    metadata["chat_client_provider"] = JsonSerializer.SerializeToElement(chatClientMetadata.ProviderName, EntitiesJsonContext.Default.String);
                }

                if (chatClientMetadata.ProviderUri is not null)
                {
                    metadata["provider_uri"] = JsonSerializer.SerializeToElement(chatClientMetadata.ProviderUri.ToString(), EntitiesJsonContext.Default.String);
                }
            }
        }

        // Add provider name from AIAgentMetadata if available
        if (agent.GetService<AIAgentMetadata>() is { } agentMetadata && !string.IsNullOrWhiteSpace(agentMetadata.ProviderName))
        {
            metadata["provider_name"] = JsonSerializer.SerializeToElement(agentMetadata.ProviderName, EntitiesJsonContext.Default.String);
        }

        // Add agent type information to metadata (in addition to chat_client_type)
        var agentTypeName = agent.GetType().Name;
        metadata["agent_type"] = JsonSerializer.SerializeToElement(agentTypeName, EntitiesJsonContext.Default.String);

        return new EntityInfo(
            Id: entityId,
            Type: "agent",
            Name: agent.DisplayName,
            Description: agent.Description,
            Framework: "agent_framework",
            Tools: tools,
            Metadata: metadata
        )
        {
            Source = "in_memory",
            Instructions = instructions,
            ModelId = modelId,
            ChatClientType = chatClientType,
            Executors = [],  // Agents have empty executors list (workflows use this field)
        };
    }

    private static EntityInfo CreateWorkflowEntityInfo(Workflow workflow)
    {
        // Extract executor IDs from the workflow structure
        var executorIds = new HashSet<string> { workflow.StartExecutorId };
        var reflectedEdges = workflow.ReflectEdges();
        foreach (var (sourceId, edgeSet) in reflectedEdges)
        {
            executorIds.Add(sourceId);
            foreach (var edge in edgeSet)
            {
                foreach (var sinkId in edge.Connection.SinkIds)
                {
                    executorIds.Add(sinkId);
                }
            }
        }

        // Create a default input schema (string type)
        var defaultInputSchema = new Dictionary<string, string>
        {
            ["type"] = "string"
        };

        var workflowId = workflow.Name ?? workflow.StartExecutorId;
        return new EntityInfo(
            Id: workflowId,
            Type: "workflow",
            Name: workflowId,
            Description: workflow.Description,
            Framework: "agent_framework",
            Tools: [],
            Metadata: []
        )
        {
            Source = "in_memory",
            Executors = [.. executorIds],  // Workflows use Executors instead of Tools
            WorkflowDump = JsonSerializer.SerializeToElement(
                workflow.ToDevUIDict(),
                EntitiesJsonContext.Default.DictionaryStringJsonElement),
            InputSchema = JsonSerializer.SerializeToElement(defaultInputSchema, EntitiesJsonContext.Default.DictionaryStringString),
            InputTypeName = "string",
            StartExecutorId = workflow.StartExecutorId
        };
    }

    private static IEnumerable<T> GetRegisteredEntities<T>(IServiceProvider serviceProvider)
    {
        var keyedEntities = serviceProvider.GetKeyedServices<T>(KeyedService.AnyKey);
        var defaultEntities = serviceProvider.GetServices<T>() ?? [];

        return keyedEntities
            .Concat(defaultEntities)
            .Where(entity => entity is not null);
    }
}
