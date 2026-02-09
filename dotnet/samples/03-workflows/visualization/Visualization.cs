// Copyright (c) Microsoft. All rights reserved.
// Description: Visualize workflow execution graphs in Mermaid and DOT formats.
// Docs: https://learn.microsoft.com/agent-framework/workflows/overview

using Microsoft.Agents.AI.Workflows;

namespace WorkflowSamples.Visualization;

// <visualization_workflow>
/// <summary>
/// Demonstrates workflow visualization using Mermaid and DOT (Graphviz) formats.
/// Generates visual representations of workflow graphs for documentation and debugging.
/// </summary>
internal static class Program
{
    private static void Main(string[] args)
    {
        // Build a sample workflow to visualize
        var fileRead = new Func<string, string>(s => s).BindAsExecutor("FileRead");
        var wordCount = new Func<string, string>(s => s).BindAsExecutor("WordCount");
        var paragraphCount = new Func<string, string>(s => s).BindAsExecutor("ParagraphCount");
        var aggregate = new Func<string, string>(s => s).BindAsExecutor("Aggregate");

        Workflow workflow = new WorkflowBuilder(fileRead)
            .AddFanOutEdge(fileRead, [wordCount, paragraphCount])
            .AddFanInEdge([wordCount, paragraphCount], aggregate)
            .WithOutputFrom(aggregate)
            .Build();

        // Generate Mermaid visualization
        Console.WriteLine("Mermaid string: \n=======");
        var mermaid = workflow.ToMermaidString();
        Console.WriteLine(mermaid);
        Console.WriteLine("=======");

        // Generate DOT (Graphviz) visualization
        Console.WriteLine("DiGraph string: \n=======");
        var dotString = workflow.ToDotString();
        Console.WriteLine(dotString);
        Console.WriteLine("=======");
    }
}
// </visualization_workflow>
