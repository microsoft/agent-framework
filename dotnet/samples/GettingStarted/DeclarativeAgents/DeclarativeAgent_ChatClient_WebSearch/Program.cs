// Copyright (c) Microsoft. All rights reserved.

// This sample shows how to create and use a simple AI agent with Azure OpenAI as the backend.

using System;
using Microsoft.Agents.Declarative;
using Microsoft.Extensions.AI;
using OpenAI;

var apiKey = Environment.GetEnvironmentVariable("OPENAI_APIKEY") ?? throw new InvalidOperationException("OPENAI_APIKEY is not set.");
var model = Environment.GetEnvironmentVariable("OPENAI_MODEL") ?? "gpt-5";

// Create the chat client
IChatClient chatClient = new OpenAIClient(apiKey)
     .GetOpenAIResponseClient(model)
     .AsIChatClient();

// Define the agent using a YAML definition.
var text =
    """
    kind: GptComponentMetadata
    type: chat_client_agent
    name: NewsAgent
    description: News Agent
    instructions: You search the web to provide news articles.
    tools:
      - type: web_search
    """;

// Create the agent from the YAML definition.
var agentFactory = new ChatClientAgentFactory();
var agent = await agentFactory.CreateFromYamlAsync(text, new() { ChatClient = chatClient });

// Invoke the agent and output the text result.
Console.WriteLine(await agent!.RunAsync("what was a positive news story from today?"));
