// Copyright (c) Microsoft. All rights reserved.

using Azure.AI.Projects;
using Azure.AI.Projects.Agents;
using Azure.Identity;
using Microsoft.Agents.AI.Workflows.Declarative;
using Microsoft.Extensions.Configuration;
using Shared.Foundry;
using Shared.Workflows;

namespace Demo.Workflows.Declarative.InvokeHttpRequest;

/// <summary>
/// Demonstrates a workflow that uses HttpRequestAction to call a REST API
/// directly from the workflow.
/// </summary>
/// <remarks>
/// <para>
/// The HttpRequestAction allows workflows to issue HTTP requests and:
/// </para>
/// <list type="bullet">
/// <item>Fetch data from external REST endpoints</item>
/// <item>Store the parsed response in workflow variables</item>
/// <item>Add the response body to the conversation so an agent can answer
///       questions based on it</item>
/// </list>
/// <para>
/// This sample fetches public metadata for the dotnet/runtime repository from
/// the GitHub REST API (no authentication required) and uses a Foundry agent
/// to answer follow-up questions about it. Type "EXIT" to end the conversation.
/// </para>
/// <para>
/// See the README.md file in the parent folder (../README.md) for detailed
/// information about the configuration required to run this sample.
/// </para>
/// </remarks>
internal sealed class Program
{
    public static async Task Main(string[] args)
    {
        // Initialize configuration
        IConfiguration configuration = Application.InitializeConfig();
        Uri foundryEndpoint = new(configuration.GetValue(Application.Settings.FoundryEndpoint));

        // Ensure sample agent exists in Foundry. The agent has no tools - it answers
        // questions about the GitHub repository using only the JSON data that the
        // HttpRequestAction adds to the conversation.
        await CreateAgentAsync(foundryEndpoint, configuration);

        // Get input from command line or console
        string workflowInput = Application.GetInput(args);

        // The default HttpRequestHandler is sufficient for this sample because the
        // GitHub REST endpoint used here does not require authentication. For
        // authenticated endpoints, supply a custom Func<HttpRequestInfo, ..., HttpClient?>
        // to DefaultHttpRequestHandler so each request can be routed through a
        // pre-configured (cached) HttpClient with the appropriate credentials.
        await using DefaultHttpRequestHandler httpRequestHandler = new();

        // Create the workflow factory with the HTTP request handler
        WorkflowFactory workflowFactory = new("InvokeHttpRequest.yaml", foundryEndpoint)
        {
            HttpRequestHandler = httpRequestHandler
        };

        // Execute the workflow
        WorkflowRunner runner = new() { UseJsonCheckpoints = true };
        await runner.ExecuteAsync(workflowFactory.CreateWorkflow, workflowInput);
    }

    private static async Task CreateAgentAsync(Uri foundryEndpoint, IConfiguration configuration)
    {
        // WARNING: DefaultAzureCredential is convenient for development but requires careful consideration in production.
        AIProjectClient aiProjectClient = new(foundryEndpoint, new DefaultAzureCredential());

        await aiProjectClient.CreateAgentAsync(
            agentName: "GitHubRepoInfoAgent",
            agentDefinition: DefineAgent(configuration),
            agentDescription: "Answers questions about a GitHub repository using HTTP response data in the conversation");
    }

    private static DeclarativeAgentDefinition DefineAgent(IConfiguration configuration)
    {
        return new DeclarativeAgentDefinition(configuration.GetValue(Application.Settings.FoundryModel))
        {
            Instructions =
                """
                Answer the user's questions about the GitHub repository using only the
                JSON data already present in the conversation history.
                If the answer is not contained in the conversation, say so plainly
                rather than guessing. Be concise and helpful.
                """
        };
    }
}
