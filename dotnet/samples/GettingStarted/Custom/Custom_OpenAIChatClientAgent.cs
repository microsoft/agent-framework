// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Extensions.Logging;
using Microsoft.Shared.Samples;
using OpenAI;
using OpenAI.Chat;

namespace Custom;

/// <summary>
/// End-to-end sample showing how to use a custom <see cref="OpenAIChatClientAgent"/>.
/// </summary>
public sealed class Custom_OpenAIChatClientAgent(ITestOutputHelper output) : AgentSample(output)
{
    /// <summary>
    /// This will create an instance of <see cref="MyOpenAIChatClientAgent"/> and run it.
    /// </summary>
    [Fact]
    public async Task RunCustomChatClientAgent()
    {
        var chatClient = new OpenAIClient(TestConfiguration.OpenAI.ApiKey).GetChatClient(TestConfiguration.OpenAI.ChatModelId);

        var agent = new MyOpenAIChatClientAgent(chatClient);

        var chatMessage = new UserChatMessage("Tell me a joke about a pirate.");
        var chatCompletion = await agent.RunAsync(chatMessage);

        Console.WriteLine(chatCompletion.Content.Last().Text);
    }
}

public class MyOpenAIChatClientAgent : OpenAIChatClientAgent
{
    private const string JokerName = "Joker";
    private const string JokerInstructions = "You are good at telling jokes.";

    public MyOpenAIChatClientAgent(ChatClient client, ILoggerFactory? loggerFactory = null) :
        base(client, instructions: JokerInstructions, name: JokerName, loggerFactory: loggerFactory)
    {
    }
}
