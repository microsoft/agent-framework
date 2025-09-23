// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Security.Cryptography;
using System.Text;
using System.Threading.Tasks;

namespace Microsoft.Agents.Workflows;

/// <summary>
/// Provides visualization utilities for workflows using Graphviz DOT format.
/// </summary>
public class WorkflowViz
{
    private readonly Workflow _workflow;

    /// <summary>
    /// Initializes a new instance of the <see cref="WorkflowViz"/> class.
    /// </summary>
    /// <param name="workflow">The workflow to visualize.</param>
    public WorkflowViz(Workflow workflow)
    {
        this._workflow = workflow ?? throw new ArgumentNullException(nameof(workflow));
    }

    /// <summary>
    /// Export the workflow as a DOT format digraph string.
    /// </summary>
    /// <returns>A string representation of the workflow in DOT format.</returns>
    public string ToDotString()
    {
        var lines = new List<string>
    {
        "digraph Workflow {",
        "  rankdir=TD;", // Top to bottom layout
        "  node [shape=box, style=filled, fillcolor=lightblue];",
        "  edge [color=black, arrowhead=vee];",
        ""
    };

        // Emit the top-level workflow nodes/edges
        this.EmitWorkflowDigraph(this._workflow, lines, "  ");

        // Emit sub-workflows hosted by WorkflowExecutor as nested clusters
        this.EmitSubWorkflowsDigraph(this._workflow, lines, "  ");

        lines.Add("}");
        return string.Join("\n", lines);
    }

    /// <summary>
    /// Export the workflow visualization to a file.
    /// </summary>
    /// <param name="format">The output format (svg, png, pdf, dot).</param>
    /// <param name="filename">Optional filename to save the output. If null, creates a temporary file.</param>
    /// <returns>The path to the saved file.</returns>
    public async Task<string> ExportAsync(string format = "svg", string? filename = null)
    {
        if (string.IsNullOrEmpty(format))
        {
            throw new ArgumentException("Format cannot be null or empty.", nameof(format));
        }

        var supportedFormats = new[] { "SVG", "PNG", "PDF", "DOT" };
        var upperFormat = format.ToUpperInvariant();
        if (!supportedFormats.Contains(upperFormat))
        {
            throw new ArgumentException($"Unsupported format: {format}. Supported formats: svg, png, pdf, dot", nameof(format));
        }

        var dotContent = this.ToDotString();

        if (format.Equals("dot", StringComparison.OrdinalIgnoreCase))
        {
            var dotFilename = filename ?? Path.GetTempFileName() + ".dot";
            File.WriteAllText(dotFilename, dotContent, Encoding.UTF8);
            return dotFilename;
        }

        // Use DotRenderer wrapper to render the graph. NOTE: GraphViz must be installed and available on the system.
        var outputFilename = filename ?? Path.GetTempFileName() + $".{format}";
        var outputFormat = format.ToUpperInvariant() switch
        {
            "SVG" => DotRenderer.OutputFormat.Svg,
            "PNG" => DotRenderer.OutputFormat.Png,
            "PDF" => DotRenderer.OutputFormat.Pdf,
            _ => throw new NotImplementedException(),
        };

        await DotRenderer.RenderToFileAsync(dotContent, outputFormat, outputFilename).ConfigureAwait(false);
        return outputFilename;
    }

    /// <summary>
    /// Convenience method to save as SVG.
    /// </summary>
    /// <param name="filename">The filename to save the SVG file.</param>
    /// <returns>The path to the saved SVG file.</returns>
    public Task<string> SaveSvgAsync(string filename) => this.ExportAsync("svg", filename);

    /// <summary>
    /// Convenience method to save as PNG.
    /// </summary>
    /// <param name="filename">The filename to save the PNG file.</param>
    /// <returns>The path to the saved PNG file.</returns>
    public Task<string> SavePngAsync(string filename) => this.ExportAsync("png", filename);

    /// <summary>
    /// Convenience method to save as PDF.
    /// </summary>
    /// <param name="filename">The filename to save the PDF file.</param>
    /// <returns>The path to the saved PDF file.</returns>
    public Task<string> SavePdfAsync(string filename) => this.ExportAsync("pdf", filename);

