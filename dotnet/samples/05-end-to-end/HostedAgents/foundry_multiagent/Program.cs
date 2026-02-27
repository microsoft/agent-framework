// Copyright (c) Microsoft. All rights reserved.

using Azure.AI.Agents.Persistent;
using Azure.AI.AgentServer.AgentFramework.Extensions;
using Azure.Core;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.Workflows;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.Configuration;
using OpenTelemetry;
using OpenTelemetry.Resources;
using OpenTelemetry.Trace;

namespace dotnetmultiagent;

internal static class Program
{
    private static TracerProvider? s_tracerProvider;

    private static async Task Main(string[] args)
    {
        try
        {
            // Enable OpenTelemetry tracing for visualization
            ConfigureObservability();

            await RunAsync().ConfigureAwait(false);
        }
        catch (Exception e)
        {
            Console.WriteLine($"Critical error: {e}");
        }
    }

    private static async ValueTask RunAsync()
    {
        // Build configuration
        var configuration = new ConfigurationBuilder()
            .SetBasePath(Directory.GetCurrentDirectory())
            .AddJsonFile("appsettings.Development.json", optional: true)
            .AddEnvironmentVariables()
            .Build();

        var endpoint =
            configuration["PROJECT_ENDPOINT"]
            ?? throw new InvalidOperationException(
                "PROJECT_ENDPOINT is required. Set it in appsettings.Development.json for local development or as PROJECT_ENDPOINT environment variable for production");
        var deployment =
            configuration["MODEL_DEPLOYMENT_NAME"]
            ?? throw new InvalidOperationException(
                "MODEL_DEPLOYMENT_NAME is required. Set it in appsettings.Development.json for local development or as MODEL_DEPLOYMENT_NAME environment variable for containers");

        Console.WriteLine($"Using Azure AI endpoint: {endpoint}");
        Console.WriteLine($"Using model deployment: {deployment}");

        // Create credential - use ManagedIdentityCredential if MSI_ENDPOINT exists, otherwise DefaultAzureCredential
        TokenCredential credential = string.IsNullOrEmpty(Environment.GetEnvironmentVariable("MSI_ENDPOINT"))
            ? new DefaultAzureCredential()
            : new ManagedIdentityCredential();

        // Create separate PersistentAgentsClient for each agent
        var writerClient = new PersistentAgentsClient(endpoint, credential);
        var reviewerClient = new PersistentAgentsClient(endpoint, credential);

        (ChatClientAgent agent, string id)? writer = null;
        (ChatClientAgent agent, string id)? reviewer = null;

        try
        {
            // Create Foundry agents with separate clients
            writer = await CreateAgentAsync(
                writerClient,
                deployment,
                "Writer",
                "You are an excellent content writer. You create new content and edit contents based on the feedback."
            );
            reviewer = await CreateAgentAsync(
                reviewerClient,
                deployment,
                "Reviewer",
                "You are an excellent content reviewer. Provide actionable feedback to the writer about the provided content. Provide the feedback in the most concise manner possible."
            );
            Console.WriteLine();

            var workflow = new WorkflowBuilder(writer.Value.agent)
                .AddEdge(writer.Value.agent, reviewer.Value.agent)
                .WithOutputFrom(reviewer.Value.agent)
                .Build();

            Console.WriteLine("Starting Writer-Reviewer Workflow Agent Server on http://localhost:8088");
            await workflow.AsAgent().RunAIAgentAsync();
        }
        catch (Exception ex)
        {
            Console.WriteLine($"Error running workflow: {ex.Message}");
            throw;
        }
        finally
        {
            // Clean up all resources
            await CleanupAsync(writerClient, writer?.id);
            await CleanupAsync(reviewerClient, reviewer?.id);

            if (credential is IDisposable disposable)
            {
                disposable.Dispose();
            }
        }
    }

    private static async Task<(ChatClientAgent agent, string id)> CreateAgentAsync(
        PersistentAgentsClient client,
        string model,
        string name,
        string instructions)
    {
        var agentMetadata = await client.Administration.CreateAgentAsync(
            model: model,
            name: name,
            instructions: instructions
        );

        var chatClient = client.AsIChatClient(agentMetadata.Value.Id);
        return (new ChatClientAgent(chatClient), agentMetadata.Value.Id);
    }

    private static async Task CleanupAsync(PersistentAgentsClient client, string? agentId)
    {
        if (string.IsNullOrEmpty(agentId))
        {
            return;
        }

        try
        {
            await client.Administration.DeleteAgentAsync(agentId);
        }
        catch (Exception e)
        {
            Console.WriteLine($"Cleanup failed for agent {agentId}: {e.Message}");
        }
    }

    private static void ConfigureObservability()
    {
        var otlpEndpoint =
            Environment.GetEnvironmentVariable("OTLP_ENDPOINT") ?? "http://localhost:4319";

        var resourceBuilder = ResourceBuilder.CreateDefault()
            .AddService("WorkflowSample");

        s_tracerProvider = Sdk.CreateTracerProviderBuilder()
            .SetResourceBuilder(resourceBuilder)
            .AddSource("Microsoft.Agents.AI.*") // All agent framework sources
            .SetSampler(new AlwaysOnSampler()) // Ensure all traces are sampled
            .AddOtlpExporter(options =>
            {
                options.Endpoint = new Uri(otlpEndpoint);
                options.Protocol = OpenTelemetry.Exporter.OtlpExportProtocol.Grpc;
            })
            .Build();

        Console.WriteLine($"OpenTelemetry configured. OTLP endpoint: {otlpEndpoint}");
    }
}
