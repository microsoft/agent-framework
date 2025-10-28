// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text.Json;
using System.Text.Json.Serialization;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Xunit.Abstractions;
using Xunit.Sdk;

namespace Microsoft.Agents.AI.Workflows.Declarative.IntegrationTests.Framework;

/// <summary>
/// Base class for workflow tests.
/// </summary>
public abstract class WorkflowTest(ITestOutputHelper output) : IntegrationTest(output)
{
    protected abstract Task RunAndVerifyAsync<TInput>(
        Testcase testcase,
        string workflowPath,
        DeclarativeWorkflowOptions workflowOptions,
        TInput input,
        bool useJsonCheckpoint) where TInput : notnull;

    protected Task RunWorkflowAsync(
        string workflowPath,
        string testcaseFileName,
        bool externalConversation = false,
        bool useJsonCheckpoint = false)
    {
        this.Output.WriteLine($"WORKFLOW: {workflowPath}");
        this.Output.WriteLine($"TESTCASE: {testcaseFileName}");

        Testcase testcase = ReadTestcase(testcaseFileName);

        this.Output.WriteLine($"          {testcase.Description}");

        return
            testcase.Setup.Input.Type switch
            {
                nameof(ChatMessage) => TestWorkflowAsync<ChatMessage>(),
                nameof(String) => TestWorkflowAsync<string>(),
                _ => throw new NotSupportedException($"Input type '{testcase.Setup.Input.Type}' is not supported."),
            };

        async Task TestWorkflowAsync<TInput>() where TInput : notnull
        {
            this.Output.WriteLine($"INPUT: {testcase.Setup.Input.Value}");

            DeclarativeWorkflowOptions workflowOptions = await this.CreateOptionsAsync(externalConversation).ConfigureAwait(false);

            TInput input = (TInput)GetInput<TInput>(testcase);

            await this.RunAndVerifyAsync(testcase, workflowPath, workflowOptions, input, useJsonCheckpoint);
        }
    }

    protected static string? GetConversationId(string? conversationId, IReadOnlyList<ConversationUpdateEvent> conversationEvents)
    {
        if (!string.IsNullOrEmpty(conversationId))
        {
            return conversationId;
        }

        if (conversationEvents.Count > 0)
        {
            return conversationEvents.SingleOrDefault(conversationEvent => conversationEvent.IsWorkflow)?.ConversationId;
        }

        return null;
    }

    protected static Testcase ReadTestcase(string testcaseFileName)
    {
        string testcaseJson = File.ReadAllText(Path.Combine("Testcases", testcaseFileName));
        Testcase? testcase = JsonSerializer.Deserialize<Testcase>(testcaseJson, s_jsonSerializerOptions);
        Assert.NotNull(testcase);
        return testcase;
    }

    private static object GetInput<TInput>(Testcase testcase) where TInput : notnull =>
        testcase.Setup.Input.Type switch
        {
            nameof(ChatMessage) => new ChatMessage(ChatRole.User, testcase.Setup.Input.Value),
            nameof(String) => testcase.Setup.Input.Value,
            _ => throw new NotSupportedException($"Input type '{testcase.Setup.Input.Type}' is not supported."),
        };

    internal static string GetRepoFolder()
    {
        DirectoryInfo? current = new(Directory.GetCurrentDirectory());

        while (current is not null)
        {
            if (Directory.Exists(Path.Combine(current.FullName, ".git")))
            {
                return current.FullName;
            }

            current = current.Parent;
        }

        throw new XunitException("Unable to locate repository root folder.");
    }

    protected static class AssertWorkflow
    {
        public static void Conversation(IReadOnlyList<ConversationUpdateEvent> conversationEvents, Testcase testcase)
        {
            Assert.Equal(testcase.Validation.ConversationCount, conversationEvents.Count);
        }

        // "isCompletion" adjusts validation logic to account for when condition completion is not experienced due to goto.  Remove this test logic once addressed.
        public static void EventCounts(int actualCount, Testcase testcase, bool isCompletion = false)
        {
            Assert.True(actualCount + (isCompletion ? 1 : 0) >= testcase.Validation.MinActionCount, $"Event count less than expected: {testcase.Validation.MinActionCount} (Actual: {actualCount}).");
            if (testcase.Validation.MaxActionCount != -1)
            {
                int maxExpectedCount = testcase.Validation.MaxActionCount ?? testcase.Validation.MinActionCount;
                Assert.True(actualCount <= maxExpectedCount, $"Event count greater than expected: {maxExpectedCount} (Actual: {actualCount}).");
            }
        }

