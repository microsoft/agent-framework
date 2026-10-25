// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
#if NET
using System.IO;
#endif
using System.Linq;
using System.Reflection;
using System.Runtime.CompilerServices;
#if NET
using System.Text.Json;
#endif
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Xunit;

namespace Microsoft.Agents.AI.UnitTests;

/// <summary>Checks model-visible approval results through the default agent middleware.</summary>
public sealed class OpenFixApprovalResultTests
{
    private const string Missing = "No approval response was provided for this approval required tool call.";
    private const string HumanReason = "Human explicitly declined.";
    private const string FinalPrefix = "Tool call invocation was rejected by the approver and must not be retried.";

    /// <summary>Automatic rejection must leave the option of requesting fresh approval open.</summary>
    [Theory]
    [InlineData(false, "unanswered", false)]
    [InlineData(true, "unanswered", false)]
    [InlineData(false, "human", false)]
    [InlineData(true, "human", false)]
    [InlineData(false, "partial", false)]
    [InlineData(true, "partial", false)]
    [InlineData(false, "unanswered", true)]
    [InlineData(true, "unanswered", true)]
    [InlineData(false, "human", true)]
    [InlineData(true, "human", true)]
    [InlineData(false, "partial", true)]
    [InlineData(true, "partial", true)]
    public async Task DefaultStack_ApprovalResultsAsync(bool streaming, string mode, bool perServiceCallPersistence)
    {
        List<string> transcript = [];
        var failures = await RunCaseAsync(streaming, mode, perServiceCallPersistence, message =>
        {
            transcript.Add(message);
            Console.WriteLine(message);
        });
        Assert.True(failures.Count == 0, string.Join(Environment.NewLine, transcript));
    }

#if NET
    /// <summary>Checks package versions against the assemblies actually loaded by the test process.</summary>
    [Fact]
    public void ApprovalDependencies_LoadedVersionsMatchDependencyManifest()
    {
        // Arrange
        string manifest = Path.Combine(AppContext.BaseDirectory, $"{typeof(OpenFixApprovalResultTests).Assembly.GetName().Name}.deps.json");
        using var dependencies = JsonDocument.Parse(File.ReadAllText(manifest));
        var libraries = dependencies.RootElement.GetProperty("libraries");

        // Act / Assert
        foreach (var assembly in new[] { typeof(FunctionInvokingChatClient).Assembly, typeof(IChatClient).Assembly })
        {
            string packageVersion = Assert.IsType<string>(assembly.GetCustomAttribute<AssemblyInformationalVersionAttribute>()?.InformationalVersion).Split('+')[0];
            Console.WriteLine($"LOADED {assembly.GetName().Name}: assembly={assembly.GetName().Version}; package={packageVersion}; path={assembly.Location}");
            Assert.True(libraries.TryGetProperty($"{assembly.GetName().Name}/{packageVersion}", out _),
                $"Loaded {assembly.GetName().Name}/{packageVersion} does not match {manifest}.");
            Assert.Equal(Path.Combine(AppContext.BaseDirectory, $"{assembly.GetName().Name}.dll"), assembly.Location);
        }
    }
#endif

