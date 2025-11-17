// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using System.Linq;
using System.Security.Cryptography;
using System.Text;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.Workflows;

/// <summary>
/// Provides visualization utilities for workflows using Graphviz DOT format.
/// </summary>
public static class WorkflowVisualizer
{
    /// <summary>
    /// Export the workflow as a DOT format digraph string.
    /// </summary>
    /// <returns>A string representation of the workflow in DOT format.</returns>
    public static string ToDotString(this Workflow workflow)
    {
        Throw.IfNull(workflow);

        var lines = new List<string>
    {
        "digraph Workflow {",
        "  rankdir=TD;", // Top to bottom layout
        "  node [shape=box, style=filled, fillcolor=lightblue];",
        "  edge [color=black, arrowhead=vee];",
        ""
    };

        // Emit the top-level workflow nodes/edges
        EmitWorkflowDigraph(workflow, lines, "  ");

        // Emit sub-workflows hosted by WorkflowExecutor as nested clusters
        EmitSubWorkflowsDigraph(workflow, lines, "  ");

        lines.Add("}");
        return string.Join("\n", lines);
    }

    /// <summary>
    /// Converts the specified <see cref="Workflow"/> into a Mermaid.js diagram representation.
    /// </summary>
    /// <remarks>This method generates a textual representation of the workflow in the Mermaid.js format,
    /// which can be used to visualize workflows as diagrams. The output is formatted with indentation for
    /// readability.</remarks>
    /// <param name="workflow">The workflow to be converted into a Mermaid.js diagram. Cannot be null.</param>
    /// <returns>A string containing the Mermaid.js representation of the workflow.</returns>
    public static string ToMermaidString(this Workflow workflow)
    {
        List<string> lines = ["flowchart TD"];

        EmitWorkflowMermaid(workflow, lines, "  ");
        return string.Join("\n", lines);
    }

    #region Private Implementation

    private static void EmitWorkflowDigraph(Workflow workflow, List<string> lines, string indent, string? ns = null)
    {
        string MapId(string id) => ns != null ? $"{ns}/{id}" : id;

        // Add start node
        var startExecutorId = workflow.StartExecutorId;
        lines.Add($"{indent}\"{MapId(startExecutorId)}\" [fillcolor=lightgreen, label=\"{startExecutorId}\\n(Start)\"];");

        // Add other executor nodes
        foreach (var executorId in workflow.ExecutorBindings.Keys)
        {
            if (executorId != startExecutorId)
            {
                lines.Add($"{indent}\"{MapId(executorId)}\" [label=\"{executorId}\"];");
            }
        }

        // Compute and emit fan-in nodes
        var fanInDescriptors = ComputeFanInDescriptors(workflow);
        if (fanInDescriptors.Count > 0)
        {
            lines.Add("");
            foreach (var (nodeId, _, _) in fanInDescriptors)
            {
                lines.Add($"{indent}\"{MapId(nodeId)}\" [shape=ellipse, fillcolor=lightgoldenrod, label=\"fan-in\"];");
            }
        }

        // Emit fan-in edges
        foreach (var (nodeId, sources, target) in fanInDescriptors)
        {
            foreach (var src in sources)
            {
                lines.Add($"{indent}\"{MapId(src)}\" -> \"{MapId(nodeId)}\";");
            }
            lines.Add($"{indent}\"{MapId(nodeId)}\" -> \"{MapId(target)}\";");
        }

        // Emit normal edges
        foreach (var (src, target, isConditional) in ComputeNormalEdges(workflow))
        {
            var edgeAttr = isConditional ? " [style=dashed, label=\"conditional\"]" : "";
            lines.Add($"{indent}\"{MapId(src)}\" -> \"{MapId(target)}\"{edgeAttr};");
        }
    }

    private static void EmitSubWorkflowsDigraph(Workflow workflow, List<string> lines, string indent)
    {
        foreach (var kvp in workflow.ExecutorBindings)
        {
            var execId = kvp.Key;
            var registration = kvp.Value;
            // Check if this is a WorkflowExecutor with a nested workflow
            if (TryGetNestedWorkflow(registration, out var nestedWorkflow))
            {
                var subgraphId = $"cluster_{ComputeShortHash(execId)}";
                lines.Add($"{indent}subgraph {subgraphId} {{");
                lines.Add($"{indent}  label=\"sub-workflow: {execId}\";");
                lines.Add($"{indent}  style=dashed;");

                // Emit the nested workflow inside this cluster using a namespace
                EmitWorkflowDigraph(nestedWorkflow, lines, $"{indent}  ", execId);

                // Recurse into deeper nested sub-workflows
                EmitSubWorkflowsDigraph(nestedWorkflow, lines, $"{indent}  ");

                lines.Add($"{indent}}}");
            }
        }
    }

