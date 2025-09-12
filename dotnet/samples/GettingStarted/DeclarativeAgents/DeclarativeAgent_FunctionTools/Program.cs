// Copyright (c) Microsoft. All rights reserved.

// This sample shows how to create and use a simple AI agent with Azure OpenAI as the backend.

using System;
using System.ComponentModel;
using Azure.AI.OpenAI;
using Azure.Identity;
using Microsoft.Agents.Declarative;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.AI.Agents;

var endpoint = Environment.GetEnvironmentVariable("AZURE_OPENAI_ENDPOINT") ?? throw new InvalidOperationException("AZURE_OPENAI_ENDPOINT is not set.");
var deploymentName = Environment.GetEnvironmentVariable("AZURE_OPENAI_DEPLOYMENT_NAME") ?? "gpt-4o-mini";

// Create the chat client
IChatClient chatClient = new AzureOpenAIClient(
    new Uri(endpoint),
    new AzureCliCredential())
     .GetChatClient(deploymentName)
     .AsIChatClient();

[Description("Get the weather for a given location.")]
static string GetWeather([Description("The location to get the weather for.")] string location)
    => $"The weather in {location} is cloudy with a high of 15°C.";

// Define the agent using a YAML definition.
var text =
    """
    kind: GptComponentMetadata
    type: chat_client_agent
    name: WeatherAgent
    description: Weather Agent
    instructions: You provide weather information.
    tools:
      - name: GetWeather
        type: function
        description: Get the weather for a given location.
    """;

// Create the agent from the YAML definition.
var agentFactory = new ChatClientAgentFactory();
var agent = await agentFactory.CreateFromYamlAsync(text, new() { ChatClient = chatClient });

// Create run options with the function tool.
var chatOptions = new ChatOptions() { Tools = [AIFunctionFactory.Create(GetWeather)] };
var runOptions = new ChatClientAgentRunOptions(chatOptions);

// Invoke the agent and output the text result.
Console.WriteLine(await agent!.RunAsync(message: "What is the weather like in Amsterdam?", options: runOptions));
