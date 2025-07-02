// Copyright (c) Microsoft. All rights reserved.

using GenerativeAI.Microsoft;
using Microsoft.Agents;
using Microsoft.Shared.Samples;

namespace GettingStarted;

public class AgentDemo_Gemini(ITestOutputHelper output) : AgentSample(output)
{
    [Fact]
    public async Task Gemini_Run()
    {
        // Get a chat client.
        using GenerativeAIChatClient chatClient = new(TestConfiguration.GoogleAI.ApiKey, TestConfiguration.GoogleAI.Gemini.ModelId);

        // Create the agent.
        Agent agent = new ChatClientAgent(chatClient, new() { Name = "Joker", Instructions = "You are good at telling jokes." });

        // Invoke the agent.
        var response = await agent.RunAsync("Tell me a joke about a pirate.");
        Console.WriteLine(response.Text);
    }

    [Fact]
    public async Task Gemini_RunWithThreadAsync()
    {
        using GenerativeAIChatClient chatClient = new(TestConfiguration.GoogleAI.ApiKey, TestConfiguration.GoogleAI.Gemini.ModelId);
        Agent agent = new ChatClientAgent(chatClient, new() { Name = "Joker", Instructions = "You are good at telling jokes." });

        // Create a thread for this agent.
        var thread = agent.GetNewThread();

        // Run with the thread.
        var response = await agent.RunAsync("Tell me a joke about a pirate.", thread);
        Console.WriteLine(response.Text);

        response = await agent.RunAsync("Now tell the same joke like a parrot.", thread);
        Console.WriteLine(response.Text);
    }
}