        public static void Responses(IReadOnlyList<AgentRunResponseEvent> responseEvents, Testcase testcase)
        {
            Assert.True(responseEvents.Count >= testcase.Validation.MinResponseCount, $"Response count less than expected: {testcase.Validation.MinResponseCount} (Actual: {responseEvents.Count})");
            if (testcase.Validation.MaxResponseCount != -1)
            {
                int maxExpectedCount = testcase.Validation.MaxResponseCount ?? testcase.Validation.MinResponseCount;
                Assert.True(responseEvents.Count <= maxExpectedCount, $"Response count greater than expected: {maxExpectedCount} (Actual: {responseEvents.Count}).");
            }
        }

        public static async ValueTask MessagesAsync(string? conversationId, Testcase testcase, WorkflowAgentProvider agentProvider)
        {
            int minExpectedCount = testcase.Validation.MinMessageCount ?? testcase.Validation.MinResponseCount;
            int maxExpectedCount = testcase.Validation.MaxMessageCount ?? testcase.Validation.MaxResponseCount ?? minExpectedCount;
            int messageCount = 0;
            if (!string.IsNullOrEmpty(conversationId))
            {
                messageCount = await agentProvider.GetMessagesAsync(conversationId).CountAsync();
            }

            ++minExpectedCount;
            Assert.True(messageCount >= minExpectedCount, $"Workflow message count less than expected: {minExpectedCount} (Actual: {messageCount}).");
            if (maxExpectedCount != -1)
            {
                ++maxExpectedCount;
                Assert.True(messageCount <= maxExpectedCount, $"Workflow message count greater than expected: {maxExpectedCount} (Actual: {messageCount}).");
            }
        }

        internal static void EventSequence(IEnumerable<string> sourceIds, Testcase testcase)
        {
            string lastId = string.Empty;
            Queue<string> startIds = [];
            Queue<string> repeatIds = [];
            bool validateStart = false;
            bool validateRepeat = false;
            foreach (string sourceId in sourceIds)
            {
                if (!validateStart && testcase.Validation.Actions.Start.Count > 0)
                {
                    if (testcase.Validation.Actions.Start.Count > 0 &&
                        startIds.Count == 0 &&
                        sourceId.Equals(testcase.Validation.Actions.Start[0], StringComparison.Ordinal))
                    {
                        // Initialize start sequence
                        startIds = new(testcase.Validation.Actions.Start);
                    }

                    // Verify start sequence
                    if (startIds.Count > 0)
                    {
                        Assert.Equal(startIds.Dequeue(), sourceId);
                        validateStart = startIds.Count == 0;
                    }
                }
                else
                {
                    if (testcase.Validation.Actions.Repeat.Count > 0 &&
                        repeatIds.Count == 0 &&
                        sourceId.Equals(testcase.Validation.Actions.Repeat[0], StringComparison.Ordinal))
                    {
                        // Initialize repeat sequence
                        repeatIds = new(testcase.Validation.Actions.Repeat);
                    }
                    // Verify repeat sequence
                    if (repeatIds.Count > 0)
                    {
                        Assert.Equal(repeatIds.Dequeue(), sourceId);
                        validateRepeat = true;
                    }
                }
                lastId = sourceId;
            }

            Assert.Equal(testcase.Validation.Actions.Start.Count > 0, validateStart);
            Assert.Equal(testcase.Validation.Actions.Repeat.Count > 0, validateRepeat);

            Assert.NotEmpty(lastId);
            HashSet<string> finalIds = [.. testcase.Validation.Actions.Final];
            Assert.Contains(lastId, finalIds);
        }
    }

    protected static readonly JsonSerializerOptions s_jsonSerializerOptions = new()
    {
        DefaultIgnoreCondition = JsonIgnoreCondition.WhenWritingNull,
        PropertyNamingPolicy = JsonNamingPolicy.SnakeCaseLower,
        ReadCommentHandling = JsonCommentHandling.Skip,
        WriteIndented = true,
    };
}