    private static async Task<List<string>> RunCaseAsync(bool streaming, string mode, bool perServiceCallPersistence, Action<string> log)
    {
        var failures = new List<string>();
        void Check(bool condition, string message)
        {
            log($"{(condition ? "PASS" : "FAIL")}: {message}");
            if (!condition)
            {
                failures.Add(message);
            }
        }

        log($"SCENARIO mode={mode}; streaming={streaming}; perServiceCallPersistence={perServiceCallPersistence}");
        foreach (var assembly in new[] { typeof(ChatClientAgent).Assembly, typeof(FunctionInvokingChatClient).Assembly, typeof(IChatClient).Assembly })
        {
            log($"LOADED {assembly.GetName().Name}: assembly={assembly.GetName().Version}; informational={assembly.GetCustomAttribute<AssemblyInformationalVersionAttribute>()?.InformationalVersion}");
        }
        bool hasFinalHumanRejection = typeof(FunctionInvokingChatClient).Assembly.GetName().Version >= new Version(10, 11);

        // Arrange: only the leaf model is simulated; all approval middleware is real.
        int executions = 0;
        using var leaf = new ScriptedClient();
        var agent = new ChatClientAgent(leaf, new ChatClientAgentOptions
        {
            ChatOptions = new ChatOptions
            {
                Tools = [new ApprovalRequiredAIFunction(AIFunctionFactory.Create(() =>
                {
                    Interlocked.Increment(ref executions);
                    return "executed";
                }, "Act"))],
            },
            ChatHistoryProvider = new InMemoryChatHistoryProvider(),
            RequirePerServiceCallChatHistoryPersistence = perServiceCallPersistence,
        });
        var session = await agent.CreateSessionAsync();
        Task<AgentResponse> RunAsync(IEnumerable<ChatMessage> messages) => streaming
            ? agent.RunStreamingAsync(messages, session).ToAgentResponseAsync()
            : agent.RunAsync(messages, session);
        List<AIContent> calls = [new FunctionCallContent("old", "Act")];
        if (string.Equals(mode, "partial", StringComparison.Ordinal))
        {
            calls.Add(new FunctionCallContent("human", "Act"));
            calls.Add(new FunctionCallContent("allowed", "Act"));
        }
        leaf.Replies.Enqueue(new ChatResponse(new ChatMessage(ChatRole.Assistant, calls)));
        var first = await RunAsync([new ChatMessage(ChatRole.User, "Please perform the action.")]);
        var requests = first.Messages.SelectMany(m => m.Contents).OfType<ToolApprovalRequestContent>()
            .ToDictionary(r => r.ToolCall.CallId);
        Check(requests.Count == calls.Count, "first run surfaces all approval requests");
        Check(executions == 0, "first run never executes gated tools");
        session = await agent.DeserializeSessionAsync(await agent.SerializeSessionAsync(session));

        // Act: leave the old request unanswered, or supply an explicit human decision.
        List<AIContent> answer = [new TextContent("Please perform the same action.")];
        if (string.Equals(mode, "human", StringComparison.Ordinal))
        {
            answer.Insert(0, requests["old"].CreateResponse(approved: false, reason: HumanReason));
        }

        if (string.Equals(mode, "partial", StringComparison.Ordinal))
        {
            answer.Insert(0, requests["human"].CreateResponse(approved: false, reason: HumanReason));
            answer.Insert(0, requests["allowed"].CreateResponse(approved: true));
        }
        var response = await RunAsync([new ChatMessage(ChatRole.User, answer)]);
        var results = leaf.LastResults.ToArray();
        foreach (var result in results)
        {
            log($"MODEL_RESULT mode={mode}; streaming={streaming}; call={result.Id}; text={result.Text}");
        }
        log($"TOOL_EXECUTIONS mode={mode}; streaming={streaming}; count={executions}");

        // Assert: accumulate failures so the remaining protocol checks still execute.
        Check(executions == (string.Equals(mode, "partial", StringComparison.Ordinal) ? 1 : 0), "only the explicitly approved call executes");
        Check(results.Count(r => r.Id == "old") == 1, "model receives exactly one old-call result");
        string old = results.Single(r => r.Id == "old").Text;
        var returnedResults = response.Messages.SelectMany(m => m.Contents).OfType<FunctionResultContent>().ToArray();
        Check(returnedResults.Count(r => r.CallId == "old") == 1, "caller receives exactly one old-call result");
        Check(string.Equals(returnedResults.Single(r => r.CallId == "old").Result?.ToString(), old, StringComparison.Ordinal),
            "caller receives the same old-call result as the model");
        var persistedResults = ChatClientAgentTestHelper.GetPersistedHistory(agent, session)
            .SelectMany(m => m.Contents).OfType<FunctionResultContent>().ToArray();
        Check(persistedResults.Count(r => r.CallId == "old") == 1, "history persists exactly one old-call result");
        Check(string.Equals(persistedResults.Single(r => r.CallId == "old").Result?.ToString(), old, StringComparison.Ordinal),
            "history preserves the model-visible old-call result");
        if (!string.Equals(mode, "human", StringComparison.Ordinal))
        {
            Check(old.IndexOf(Missing, StringComparison.Ordinal) >= 0, "automatic result explains missing approval");
            Check(old.IndexOf("rejected by the approver", StringComparison.OrdinalIgnoreCase) < 0, "automatic result does not claim an approver rejected it");
            Check(old.IndexOf("must not be retried", StringComparison.OrdinalIgnoreCase) < 0, "automatic result does not prohibit a new request");
        }
        if (!string.Equals(mode, "unanswered", StringComparison.Ordinal))
        {
            string denied = string.Equals(mode, "human", StringComparison.Ordinal) ? old : results.Single(r => r.Id == "human").Text;
            Check(denied.IndexOf(HumanReason, StringComparison.Ordinal) >= 0, "human rejection reason is retained");
            if (hasFinalHumanRejection)
            {
                Check(denied.StartsWith(FinalPrefix, StringComparison.Ordinal), "10.11 human rejection retains the final-decision prefix");
            }
            else
            {
                Check(denied.StartsWith("Tool call invocation rejected.", StringComparison.Ordinal), "baseline human rejection retains its rejection prefix");
            }
        }
        if (string.Equals(mode, "partial", StringComparison.Ordinal))
        {
            Check(results.Single(r => r.Id == "allowed").Text.IndexOf("executed", StringComparison.Ordinal) >= 0, "partial batch contains the approved invocation result");
        }
        if (string.Equals(mode, "unanswered", StringComparison.Ordinal))
        {
            session = await agent.DeserializeSessionAsync(await agent.SerializeSessionAsync(session));
            await RunAsync([new ChatMessage(ChatRole.User,
                [requests["old"].CreateResponse(approved: true), new TextContent("Late approval.")])]);
            log($"LATE_APPROVAL executions={executions}; old_results={leaf.LastResults.Count(r => r.Id == "old")}");
            Check(executions == 0, "late approval cannot execute the old call");
            Check(leaf.LastResults.Count(r => r.Id == "old") == 1, "history replay contains no duplicate old result");

            // This checks the protocol, not how a real model interprets rejection wording.
            leaf.Replies.Enqueue(new ChatResponse(new ChatMessage(ChatRole.Assistant,
                [new FunctionCallContent("fresh", "Act")])));
            var fresh = await RunAsync([new ChatMessage(ChatRole.User, "Please request the action again.")]);
            var freshRequests = fresh.Messages.SelectMany(m => m.Contents).OfType<ToolApprovalRequestContent>().ToArray();
            log($"FRESH_APPROVALS={freshRequests.Length}; TOOL_EXECUTIONS={executions}");
            Check(freshRequests.Length == 1 && freshRequests[0].ToolCall.CallId == "fresh", "new call receives a fresh approval request");
            Check(freshRequests.Length == 1 && freshRequests[0].RequestId != requests["old"].RequestId, "fresh request has a different identity");
            Check(executions == 0, "fresh call still waits for approval");
        }
        return failures;
    }

