// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Frozen;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text.Json;
using System.Text.Json.Serialization;
using System.Threading.Tasks;
using Azure.Identity;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.Configuration;
using Shared.IntegrationTests;
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
        DeclarativeWorkflowOptions workflowOptions) where TInput : notnull;

    protected Task RunWorkflowAsync(
        string workflowPath,
        string testcaseFileName,
        bool externalConversation = false)
    {
        this.Output.WriteLine($"WORKFLOW: {workflowPath}");
        this.Output.WriteLine($"TESTCASE: {testcaseFileName}");

        Testcase testcase = ReadTestcase(testcaseFileName);
        IConfiguration configuration = InitializeConfig();

        this.Output.WriteLine($"          {testcase.Description}");

        return
            testcase.Setup.Input.Type switch
            {
                nameof(ChatMessage) => this.TestWorkflowAsync<ChatMessage>(testcase, workflowPath, configuration),
                nameof(String) => this.TestWorkflowAsync<string>(testcase, workflowPath, configuration),
                _ => throw new NotSupportedException($"Input type '{testcase.Setup.Input.Type}' is not supported."),
            };
    }

    protected async Task TestWorkflowAsync<TInput>(
        Testcase testcase,
        string workflowPath,
        IConfiguration configuration,
        bool externalConversation = false) where TInput : notnull
    {
        this.Output.WriteLine($"INPUT: {testcase.Setup.Input.Value}");

        AzureAIConfiguration? foundryConfig = configuration.GetSection("AzureAI").Get<AzureAIConfiguration>();
        Assert.NotNull(foundryConfig);

        FrozenDictionary<string, string?> agentMap = await AgentFactory.GetAgentsAsync(foundryConfig, configuration);

        IConfiguration workflowConfig =
            new ConfigurationBuilder()
                .AddInMemoryCollection(agentMap)
                .Build();

        AzureAgentProvider agentProvider = new(foundryConfig.Endpoint, new AzureCliCredential());

        string? conversationId = null;
        if (externalConversation)
        {
            conversationId = await agentProvider.CreateConversationAsync().ConfigureAwait(false);
        }

        DeclarativeWorkflowOptions workflowOptions =
            new(agentProvider)
            {
                Configuration = workflowConfig,
                ConversationId = conversationId,
                LoggerFactory = this.Output
            };

        await this.RunAndVerifyAsync<TInput>(testcase, workflowPath, workflowOptions);
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

    protected static object GetInput<TInput>(Testcase testcase) where TInput : notnull =>
        testcase.Setup.Input.Type switch
        {
            nameof(ChatMessage) => new ChatMessage(ChatRole.User, testcase.Setup.Input.Value),
            nameof(String) => testcase.Setup.Input.Value,
            _ => throw new NotSupportedException($"Input type '{testcase.Setup.Input.Type}' is not supported."),
        };

    protected static Testcase ReadTestcase(string testcaseFileName)
    {
        using Stream testcaseStream = File.Open(Path.Combine("Testcases", testcaseFileName), FileMode.Open);
        Testcase? testcase = JsonSerializer.Deserialize<Testcase>(testcaseStream, s_jsonSerializerOptions);
        Assert.NotNull(testcase);
        return testcase;
    }

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
        public static void Conversation(string? conversationId, IReadOnlyList<ConversationUpdateEvent> conversationEvents, Testcase testcase)
        {
            if (string.IsNullOrEmpty(conversationId))
            {
                Assert.Equal(testcase.Validation.ConversationCount, conversationEvents.Count);
            }
            else
            {
                Assert.Equal(testcase.Validation.ConversationCount - 1, conversationEvents.Count);
            }
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
