// Copyright (c) Microsoft. All rights reserved.

using System;
using Microsoft.Agents.AI.Workflows;

namespace WorkflowVisualizationSample;

internal static class Program
{
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
        Console.WriteLine("DiGraph string: \n=======");
        Console.Write("*** Tip: To export DOT as an image, install Graphviz and pipe the DOT output to 'dot -Tsvg', 'dot -Tpng', etc.");
        var dotString = workflow.ToDotString();
        Console.WriteLine(dotString);
        Console.WriteLine("=======");
    }
}
