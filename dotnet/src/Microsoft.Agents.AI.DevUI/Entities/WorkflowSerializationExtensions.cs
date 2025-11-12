// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json;
using System.Text.Json.Serialization.Metadata;
using Microsoft.Agents.AI.Workflows;
using Microsoft.Agents.AI.Workflows.Checkpointing;

namespace Microsoft.Agents.AI.DevUI.Entities;

/// <summary>
/// Extension methods for serializing workflows to DevUI-compatible format
/// </summary>
internal static class WorkflowSerializationExtensions
{
    // The frontend max iterations default value expected by the DevUI frontend
    private const int MaxIterationsDefault = 100;

    /// <summary>
    /// Converts a workflow to a dictionary representation compatible with DevUI frontend.
    /// This matches the Python workflow.to_dict() format expected by the UI.
    /// </summary>
    /// <param name="workflow">The workflow to convert.</param>
    /// <param name="options">JSON serialization options containing type info for source-generated serialization. If null, uses EntitiesJsonContext.Default.Options.</param>
    /// <returns>A dictionary with string keys and JsonElement values containing the workflow data.</returns>
    public static Dictionary<string, JsonElement> ToDevUIDict(this Workflow workflow, JsonSerializerOptions? options = null)
    {
        options ??= EntitiesJsonContext.Default.Options;

        var result = new Dictionary<string, JsonElement>
        {
            ["id"] = JsonSerializer.SerializeToElement(workflow.Name ?? Guid.NewGuid().ToString(), (JsonTypeInfo<string>)options.GetTypeInfo(typeof(string))),
            ["start_executor_id"] = JsonSerializer.SerializeToElement(workflow.StartExecutorId, (JsonTypeInfo<string>)options.GetTypeInfo(typeof(string))),
            ["max_iterations"] = JsonSerializer.SerializeToElement(MaxIterationsDefault, (JsonTypeInfo<int>)options.GetTypeInfo(typeof(int)))
        };

        // Add optional fields
        if (!string.IsNullOrEmpty(workflow.Name))
        {
            result["name"] = JsonSerializer.SerializeToElement(workflow.Name, (JsonTypeInfo<string>)options.GetTypeInfo(typeof(string)));
        }

        if (!string.IsNullOrEmpty(workflow.Description))
        {
            result["description"] = JsonSerializer.SerializeToElement(workflow.Description, (JsonTypeInfo<string>)options.GetTypeInfo(typeof(string)));
        }

        // Convert executors to Python-compatible format
        result["executors"] = JsonSerializer.SerializeToElement(ConvertExecutorsToDict(workflow, options), (JsonTypeInfo<Dictionary<string, JsonElement>>)options.GetTypeInfo(typeof(Dictionary<string, JsonElement>)));

        // Convert edges to edge_groups format
        result["edge_groups"] = JsonSerializer.SerializeToElement(ConvertEdgesToEdgeGroups(workflow, options), (JsonTypeInfo<List<JsonElement>>)options.GetTypeInfo(typeof(List<JsonElement>)));

        return result;
    }

    /// <summary>
    /// Converts workflow executors to a dictionary format compatible with Python
    /// </summary>
    private static Dictionary<string, JsonElement> ConvertExecutorsToDict(Workflow workflow, JsonSerializerOptions options)
    {
        var executors = new Dictionary<string, JsonElement>();

        // Extract executor IDs from edges and start executor
        // (Registrations is internal, so we infer executors from the graph structure)
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

        // Create executor entries (we can't access internal Registrations for type info)
        foreach (var executorId in executorIds)
        {
            var executorDict = new Dictionary<string, string>
            {
                ["id"] = executorId,
                ["type"] = "Executor"
            };

            executors[executorId] = JsonSerializer.SerializeToElement(
                executorDict,
                (JsonTypeInfo<Dictionary<string, string>>)options.GetTypeInfo(typeof(Dictionary<string, string>)));
        }

        return executors;
    }