    private sealed class ScriptedClient : IChatClient
    {
        public Queue<ChatResponse> Replies { get; } = new();

        public List<(string Id, string Text)> LastResults { get; private set; } = [];

        public Task<ChatResponse> GetResponseAsync(IEnumerable<ChatMessage> messages, ChatOptions? options = null, CancellationToken cancellationToken = default)
        {
            cancellationToken.ThrowIfCancellationRequested();
            this.LastResults = messages.SelectMany(m => m.Contents).OfType<FunctionResultContent>()
                .Select(r => (r.CallId, r.Result?.ToString() ?? "<null>")).ToList();
            return Task.FromResult(this.Replies.Count > 0 ? this.Replies.Dequeue()
                : new ChatResponse(new ChatMessage(ChatRole.Assistant, "Done.")));
        }

        public async IAsyncEnumerable<ChatResponseUpdate> GetStreamingResponseAsync(IEnumerable<ChatMessage> messages, ChatOptions? options = null, [EnumeratorCancellation] CancellationToken cancellationToken = default)
        {
            var response = await this.GetResponseAsync(messages, options, cancellationToken);
            foreach (var update in response.ToChatResponseUpdates())
            {
                cancellationToken.ThrowIfCancellationRequested();
                yield return update;
            }
        }

        public object? GetService(Type serviceType, object? serviceKey = null) => null;

        public void Dispose()
        {
        }
    }
}
