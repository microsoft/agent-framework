// Copyright (c) Microsoft. All rights reserved.

// This sample shows how to create and use a simple AI agent with OpenAI Responses as the backend.

using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;
using OpenAI;
using OpenAI.Responses;

var apiKey = Environment.GetEnvironmentVariable("OPENAI_API_KEY") ?? throw new InvalidOperationException("OPENAI_API_KEY is not set.");
var model = Environment.GetEnvironmentVariable("OPENAI_CHAT_MODEL_NAME") ?? "gpt-4o-mini";

AIAgent agent = new OpenAIClient(
    apiKey)
     .GetResponsesClient()
     .AsAIAgent(
        new ChatClientAgentOptions()
        {
            Name = "Joker",
            ChatOptions = new ChatOptions()
            {
                ModelId = model,
                Instructions = "You are good at telling jokes."
            }
        });

// Invoke the agent and output the text result.
Console.WriteLine(await agent.RunAsync("Tell me a joke about a pirate."));
