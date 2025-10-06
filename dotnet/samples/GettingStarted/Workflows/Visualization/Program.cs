// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI.Workflows;

namespace WorkflowVisualizationSample;

/// <summary>
/// Sample demonstrating workflow visualization using Mermaid and DOT (Graphviz) formats.
/// </summary>
/// <remarks>
/// This sample shows how to use the ToMermaidString() and ToDotString() extension methods
/// to generate visual representations of workflow graphs. The visualizations can be used
/// for documentation, debugging, and understanding complex workflow structures.
/// </remarks>
internal static class Program
{
    /// <summary>
    /// Entry point that generates and displays workflow visualizations in Mermaid and DOT formats.
    /// </summary>
    /// <param name="args">Command line arguments (not used).</param>
    private static void Main(string[] args)
    {
        // Step 1: Build the workflow you want to visualize
        Workflow workflow = WorkflowMapReduceSample.Program.BuildWorkflow();

        // Step 2: Generate and display workflow visualization
        Console.WriteLine("Generating workflow visualization...");

        // Mermaid
        Console.WriteLine("Mermaid string: \n=======");
        var mermaid = workflow.ToMermaidString();
        Console.WriteLine(mermaid);
        Console.WriteLine("=======");

        // DOT
        Console.WriteLine("DiGraph string: *** Tip: To export DOT as an image, install Graphviz and pipe the DOT output to 'dot -Tsvg', 'dot -Tpng', etc. *** \n=======");
        var dotString = workflow.ToDotString();
        Console.WriteLine(dotString);
        Console.WriteLine("=======");
    }
}
