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
    /// <returns>A dictionary with string keys and JsonElement values containing the workflow data.</returns>
    public static Dictionary<string, JsonElement> ToDevUIDict(this Workflow workflow)
    {
        var result = new Dictionary<string, JsonElement>
        {
            ["id"] = Serialize(workflow.Name ?? Guid.NewGuid().ToString(), EntitiesJsonContext.Default.String),
            ["start_executor_id"] = Serialize(workflow.StartExecutorId, EntitiesJsonContext.Default.String),
            ["max_iterations"] = Serialize(MaxIterationsDefault, EntitiesJsonContext.Default.Int32)
        };

        // Add optional fields
        if (!string.IsNullOrEmpty(workflow.Name))
        {
            result["name"] = Serialize(workflow.Name, EntitiesJsonContext.Default.String);
        }

        if (!string.IsNullOrEmpty(workflow.Description))
        {
            result["description"] = Serialize(workflow.Description, EntitiesJsonContext.Default.String);
        }

        // Convert executors to Python-compatible format
        result["executors"] = Serialize(
            ConvertExecutorsToDict(workflow),
            EntitiesJsonContext.Default.DictionaryStringDictionaryStringString);

        // Convert edges to edge_groups format
        result["edge_groups"] = Serialize(
            ConvertEdgesToEdgeGroups(workflow),
            EntitiesJsonContext.Default.ListDictionaryStringJsonElement);

        return result;
    }

    /// <summary>
    /// Converts workflow executors to a dictionary format compatible with Python
    /// </summary>
    private static Dictionary<string, Dictionary<string, string>> ConvertExecutorsToDict(Workflow workflow)
    {
        var executors = new Dictionary<string, Dictionary<string, string>>();

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
            executors[executorId] = new Dictionary<string, string>
            {
                ["id"] = executorId,
                ["type"] = "Executor"
            };
        }

        return executors;
    }

    /// <summary>
    /// Converts workflow edges to edge_groups format expected by the UI
    /// </summary>
    private static List<Dictionary<string, JsonElement>> ConvertEdgesToEdgeGroups(Workflow workflow)
    {
        var edgeGroups = new List<Dictionary<string, JsonElement>>();
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
                        ["id"] = Serialize($"edge_group_{edgeGroupId++}", EntitiesJsonContext.Default.String),
                        ["type"] = Serialize("SingleEdgeGroup", EntitiesJsonContext.Default.String),
                        ["edges"] = Serialize(edges, EntitiesJsonContext.Default.ListDictionaryStringString)
                    };

                    edgeGroups.Add(edgeGroup);
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
                        ["id"] = Serialize($"edge_group_{edgeGroupId++}", EntitiesJsonContext.Default.String),
                        ["type"] = Serialize("FanOutEdgeGroup", EntitiesJsonContext.Default.String),
                        ["edges"] = Serialize(edges, EntitiesJsonContext.Default.ListDictionaryStringString)
                    };

                    if (fanOutEdge.HasAssigner)
                    {
                        fanOutGroup["selection_func_name"] = Serialize("selector", EntitiesJsonContext.Default.String);
                    }

                    edgeGroups.Add(fanOutGroup);
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
                        ["id"] = Serialize($"edge_group_{edgeGroupId++}", EntitiesJsonContext.Default.String),
                        ["type"] = Serialize("FanInEdgeGroup", EntitiesJsonContext.Default.String),
                        ["edges"] = Serialize(edges, EntitiesJsonContext.Default.ListDictionaryStringString)
                    };

                    edgeGroups.Add(edgeGroup);
                }
            }
        }

        return edgeGroups;
    }

    private static JsonElement Serialize<T>(T value, JsonTypeInfo<T> typeInfo) => JsonSerializer.SerializeToElement(value, typeInfo);
}
