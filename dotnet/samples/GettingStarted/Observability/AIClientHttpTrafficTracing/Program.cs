// Copyright (c) Microsoft. All rights reserved.

// This sample shows how to enable **HTTP request/response logging** for LLM calls (including request/response bodies) for any `AIClient`.

using System.ClientModel.Primitives;
using Azure.AI.OpenAI;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Logging;

string endpoint = Environment.GetEnvironmentVariable("AZURE_OPENAI_ENDPOINT") ?? throw new InvalidOperationException("AZURE_OPENAI_ENDPOINT environment variable is not set.");
string deploymentName = Environment.GetEnvironmentVariable("AZURE_OPENAI_DEPLOYMENT_NAME") ?? "gpt-4o-mini";

ServiceCollection services = new();
services.AddLogging(loggingBuilder =>
{
    loggingBuilder.AddConsole();
    loggingBuilder.AddFilter("System.ClientModel.Primitives.MessageLoggingPolicy", LogLevel.Debug);  // For Request and Response body logging we need to set Debug level
    /* If used in ASP.NET Core, with appsettings then this can be configured in appsettings.json as:
    {
      "Logging": {
        "LogLevel": {
          "Default": "Information",
          "Microsoft.AspNetCore": "Warning",
          "System.ClientModel.Primitives.MessageLoggingPolicy": "Debug"
        }
      }
    }
     */
});

services.AddChatClient(provider =>
{
    var clientLoggingOptions = new ClientLoggingOptions
    {
        EnableLogging = true, // Enable logging overall
        EnableMessageContentLogging = true, // Enable request and response body logging
        MessageContentSizeLimit = 5000, // Limit size of logged content. If Null or Not set, then default value will be 4 * 1024 characters
        EnableMessageLogging = true, // Logging the Request and Response Url and Header information. If Null or Not set, then default value will be true
        LoggerFactory = provider.GetRequiredService<ILoggerFactory>()
    };
    // WARNING: Do NOT log sensitive headers such as "Authorization" in production or shared environments.
    // By default, sensitive headers are REDACTED. The following example shows how to override this behavior
    // for controlled, non-production testing only.
    clientLoggingOptions.AllowedHeaderNames.Add("Authorization");

    /* Switch to OpenAI Compatible SDK using below code
    var clientOptions = new OpenAIClientOptions()
    {
        Endpoint = new Uri("https://endpoint"),
        ClientLoggingOptions = clientLoggingOptions
    };
    new OpenAIClient(new ApiKeyCredential("<apiKey/accessKey>"), clientOptions)
    .GetChatClient("modelName")
    .AsIChatClient();
    */

    return new AzureOpenAIClient(new Uri(endpoint), new AzureCliCredential(), new AzureOpenAIClientOptions() // Use OpenAIClientOptions of OpenAIClient, similar options for other clients
    {
        ClientLoggingOptions = clientLoggingOptions
    })
    .GetChatClient(deploymentName)
    .AsIChatClient();
});

ServiceProvider serviceProvider = services.BuildServiceProvider();

IChatClient chatClient = serviceProvider.GetRequiredService<IChatClient>();
ChatClientAgent pirateAssistant = chatClient.CreateAIAgent("You are a pirate assistant. Answer questions in short pirate speak.");

string userInput = "Who are you?";
Console.WriteLine($"You: {userInput}\n");
AgentRunResponse response = await pirateAssistant.RunAsync(userInput);
Console.WriteLine($"\nPirate Assistant: {response}");

/*await foreach (var item in pirateAssistant.RunStreamingAsync(userInput)) // For Streaming responses (RunStreamingAsync), there will be multiple log entries
{
    Console.Write(item);
}*/
