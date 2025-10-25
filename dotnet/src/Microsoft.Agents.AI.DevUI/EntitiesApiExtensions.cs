// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json;

using Microsoft.Agents.AI.DevUI.Entities;
using Microsoft.Agents.AI.Hosting;

namespace Microsoft.Agents.AI.DevUI;

/// <summary>
/// Provides extension methods for mapping entity discovery and management endpoints to an <see cref="IEndpointRouteBuilder"/>.
/// </summary>
public static class EntitiesApiExtensions
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

            // Discover agents from the agent catalog
            if (agentCatalog is not null)
            {
                await foreach (var agent in agentCatalog.GetAgentsAsync(cancellationToken).ConfigureAwait(false))
                {
                    if (agent.GetType().Name == "WorkflowHostAgent")
                    {
                        // HACK: ignore WorkflowHostAgent instances as they are just wrappers around workflows,
                        // and workflows are handled below.
                        continue;
                    }

                    entities.Add(new EntityInfo(
                        Id: agent.Name ?? agent.Id,
                        Type: "agent",
                        Name: agent.Name ?? agent.Id,
                        Description: agent.Description,
                        Framework: "agent-framework",
                        Tools: null,
                        Metadata: []
                    )
                    {
                        Source = "in_memory"
                    });
                }
            }

            // Discover workflows from the workflow catalog
            if (workflowCatalog is not null)
            {
                await foreach (var workflow in workflowCatalog.GetWorkflowsAsync(cancellationToken).ConfigureAwait(false))
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

                    entities.Add(new EntityInfo(
                        Id: workflow.Name ?? workflow.StartExecutorId,
                        Type: "workflow",
                        Name: workflow.Name ?? workflow.StartExecutorId,
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
                    });
                }
            }

            return Results.Json(new DiscoveryResponse(entities), EntitiesJsonContext.Default.DiscoveryResponse);
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
        AgentCatalog? agentCatalog,
        WorkflowCatalog? workflowCatalog,
        CancellationToken cancellationToken)
    {
        try
        {
            // Try to find the entity among discovered agents
            if (agentCatalog is not null)
            {
                await foreach (var agent in agentCatalog.GetAgentsAsync(cancellationToken).ConfigureAwait(false))
                {
                    if (agent.GetType().Name == "WorkflowHostAgent")
                    {
                        // HACK: ignore WorkflowHostAgent instances as they are just wrappers around workflows,
                        // and workflows are handled below.
                        continue;
                    }

                    if (string.Equals(agent.Name, entityId, StringComparison.OrdinalIgnoreCase) ||
                        string.Equals(agent.Id, entityId, StringComparison.OrdinalIgnoreCase))
                    {
                        var entityInfo = new EntityInfo(
                            Id: agent.Name ?? agent.Id,
                            Type: "agent",
                            Name: agent.Name ?? agent.Id,
                            Description: agent.Description,
                            Framework: "agent-framework",
                            Tools: null,
                            Metadata: []
                        )
                        {
                            Source = "in_memory"
                        };

                        return Results.Json(entityInfo, EntitiesJsonContext.Default.EntityInfo);
                    }
                }
            }

            // Try to find the entity among discovered workflows
            if (workflowCatalog is not null)
            {
                await foreach (var workflow in workflowCatalog.GetWorkflowsAsync(cancellationToken).ConfigureAwait(false))
                {
                    var workflowId = workflow.Name ?? workflow.StartExecutorId;
                    if (string.Equals(workflowId, entityId, StringComparison.OrdinalIgnoreCase))
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

                        var entityInfo = new EntityInfo(
                            Id: workflowId,
                            Type: "workflow",
                            Name: workflow.Name ?? workflow.StartExecutorId,
                            Description: workflow.Description,
                            Framework: "agent-framework",
                            Tools: [.. executorIds],
                            Metadata: []
                        )
                        {
                            Source = "in_memory",
                            WorkflowDump = JsonSerializer.SerializeToElement(workflow.ToDevUIDict()),
                            InputSchema = JsonSerializer.SerializeToElement(defaultInputSchema),
                            InputTypeName = "Input",
                            StartExecutorId = workflow.StartExecutorId
                        };

                        return Results.Json(entityInfo, EntitiesJsonContext.Default.EntityInfo);
                    }
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
}
