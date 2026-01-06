// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading.Tasks;
using FluentAssertions;
using Microsoft.Agents.AI.Workflows.Specialized;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Workflows.UnitTests;

public class AIAgentHostExecutorTests
{
    private const string TestAgentId = nameof(TestAgentId);
    private const string TestAgentName = nameof(TestAgentName);

    private static readonly string[] s_messageStrings = [
        "",
        "Hello world!",
        "Lorem ipsum dolor sit amet, consectetur adipiscing elit.",
        "Quisque dignissim ante odio, at facilisis orci porta a. Duis mi augue, fringilla eu egestas a, pellentesque sed lacus."
    ];

    private static List<ChatMessage> TestMessages => TestReplayAgent.ToChatMessages(s_messageStrings);

    [Theory]
    [InlineData(null, null)]
    [InlineData(null, true)]
    [InlineData(null, false)]
    [InlineData(true, null)]
    [InlineData(true, true)]
    [InlineData(true, false)]
    [InlineData(false, null)]
    [InlineData(false, true)]
    [InlineData(false, false)]
    public async Task Test_AgentHostExecutor_EmitsStreamingUpdatesIFFConfiguredAsync(bool? executorSetting, bool? turnSetting)
    {
        // Arrange
        TestRunContext testContext = new();
        TestReplayAgent agent = new(TestMessages, TestAgentId, TestAgentName);
        AIAgentHostExecutor executor = new(agent, new() { EmitAgentRunUpdateEvents = executorSetting });
        testContext.ConfigureExecutor(executor);

        // Act
        await executor.TakeTurnAsync(new(turnSetting), testContext.BindWorkflowContext(executor.Id));

        // Assert
        // The rules are: TurnToken overrides Agent, if set. Default to false, if both unset.
        bool expectingEvents = turnSetting ?? executorSetting ?? false;

        AgentResponseUpdateEvent[] updates = testContext.Events.OfType<AgentResponseUpdateEvent>().ToArray();
        if (expectingEvents)
        {
            // The way TestReplayAgent is set up, it will emit one update per non-empty AIContent
            List<AIContent> expectedUpdateContents = TestMessages.SelectMany(message => message.Contents).ToList();

            updates.Should().HaveCount(expectedUpdateContents.Count);
            for (int i = 0; i < updates.Length; i++)
            {
                AgentResponseUpdateEvent updateEvent = updates[i];
                AIContent expectedUpdateContent = expectedUpdateContents[i];

                updateEvent.ExecutorId.Should().Be(agent.GetDescriptiveId());

                AgentResponseUpdate update = updateEvent.Update;
                update.AuthorName.Should().Be(TestAgentName);
                update.AgentId.Should().Be(TestAgentId);
                update.Contents.Should().HaveCount(1);
                update.Contents[0].Should().BeEquivalentTo(expectedUpdateContent);
            }
        }
        else
        {
            updates.Should().BeEmpty();
        }
    }

    [Theory]
    [InlineData(true)]
    [InlineData(false)]
    public async Task Test_AgentHostExecutor_EmitsResponseIFFConfiguredAsync(bool executorSetting)
    {
        // Arrange
        TestRunContext testContext = new();
        TestReplayAgent agent = new(TestMessages, TestAgentId, TestAgentName);
        AIAgentHostExecutor executor = new(agent, new() { EmitAgentRunResponseEvents = executorSetting });
        testContext.ConfigureExecutor(executor);

        // Act
        await executor.TakeTurnAsync(new(), testContext.BindWorkflowContext(executor.Id));

        // Assert
        AgentResponseEvent[] updates = testContext.Events.OfType<AgentResponseEvent>().ToArray();
        if (executorSetting)
        {
            updates.Should().HaveCount(1);

            AgentResponseEvent responseEvent = updates[0];
            responseEvent.ExecutorId.Should().Be(agent.GetDescriptiveId());

            AgentResponse response = responseEvent.Response;
            response.AgentId.Should().Be(TestAgentId);
            response.Messages.Should().HaveCount(TestMessages.Count - 1);

            for (int i = 0; i < response.Messages.Count; i++)
            {
                ChatMessage responseMessage = response.Messages[i];
                ChatMessage expectedMessage = TestMessages[i + 1]; // Skip the first empty message

                responseMessage.AuthorName.Should().Be(TestAgentName);
                responseMessage.Text.Should().Be(expectedMessage.Text);
            }
        }
        else
        {
            updates.Should().BeEmpty();
        }
    }

    private static ChatMessage UserMessage => new(ChatRole.User, "Hello from User!") { AuthorName = "User" };
    private static ChatMessage AssistantMessage => new(ChatRole.Assistant, "Hello from Assistant!") { AuthorName = "User" };
    private static ChatMessage TestAgentMessage => new(ChatRole.Assistant, $"Hello from {TestAgentName}!") { AuthorName = TestAgentName };

