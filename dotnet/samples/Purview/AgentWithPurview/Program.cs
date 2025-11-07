// Copyright (c) Microsoft. All rights reserved.

// This sample shows how to create and use a simple AI agent with Azure OpenAI Responses as the backend.

using Azure.AI.OpenAI;
using Azure.Core;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.Purview;
using Microsoft.Extensions.AI;

var endpoint = Environment.GetEnvironmentVariable("AZURE_OPENAI_ENDPOINT") ?? throw new InvalidOperationException("AZURE_OPENAI_ENDPOINT is not set.");
var deploymentName = Environment.GetEnvironmentVariable("AZURE_OPENAI_DEPLOYMENT_NAME") ?? "gpt-4o-mini";
var purviewClientAppId = Environment.GetEnvironmentVariable("PURVIEW_CLIENT_APP_ID") ?? throw new InvalidOperationException("PURVIEW_CLIENT_APP_ID is not set.");

// This will get a user token for an entra app configured to call the Purview API.
// Any TokenCredential with permissions to call the Purview API can be used here.
TokenCredential browserCredential = new InteractiveBrowserCredential(
    new InteractiveBrowserCredentialOptions
    {
        ClientId = purviewClientAppId
    });

IChatClient client = new AzureOpenAIClient(
    new Uri(endpoint),
    new AzureCliCredential())
    .GetOpenAIResponseClient(deploymentName)
    .AsIChatClient()
    .AsBuilder()
    .WithPurview(browserCredential, new PurviewSettings("Agent Framework Test App"))
    .Build();

using (client)
{
    Console.WriteLine("Enter a prompt to send to the client:");
    string? promptText = Console.ReadLine();

    if (!string.IsNullOrEmpty(promptText))
    {
        // Invoke the agent and output the text result.
        Console.WriteLine(await client.GetResponseAsync(promptText));
    }
}