    #region Private Implementation

    private void EmitWorkflowDigraph(Workflow workflow, List<string> lines, string indent, string? ns = null)
    {
        string MapId(string id) => ns != null ? $"{ns}/{id}" : id;

        // Add start node
        var startExecutorId = workflow.StartExecutorId;
        lines.Add($"{indent}\"{MapId(startExecutorId)}\" [fillcolor=lightgreen, label=\"{startExecutorId}\\n(Start)\"];");

        // Add other executor nodes
        foreach (var executorId in workflow.Registrations.Keys)
        {
            if (executorId != startExecutorId)
            {
                lines.Add($"{indent}\"{MapId(executorId)}\" [label=\"{executorId}\"];");
            }
        }

        // Compute and emit fan-in nodes
        var fanInDescriptors = this.ComputeFanInDescriptors(workflow);
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
        foreach (var (src, target, isConditional) in this.ComputeNormalEdges(workflow))
        {
            var edgeAttr = isConditional ? " [style=dashed, label=\"conditional\"]" : "";
            lines.Add($"{indent}\"{MapId(src)}\" -> \"{MapId(target)}\"{edgeAttr};");
        }
    }

    private void EmitSubWorkflowsDigraph(Workflow workflow, List<string> lines, string indent)
    {
        foreach (var kvp in workflow.Registrations)
        {
            var execId = kvp.Key;
            var registration = kvp.Value;
            // Check if this is a WorkflowExecutor with a nested workflow
            if (this.TryGetNestedWorkflow(registration, out var nestedWorkflow))
            {
                var subgraphId = $"cluster_{this.ComputeShortHash(execId)}";
                lines.Add($"{indent}subgraph {subgraphId} {{");
                lines.Add($"{indent}  label=\"sub-workflow: {execId}\";");
                lines.Add($"{indent}  style=dashed;");

                // Emit the nested workflow inside this cluster using a namespace
                this.EmitWorkflowDigraph(nestedWorkflow, lines, $"{indent}  ", execId);

                // Recurse into deeper nested sub-workflows
                this.EmitSubWorkflowsDigraph(nestedWorkflow, lines, $"{indent}  ");

                lines.Add($"{indent}}}");
            }
        }
    }

    private List<(string NodeId, List<string> Sources, string Target)> ComputeFanInDescriptors(Workflow workflow)
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
                var digest = this.ComputeFanInDigest(target, sources);
                var nodeId = $"fan_in::{target}::{digest}";

                // Avoid duplicates - the same fan-in edge group might appear in multiple source executor lists
                if (seen.Add(nodeId))
                {
                    result.Add((nodeId, sources.OrderBy(x => x, StringComparer.Ordinal).ToList(), target));
                }
            }
        }

        return result;
    }

    private List<(string Source, string Target, bool IsConditional)> ComputeNormalEdges(Workflow workflow)
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

    private string ComputeFanInDigest(string target, List<string> sources)
    {
        var sortedSources = sources.OrderBy(x => x, StringComparer.Ordinal).ToList();
        var input = target + "|" + string.Join("|", sortedSources);
        using (var sha256 = SHA256.Create())
        {
            return this.ComputeShortHash(input);
        }
    }

    private string ComputeShortHash(string input)
    {
#if !NET
        using (var sha256 = SHA256.Create())
        {
            var hash = sha256.ComputeHash(Encoding.UTF8.GetBytes(input));
            return BitConverter.ToString(hash).Replace("-", "").Substring(0, 8).ToUpperInvariant();
        }
#else
        var hash = SHA256.HashData(Encoding.UTF8.GetBytes(input));
        return Convert.ToHexString(hash).Substring(0, 8).ToUpperInvariant();
#endif
    }

    private bool TryGetNestedWorkflow(ExecutorRegistration registration, out Workflow workflow)
    {
        workflow = null!;

        // This is a simplified check - in a real implementation, you would need to:
        // 1. Check if the registration contains a WorkflowExecutor
        // 2. Extract the nested workflow from it
        // For now, we'll return false as this requires more knowledge of the ExecutorRegistration structure

        // TODO: Implement proper WorkflowExecutor detection and workflow extraction
        return false;
    }

    #endregion
}
