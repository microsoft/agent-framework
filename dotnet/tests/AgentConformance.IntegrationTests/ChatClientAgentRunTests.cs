﻿// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Threading.Tasks;
using AgentConformance.IntegrationTests.Support;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.AI.Agents;

namespace AgentConformance.IntegrationTests;

/// <summary>
/// Conformance tests that are specific to the <see cref="ChatClientAgent"/> in addition to those in <see cref="RunTests{TAgentFixture}"/>.
/// </summary>
/// <typeparam name="TAgentFixture">The type of test fixture used by the concrete test implementation.</typeparam>
/// <param name="createAgentFixture">Function to create the test fixture with.</param>
public abstract class ChatClientAgentRunTests<TAgentFixture>(Func<TAgentFixture> createAgentFixture) : AgentTests<TAgentFixture>(createAgentFixture)
    where TAgentFixture : IChatClientAgentFixture
{
    [RetryFact(Constants.RetryCount, Constants.RetryDelay)]
    public virtual async Task RunWithInstructionsAndNoMessageReturnsExpectedResultAsync()
    {
        // Arrange
        var agent = await this.Fixture.CreateChatClientAgentAsync(instructions: "Always respond with 'Computer says no', even if there was no user input.");
        var thread = agent.GetNewThread();
        await using var agentCleanup = new AgentCleanup(agent, this.Fixture);
        await using var threadCleanup = new ThreadCleanup(thread, this.Fixture);

        // Act
        var chatResponse = await agent.RunAsync(thread);

        // Assert
        Assert.NotNull(chatResponse);
        Assert.Single(chatResponse.Messages);
        Assert.Contains("Computer says no", chatResponse.Text, StringComparison.OrdinalIgnoreCase);
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
        var thread = agent.GetNewThread();

        foreach (var questionAndAnswer in questionsAndAnswers)
        {
            // Act
            var result = await agent.RunAsync(
                new ChatMessage(ChatRole.User, questionAndAnswer.Question),
                thread);

            // Assert
            Assert.NotNull(result);
            Assert.Contains(questionAndAnswer.ExpectedAnswer, result.Text);
        }
    }
}
