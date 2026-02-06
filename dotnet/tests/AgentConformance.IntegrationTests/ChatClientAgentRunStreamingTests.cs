// Copyright (c) Microsoft. All rights reserved.

using System;
using System.IO;
using System.Linq;
using System.Threading.Tasks;
using AgentConformance.IntegrationTests.Support;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;

namespace AgentConformance.IntegrationTests;

/// <summary>
/// Conformance tests that are specific to the <see cref="ChatClientAgent"/> in addition to those in <see cref="RunStreamingTests{TAgentFixture}"/>.
/// </summary>
/// <typeparam name="TAgentFixture">The type of test fixture used by the concrete test implementation.</typeparam>
/// <param name="createAgentFixture">Function to create the test fixture with.</param>
public abstract class ChatClientAgentRunStreamingTests<TAgentFixture>(Func<TAgentFixture> createAgentFixture) : AgentTests<TAgentFixture>(createAgentFixture)
    where TAgentFixture : IChatClientAgentFixture
{
    [RetryFact(Constants.RetryCount, Constants.RetryDelay)]
    public virtual async Task RunWithInstructionsAndNoMessageReturnsExpectedResultAsync()
    {
        // Arrange
        var agent = await this.Fixture.CreateChatClientAgentAsync(instructions: "Always respond with 'Computer says no', even if there was no user input.");
        var session = await agent.CreateSessionAsync();
        await using var agentCleanup = new AgentCleanup(agent, this.Fixture);
        await using var sessionCleanup = new SessionCleanup(session, this.Fixture);

        // Act
        var responseUpdates = await agent.RunStreamingAsync(session).ToListAsync();

        // Assert
        var chatResponseText = string.Concat(responseUpdates.Select(x => x.Text));
        Assert.Contains("Computer says no", chatResponseText, StringComparison.OrdinalIgnoreCase);
    }

    [RetryFact(Constants.RetryCount, Constants.RetryDelay)]
    public virtual async Task RunWithFunctionsInvokesFunctionsAndReturnsExpectedResultsAsync()
    {
        // Arrange
        var questionsAndAnswers = new[]
        {
            (Question: "Hello", ExpectedAnswer: string.Empty),
            (Question: "What is the special soup?", ExpectedAnswer: "Clam Chowder"),
            (Question: "What is the special drink?", ExpectedAnswer: "Chai Tea"),
            (Question: "What is the special salad?", ExpectedAnswer: "Cobb Salad"),
            (Question: "Thank you", ExpectedAnswer: string.Empty)
        };

        var agent = await this.Fixture.CreateChatClientAgentAsync(
            aiTools:
            [
                AIFunctionFactory.Create(MenuPlugin.GetSpecials),
                AIFunctionFactory.Create(MenuPlugin.GetItemPrice)
            ]);
        var session = await agent.CreateSessionAsync();

        foreach (var questionAndAnswer in questionsAndAnswers)
        {
            // Act
            var responseUpdates = await agent.RunStreamingAsync(
                new ChatMessage(ChatRole.User, questionAndAnswer.Question),
                session).ToListAsync();

            // Assert
            var chatResponseText = string.Concat(responseUpdates.Select(x => x.Text));
            Assert.Contains(questionAndAnswer.ExpectedAnswer, chatResponseText, StringComparison.OrdinalIgnoreCase);
        }
    }

    [RetryFact(Constants.RetryCount, Constants.RetryDelay)]
    public virtual async Task RunWithImageContentWorksAsync()
    {
        const string AgentInstructions = "You are a helpful agent that can analyze images";
        const string AgentName = "VisionAgent";

        var agent = await this.Fixture.CreateChatClientAgentAsync(name: AgentName, instructions: AgentInstructions);
        try
        {
            ChatMessage message = new(ChatRole.User, [
                new TextContent("What do you see in this image?"),
                new DataContent(File.ReadAllBytes(Path.Combine("shared", "assets", "walkway.jpg")), "image/jpeg")
            ]);

            var thread = agent.GetNewThread();
            var response = (await agent.RunStreamingAsync(message, thread).ToListAsync()).ToAgentRunResponse();

            var isImageDescriptionFoundResponse = await agent.RunAsync($"Respond with Yes or No:\n Does text below looks like the description of an image?\n {response.Text}");
            Assert.Contains("Yes", isImageDescriptionFoundResponse.ToString(), StringComparison.OrdinalIgnoreCase);
        }
        finally
        {
            await this.Fixture.DeleteAgentAsync(agent);
        }
    }
}
