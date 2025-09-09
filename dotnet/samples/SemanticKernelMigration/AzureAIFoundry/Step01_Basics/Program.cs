// Copyright (c) Microsoft. All rights reserved.

using Azure.AI.Agents.Persistent;
using Azure.Core.Pipeline;
using Azure.Identity;
using Microsoft.Extensions.AI.Agents;
using Microsoft.SemanticKernel;
using Microsoft.SemanticKernel.Agents.AzureAI;

#pragma warning disable SKEXP0110 // Type is for evaluation purposes only and is subject to change or removal in future updates. Suppress this diagnostic to proceed.
#pragma warning disable CS8321 

var azureEndpoint = Environment.GetEnvironmentVariable("AZURE_FOUNDRY_PROJECT_ENDPOINT") ?? throw new InvalidOperationException("AZURE_FOUNDRY_PROJECT_ENDPOINT is not set.");
var deploymentName = System.Environment.GetEnvironmentVariable("AZURE_FOUNDRY_PROJECT_DEPLOYMENT_NAME") ?? "gpt-4o";
var userInput = "Tell me a joke about a pirate.";

Console.WriteLine($"User Input: {userInput}");

//await SKAgent();
await AFAgent();

async Task SKAgent()
{
    Console.WriteLine("\n=== SK Agent ===\n");

    var azureAgentClient = AzureAIAgent.CreateAgentsClient(azureEndpoint, new AzureCliCredential());

    PersistentAgent definition = await azureAgentClient.Administration.CreateAgentAsync(
        deploymentName,
        name: "GenerateStory",
        instructions: "You are good at telling jokes.");

    AzureAIAgent agent = new(definition, azureAgentClient);

    var thread = new AzureAIAgentThread(azureAgentClient);

    AzureAIAgentInvokeOptions options = new() { MaxPromptTokens = 1000 };
    var result = await agent.InvokeAsync(userInput, thread, options).FirstAsync();
    Console.WriteLine(result.Message);

    Console.WriteLine("---");
    await foreach (StreamingChatMessageContent update in agent.InvokeStreamingAsync(userInput, thread))
    {
        Console.Write(update);
    }

    // Clean up
    await thread.DeleteAsync();
    await azureAgentClient.Administration.DeleteAgentAsync(agent.Id);
}

async Task AFAgent()
{
    Console.WriteLine("\n=== AF Agent ===\n");

    using var myHandler = new MyHttpHandler();
#pragma warning disable CA5399
    using var httpClient = new HttpClient(myHandler);
#pragma warning restore CA5399
    var azureAgentClient = new PersistentAgentsClient(azureEndpoint, new AzureCliCredential(), new() { Transport = new HttpClientTransport(httpClient) });

    var agent = await azureAgentClient.CreateAIAgentAsync(
        deploymentName,
        name: "GenerateStory",
        instructions: "You are good at telling jokes.");

    var thread = agent.GetNewThread();
    var agentOptions = new ChatClientAgentRunOptions(new() { MaxOutputTokens = 1000 });

    var result = await agent.RunAsync(userInput, thread, agentOptions);
    Console.WriteLine(result);

    Console.WriteLine("---");
    await foreach (var update in agent.RunStreamingAsync(userInput, thread, agentOptions))
    {
        Console.Write(update);
    }

    // Clean up
    await azureAgentClient.Threads.DeleteThreadAsync(thread.ConversationId);
    await azureAgentClient.Administration.DeleteAgentAsync(agent.Id);
}

internal sealed class MyHttpHandler : HttpClientHandler
{
    protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
    {
        foreach (var header in request.Headers)
        {
            switch (header.Key.ToUpperInvariant())
            {
                case "AGENT-FRAMEWORK-VERSION":
                case "USER-AGENT":
                    Console.WriteLine($"{header.Key}: {string.Join('/', header.Value)}");
                    break;
            }
        }

        return base.SendAsync(request, cancellationToken);
    }
}
