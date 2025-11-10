// Copyright (c) Microsoft. All rights reserved.

using System.Runtime.CompilerServices;
using System.Text.Json;

using Microsoft.Agents.AI.DevUI.Entities;
using Microsoft.Agents.AI.Hosting;
using Microsoft.Agents.AI.Workflows;

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
    /// from the registered <see cref="AgentCatalog"/> and <see cref="WorkflowCatalog"/> services.
    /// </remarks>
    public static IEndpointConventionBuilder MapEntities(this IEndpointRouteBuilder endpoints)
    {
        var group = endpoints.MapGroup("/v1/entities")
            .WithTags("Entities");

        // List all entities
        group.MapGet("", ListEntitiesAsync)
            .WithName("ListEntities")
            .WithSummary("List all registered entities (agents and workflows)")
            .Produces<DiscoveryResponse>(StatusCodes.Status200OK, contentType: "application/json");

        // Get detailed entity information
        group.MapGet("{entityId}/info", GetEntityInfoAsync)
            .WithName("GetEntityInfo")
            .WithSummary("Get detailed information about a specific entity")
            .Produces<EntityInfo>(StatusCodes.Status200OK, contentType: "application/json")
            .Produces(StatusCodes.Status404NotFound);

        return group;
    }

    private static async Task<IResult> ListEntitiesAsync(
        AgentCatalog? agentCatalog,
        WorkflowCatalog? workflowCatalog,
        CancellationToken cancellationToken)
    {
        try
        {
            var entities = new List<EntityInfo>();

            // Discover agents
            await foreach (var agentInfo in DiscoverAgentsAsync(agentCatalog, entityIdFilter: null, cancellationToken).ConfigureAwait(false))
            {
                entities.Add(agentInfo);
            }

            // Discover workflows
            await foreach (var workflowInfo in DiscoverWorkflowsAsync(workflowCatalog, entityIdFilter: null, cancellationToken).ConfigureAwait(false))
            {
                entities.Add(workflowInfo);
            }

            return Results.Json(new DiscoveryResponse([.. entities]), EntitiesJsonContext.Default.DiscoveryResponse);
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
        AgentCatalog? agentCatalog,
        WorkflowCatalog? workflowCatalog,
        CancellationToken cancellationToken)
    {
        try
        {
            if (type is null || string.Equals(type, "agent", StringComparison.OrdinalIgnoreCase))
            {
                await foreach (var agentInfo in DiscoverAgentsAsync(agentCatalog, entityId, cancellationToken).ConfigureAwait(false))
                {
                    return Results.Json(agentInfo, EntitiesJsonContext.Default.EntityInfo);
                }
            }

            if (type is null || string.Equals(type, "workflow", StringComparison.OrdinalIgnoreCase))
            {
                await foreach (var workflowInfo in DiscoverWorkflowsAsync(workflowCatalog, entityId, cancellationToken).ConfigureAwait(false))
                {
                    return Results.Json(workflowInfo, EntitiesJsonContext.Default.EntityInfo);
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

    private static async IAsyncEnumerable<EntityInfo> DiscoverAgentsAsync(
        AgentCatalog? agentCatalog,
        string? entityIdFilter,
        [EnumeratorCancellation] CancellationToken cancellationToken)
    {
        if (agentCatalog is null)
        {
            yield break;
        }

        await foreach (var agent in agentCatalog.GetAgentsAsync(cancellationToken).ConfigureAwait(false))
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

    private static async IAsyncEnumerable<EntityInfo> DiscoverWorkflowsAsync(
        WorkflowCatalog? workflowCatalog,
        string? entityIdFilter,
        [EnumeratorCancellation] CancellationToken cancellationToken)
    {
        if (workflowCatalog is null)
        {
            yield break;
        }

        await foreach (var workflow in workflowCatalog.GetWorkflowsAsync(cancellationToken).ConfigureAwait(false))
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
        return new EntityInfo(
            Id: entityId,
            Type: "agent",
            Name: entityId,
            Description: agent.Description,
            Framework: "agent-framework",
            Tools: null,
            Metadata: []
        )
        {
            Source = "in_memory"
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
        var defaultInputSchema = new Dictionary<string, object>
        {
            ["type"] = "string"
        };

        var workflowId = workflow.Name ?? workflow.StartExecutorId;
        return new EntityInfo(
            Id: workflowId,
            Type: "workflow",
            Name: workflowId,
            Description: workflow.Description,
            Framework: "agent-framework",
            Tools: [.. executorIds],
            Metadata: []
        )
        {
            Source = "in_memory",
            WorkflowDump = JsonSerializer.SerializeToElement(workflow.ToDevUIDict()),
            InputSchema = JsonSerializer.SerializeToElement(defaultInputSchema),
            InputTypeName = "string",
            StartExecutorId = workflow.StartExecutorId
        };
    }
}
