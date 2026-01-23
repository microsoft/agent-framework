// Copyright (c) Microsoft. All rights reserved.

using Azure;
using Azure.AI.OpenAI;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.Workflows;
using OpenAI.Chat;

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
        // Get the Azure OpenAI endpoint and deployment name from environment variables.
        string endpoint = Environment.GetEnvironmentVariable("AZURE_OPENAI_ENDPOINT")
            ?? throw new InvalidOperationException("AZURE_OPENAI_ENDPOINT is not set.");
        string deploymentName = Environment.GetEnvironmentVariable("AZURE_OPENAI_DEPLOYMENT")
            ?? throw new InvalidOperationException("AZURE_OPENAI_DEPLOYMENT is not set.");

        // Use Azure Key Credential if provided, otherwise use Azure CLI Credential.
        string? azureOpenAiKey = System.Environment.GetEnvironmentVariable("AZURE_OPENAI_KEY");
        AzureOpenAIClient client = !string.IsNullOrEmpty(azureOpenAiKey)
            ? new AzureOpenAIClient(new Uri(endpoint), new AzureKeyCredential(azureOpenAiKey))
            : new AzureOpenAIClient(new Uri(endpoint), new AzureCliCredential());

        AIAgent physicist = client.GetChatClient(deploymentName).CreateAIAgent("You are an expert in physics. You answer questions from a physics perspective.", "Physicist");
        AIAgent chemist = client.GetChatClient(deploymentName).CreateAIAgent("You are an expert in chemistry. You answer questions from a chemistry perspective.", "Chemist");

        var startExecutor = new PrepareQuery();
        var aggregationExecutor = new ResultAggregator();

        var workflow = new WorkflowBuilder(startExecutor)
            .WithName("ExpertReview")
            .AddFanOutEdge(startExecutor, [physicist, chemist])
            .AddFanInEdge([physicist, chemist], aggregationExecutor)
            .Build();

        // Step 2: Generate and display workflow visualization
        Console.WriteLine("Generating workflow visualization...");

        // Mermaid
        Console.WriteLine("Mermaid string: \n=======");
        var mermaid = workflow.ToMermaidString();
        Console.WriteLine(mermaid);
        Console.WriteLine("=======");
    }
}

internal sealed class PrepareQuery() : Executor<string, string>("PrepareQuery")
{
    public override ValueTask<string> HandleAsync(string message, IWorkflowContext context, CancellationToken cancellationToken = default)
    {
        // do some initial parsing and validation of the message.
        // Return a polished version ith additional metadta.
        if (!message.StartsWith("Query for the agent:", StringComparison.OrdinalIgnoreCase))
        {
            message = "Query for the agent: " + message;
        }

        return ValueTask.FromResult(message);
    }
}

internal sealed class ResultAggregator() : Executor<string[], string>("ResultAggregator")
{
    public override ValueTask<string> HandleAsync(string[] message, IWorkflowContext context, CancellationToken cancellationToken = default)
    {
        // Aggregate all responses from parallel executors.
        string aggregatedResponse = string.Join("\n---\n", message);
        return ValueTask.FromResult($"Aggregated {message.Length} responses:\n{aggregatedResponse}");
    }
}