    /// <summary>
    /// Converts workflow edges to edge_groups format expected by the UI
    /// </summary>
    private static List<JsonElement> ConvertEdgesToEdgeGroups(Workflow workflow, JsonSerializerOptions options)
    {
        var edgeGroups = new List<JsonElement>();
        var edgeGroupId = 0;

        // Get edges using the public ReflectEdges method
        var reflectedEdges = workflow.ReflectEdges();

        foreach (var (sourceId, edgeSet) in reflectedEdges)
        {
            foreach (var edgeInfo in edgeSet)
            {
                if (edgeInfo is DirectEdgeInfo directEdge)
                {
                    // Single edge group for direct edges
                    var edges = new List<Dictionary<string, string>>();

                    foreach (var source in directEdge.Connection.SourceIds)
                    {
                        foreach (var sink in directEdge.Connection.SinkIds)
                        {
                            var edge = new Dictionary<string, string>
                            {
                                ["source_id"] = source,
                                ["target_id"] = sink
                            };

                            // Add condition name if this is a conditional edge
                            if (directEdge.HasCondition)
                            {
                                edge["condition_name"] = "predicate";
                            }

                            edges.Add(edge);
                        }
                    }

                    var edgeGroup = new Dictionary<string, JsonElement>
                    {
                        ["id"] = JsonSerializer.SerializeToElement($"edge_group_{edgeGroupId++}", (JsonTypeInfo<string>)options.GetTypeInfo(typeof(string))),
                        ["type"] = JsonSerializer.SerializeToElement("SingleEdgeGroup", (JsonTypeInfo<string>)options.GetTypeInfo(typeof(string))),
                        ["edges"] = JsonSerializer.SerializeToElement(edges, options)
                    };

                    edgeGroups.Add(JsonSerializer.SerializeToElement(
                        edgeGroup,
                        (JsonTypeInfo<Dictionary<string, JsonElement>>)options.GetTypeInfo(typeof(Dictionary<string, JsonElement>))));
                }
                else if (edgeInfo is FanOutEdgeInfo fanOutEdge)
                {
                    // FanOut edge group
                    var edges = new List<Dictionary<string, string>>();

                    foreach (var source in fanOutEdge.Connection.SourceIds)
                    {
                        foreach (var sink in fanOutEdge.Connection.SinkIds)
                        {
                            edges.Add(new Dictionary<string, string>
                            {
                                ["source_id"] = source,
                                ["target_id"] = sink
                            });
                        }
                    }

                    var fanOutGroup = new Dictionary<string, JsonElement>
                    {
                        ["id"] = JsonSerializer.SerializeToElement($"edge_group_{edgeGroupId++}", (JsonTypeInfo<string>)options.GetTypeInfo(typeof(string))),
                        ["type"] = JsonSerializer.SerializeToElement("FanOutEdgeGroup", (JsonTypeInfo<string>)options.GetTypeInfo(typeof(string))),
                        ["edges"] = JsonSerializer.SerializeToElement(edges, options)
                    };

                    if (fanOutEdge.HasAssigner)
                    {
                        fanOutGroup["selection_func_name"] = JsonSerializer.SerializeToElement("selector", (JsonTypeInfo<string>)options.GetTypeInfo(typeof(string)));
                    }

                    edgeGroups.Add(JsonSerializer.SerializeToElement(
                        fanOutGroup,
                        (JsonTypeInfo<Dictionary<string, JsonElement>>)options.GetTypeInfo(typeof(Dictionary<string, JsonElement>))));
                }
                else if (edgeInfo is FanInEdgeInfo fanInEdge)
                {
                    // FanIn edge group
                    var edges = new List<Dictionary<string, string>>();

                    foreach (var source in fanInEdge.Connection.SourceIds)
                    {
                        foreach (var sink in fanInEdge.Connection.SinkIds)
                        {
                            edges.Add(new Dictionary<string, string>
                            {
                                ["source_id"] = source,
                                ["target_id"] = sink
                            });
                        }
                    }

                    var edgeGroup = new Dictionary<string, JsonElement>
                    {
                        ["id"] = JsonSerializer.SerializeToElement($"edge_group_{edgeGroupId++}", (JsonTypeInfo<string>)options.GetTypeInfo(typeof(string))),
                        ["type"] = JsonSerializer.SerializeToElement("FanInEdgeGroup", (JsonTypeInfo<string>)options.GetTypeInfo(typeof(string))),
                        ["edges"] = JsonSerializer.SerializeToElement(edges, options)
                    };

                    edgeGroups.Add(JsonSerializer.SerializeToElement(
                        edgeGroup,
                        (JsonTypeInfo<Dictionary<string, JsonElement>>)options.GetTypeInfo(typeof(Dictionary<string, JsonElement>))));
                }
            }
        }

        return edgeGroups;
    }
}