    [Theory]
    [InlineData(true, true, false, false)]
    [InlineData(true, true, false, true)]
    [InlineData(true, true, true, false)]
    [InlineData(true, true, true, true)]
    [InlineData(true, false, false, false)]
    [InlineData(true, false, false, true)]
    [InlineData(true, false, true, false)]
    [InlineData(true, false, true, true)]
    [InlineData(false, true, false, false)]
    [InlineData(false, true, false, true)]
    [InlineData(false, true, true, false)]
    [InlineData(false, true, true, true)]
    [InlineData(false, false, false, false)]
    [InlineData(false, false, false, true)]
    [InlineData(false, false, true, false)]
    [InlineData(false, false, true, true)]
    public async Task Test_AgentHostExecutor_ReassignsRolesIFFConfiguredAsync(bool executorSetting, bool includeUser, bool includeSelfMessages, bool includeOtherMessages)
    {
        // Arrange
        TestRunContext testContext = new();
        RoleCheckAgent agent = new(false, TestAgentId, TestAgentName);
        AIAgentHostExecutor executor = new(agent, new() { ReassignOtherAgentsAsUsers = executorSetting });
        testContext.ConfigureExecutor(executor);

        List<ChatMessage> messages = [];

        if (includeUser)
        {
            messages.Add(UserMessage);
        }

        if (includeSelfMessages)
        {
            messages.Add(TestAgentMessage);
        }

        if (includeOtherMessages)
        {
            messages.Add(AssistantMessage);
        }

        // Act
        await executor.Router.RouteMessageAsync(messages, testContext.BindWorkflowContext(executor.Id));

        Func<Task> act = async () => await executor.TakeTurnAsync(new(), testContext.BindWorkflowContext(executor.Id));

        // Assert
        bool shouldThrow = includeOtherMessages && !executorSetting;

        if (shouldThrow)
        {
            await act.Should().ThrowAsync<InvalidOperationException>();
        }
        else
        {
            await act.Should().NotThrowAsync();
        }
    }

    [Theory]
    [InlineData(true, TestAgentRequestType.FunctionCall)]
    [InlineData(false, TestAgentRequestType.FunctionCall)]
    //[InlineData(true, TestAgentRequestType.UserInputRequest)] TODO: Enable when we support polymorphic routing
    [InlineData(false, TestAgentRequestType.UserInputRequest)]
    public async Task Test_AgentHostExecutor_InterceptsRequestsIFFConfiguredAsync(bool intercept, TestAgentRequestType requestType)
    {
        const int UnpairedRequestCount = 2;
        const int PairedRequestCount = 3;

        // Arrange
        TestRunContext testContext = new();
        TestRequestAgent agent = new(requestType, UnpairedRequestCount, PairedRequestCount, TestAgentId, TestAgentName);
        AIAgentHostOptions agentHostOptions = requestType switch
        {
            TestAgentRequestType.FunctionCall =>
                new()
                {
                    EmitAgentRunResponseEvents = true,
                    InterceptUnterminatedFunctionCalls = intercept
                },
            TestAgentRequestType.UserInputRequest =>
                new()
                {
                    EmitAgentRunResponseEvents = true,
                    InterceptUserInputRequests = intercept
                },
            _ => throw new NotSupportedException()
        };

        AIAgentHostExecutor executor = new(agent, agentHostOptions);
        testContext.ConfigureExecutor(executor);

        // Act
        await executor.TakeTurnAsync(new(), testContext.BindWorkflowContext(executor.Id));

        // Assert
        List<object> responses;
        if (intercept)
        {
            // We expect to have a sent message containing the requests as an ExternalRequest
            switch (requestType)
            {
                case TestAgentRequestType.FunctionCall:
                    responses = ExtractAndValidateRequestContents<FunctionCallContent>();
                    break;
                case TestAgentRequestType.UserInputRequest:
                    responses = ExtractAndValidateRequestContents<UserInputRequestContent>();
                    break;
                default:
                    throw new NotSupportedException();
            }

            List<object> ExtractAndValidateRequestContents<TRequest>() where TRequest : AIContent
            {
                IEnumerable<TRequest> requests = testContext.QueuedMessages.Should().ContainKey(executor.Id)
                                                            .WhoseValue
                                                            .Select(envelope => envelope.Message as TRequest)
                                                            .Where(item => item is not null)
                                                            .Select(item => item!);

                return agent.ValidateUnpairedRequests(requests).ToList();
            }
        }
        else
        {
            responses = agent.ValidateUnpairedRequests([.. testContext.ExternalRequests]).ToList<object>();
        }

        // Act 2
        foreach (object response in responses.Take(UnpairedRequestCount - 1))
        {
            await executor.Router.RouteMessageAsync(response, testContext.BindWorkflowContext(executor.Id));
        }

        // Assert 2
        // Since we are not finished, we expect the agent to not have produced a final response (="Remaining: 1")
        AgentResponseEvent lastResponseEvent = testContext.Events.OfType<AgentResponseEvent>().Should().NotBeEmpty()
                                                                                                    .And.Subject.Last();

        lastResponseEvent.Response.Text.Should().Be("Remaining: 1");

        // Act 3
        object finalResponse = responses.Last();
        await executor.Router.RouteMessageAsync(finalResponse, testContext.BindWorkflowContext(executor.Id));

        // Assert 3
        // Now that we are finished, we expect the agent to have produced a final response
        lastResponseEvent = testContext.Events.OfType<AgentResponseEvent>().Should().NotBeEmpty()
                                                                              .And.Subject.Last();

        lastResponseEvent.Response.Text.Should().Be("Done");
    }
}
