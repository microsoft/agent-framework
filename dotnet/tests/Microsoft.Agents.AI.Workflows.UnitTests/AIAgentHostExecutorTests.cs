// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading.Tasks;
using FluentAssertions;
using Microsoft.Agents.AI.Workflows.Specialized;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Workflows.UnitTests;

public class AIAgentHostExecutorTests : AIAgentHostingExecutorTestsBase
{
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
        AIAgentHostExecutor executor = new(agent, new() { EmitAgentUpdateEvents = executorSetting });
        testContext.ConfigureExecutor(executor);

        // Act
        await executor.TakeTurnAsync(new(turnSetting), testContext.BindWorkflowContext(executor.Id));

        // Assert
        // The rules are: TurnToken overrides Agent, if set. Default to false, if both unset.
        bool expectingEvents = turnSetting ?? executorSetting ?? false;

        AgentResponseUpdateEvent[] updates = testContext.Events.OfType<AgentResponseUpdateEvent>().ToArray();
        CheckResponseUpdateEventsAgainstTestMessages(updates, expectingEvents, agent.GetDescriptiveId());
    }

    [Theory]
    [InlineData(true)]
    [InlineData(false)]
    public async Task Test_AgentHostExecutor_EmitsResponseIFFConfiguredAsync(bool executorSetting)
    {
        // Arrange
        TestRunContext testContext = new();
        TestReplayAgent agent = new(TestMessages, TestAgentId, TestAgentName);
        AIAgentHostExecutor executor = new(agent, new() { EmitAgentResponseEvents = executorSetting });
        testContext.ConfigureExecutor(executor);

        // Act
        await executor.TakeTurnAsync(new(), testContext.BindWorkflowContext(executor.Id));

        // Assert
        AgentResponseEvent[] updates = testContext.Events.OfType<AgentResponseEvent>().ToArray();
        CheckResponseEventsAgainstTestMessages(updates, expectingResponse: executorSetting, agent.GetDescriptiveId());
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
                    EmitAgentResponseEvents = true,
                    InterceptUnterminatedFunctionCalls = intercept
                },
            TestAgentRequestType.UserInputRequest =>
                new()
                {
                    EmitAgentResponseEvents = true,
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
                    responses = ExtractAndValidateRequestContents<ToolApprovalRequestContent>();
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