    private static void EmitWorkflowMermaid(Workflow workflow, List<string> lines, string indent, string? ns = null)
    {
        string sanitize(string input)
        {
            return input;
        }

        string MapId(string id) => ns != null ? $"{sanitize(ns)}/{sanitize(id)}" : id;

        // Add start node
        var startExecutorId = workflow.StartExecutorId;
        lines.Add($"{indent}{MapId(startExecutorId)}[\"{startExecutorId} (Start)\"];");

        // Add other executor nodes
        foreach (var executorId in workflow.ExecutorBindings.Keys)
        {
            if (executorId != startExecutorId)
            {
                lines.Add($"{indent}{MapId(executorId)}[\"{executorId}\"];");
            }
        }

        // Compute and emit fan-in nodes
        var fanInDescriptors = ComputeFanInDescriptors(workflow);
        if (fanInDescriptors.Count > 0)
        {
            lines.Add("");
            foreach (var (nodeId, _, _) in fanInDescriptors)
            {
                lines.Add($"{indent}{MapId(nodeId)}((fan-in))");
            }
        }

        // Emit fan-in edges
        foreach (var (nodeId, sources, target) in fanInDescriptors)
        {
            foreach (var src in sources)
            {
                lines.Add($"{indent}{MapId(src)} --> {MapId(nodeId)};");
            }
            lines.Add($"{indent}{MapId(nodeId)} --> {MapId(target)};");
        }

        // Emit normal edges
        foreach (var (src, target, isConditional) in ComputeNormalEdges(workflow))
        {
            if (isConditional)
            {
                lines.Add($"{indent}{MapId(src)} -. conditional .--> {MapId(target)};");
            }
            else
            {
                lines.Add($"{indent}{MapId(src)} --> {MapId(target)};");
            }
        }
    }

    private static List<(string NodeId, List<string> Sources, string Target)> ComputeFanInDescriptors(Workflow workflow)
    {
        var result = new List<(string, List<string>, string)>();
        var seen = new HashSet<string>();

        foreach (var edgeGroup in workflow.Edges.Values.SelectMany(x => x))
        {
            if (edgeGroup.Kind == EdgeKind.FanIn && edgeGroup.FanInEdgeData != null)
            {
                var fanInData = edgeGroup.FanInEdgeData;
                var target = fanInData.SinkId;
                var sources = fanInData.SourceIds.ToList();
                var digest = ComputeFanInDigest(target, sources);
                var nodeId = $"fan_in_{target}_{digest}";

                // Avoid duplicates - the same fan-in edge group might appear in multiple source executor lists
                if (seen.Add(nodeId))
                {
                    result.Add((nodeId, sources.OrderBy(x => x, StringComparer.Ordinal).ToList(), target));
                }
            }
        }

        return result;
    }

    private static List<(string Source, string Target, bool IsConditional)> ComputeNormalEdges(Workflow workflow)
    {
        var edges = new List<(string, string, bool)>();
        foreach (var edgeGroup in workflow.Edges.Values.SelectMany(x => x))
        {
            if (edgeGroup.Kind == EdgeKind.FanIn)
            {
                continue;
            }

            switch (edgeGroup.Kind)
            {
                case EdgeKind.Direct when edgeGroup.DirectEdgeData != null:
                    var directData = edgeGroup.DirectEdgeData;
                    var isConditional = directData.Condition != null;
                    edges.Add((directData.SourceId, directData.SinkId, isConditional));
                    break;

                case EdgeKind.FanOut when edgeGroup.FanOutEdgeData != null:
                    var fanOutData = edgeGroup.FanOutEdgeData;
                    foreach (var sinkId in fanOutData.SinkIds)
                    {
                        edges.Add((fanOutData.SourceId, sinkId, false));
                    }
                    break;
            }
        }

        return edges;
    }

    private static string ComputeFanInDigest(string target, List<string> sources)
    {
        var sortedSources = sources.OrderBy(x => x, StringComparer.Ordinal).ToList();
        var input = target + "|" + string.Join("|", sortedSources);
        return ComputeShortHash(input);
    }

    private static string ComputeShortHash(string input)
    {
#if !NET
        using var sha256 = SHA256.Create();
        var hash = sha256.ComputeHash(Encoding.UTF8.GetBytes(input));
        return BitConverter.ToString(hash).Replace("-", "").Substring(0, 8).ToUpperInvariant();
#else
        var hash = SHA256.HashData(Encoding.UTF8.GetBytes(input));
        return Convert.ToHexString(hash).Substring(0, 8);
#endif
    }

    private static bool TryGetNestedWorkflow(ExecutorBinding binding, [NotNullWhen(true)] out Workflow? workflow)
    {
        if (binding.RawValue is Workflow subWorkflow)
        {
            workflow = subWorkflow;
            return true;
        }

        workflow = null;
        return false;
    }

    #endregion
}
