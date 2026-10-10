// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Compaction;
using Microsoft.Extensions.AI;
using Moq;

namespace Microsoft.Agents.AI.UnitTests.Compaction;

/// <summary>
/// Contains tests for the <see cref="CompactionProvider"/> class.
/// </summary>
public sealed class CompactionProviderTests
{
    [Fact]
    public void ConstructorThrowsOnNullStrategy()
    {
        Assert.Throws<ArgumentNullException>(() => new CompactionProvider(null!));
    }

    [Fact]
    public void StateKeysReturnsExpectedKey()
    {
        // Arrange
        TruncationCompactionStrategy strategy = new(CompactionTriggers.TokensExceed(100000));
        CompactionProvider provider = new(strategy);

        // Act & Assert — default state key is the strategy type name
        Assert.Single(provider.StateKeys);
        Assert.Equal(nameof(TruncationCompactionStrategy), provider.StateKeys[0]);
    }

    [Fact]
    public void StateKeysAreStableAcrossEquivalentInstances()
    {
        // Arrange — two providers with equivalent (but distinct) strategies
        CompactionProvider provider1 = new(new TruncationCompactionStrategy(CompactionTriggers.TokensExceed(100000)));
        CompactionProvider provider2 = new(new TruncationCompactionStrategy(CompactionTriggers.TokensExceed(100000)));

        // Act & Assert — default keys must be identical for session state stability
        Assert.Equal(provider1.StateKeys[0], provider2.StateKeys[0]);
    }

    [Fact]
    public void StateKeysReturnsCustomKeyWhenProvided()
    {
        // Arrange
        TruncationCompactionStrategy strategy = new(CompactionTriggers.TokensExceed(100000));
        CompactionProvider provider = new(strategy, stateKey: "my-custom-key");

        // Act & Assert
        Assert.Single(provider.StateKeys);
        Assert.Equal("my-custom-key", provider.StateKeys[0]);
    }

    [Fact]
    public async Task InvokingAsyncNoSessionPassesThroughAsync()
    {
        // Arrange — no session → passthrough
        TruncationCompactionStrategy strategy = new(CompactionTriggers.TokensExceed(100000));
        CompactionProvider provider = new(strategy);

        Mock<AIAgent> mockAgent = new() { CallBase = true };
        List<ChatMessage> messages =
        [
            new ChatMessage(ChatRole.User, "Hello"),
        ];

        AIContextProvider.InvokingContext context = new(
            mockAgent.Object,
            session: null,
            new AIContext { Messages = messages });

        // Act
        AIContext result = await provider.InvokingAsync(context);

        // Assert — original context returned unchanged
        Assert.Same(messages, result.Messages);
    }

    [Fact]
    public async Task InvokingAsyncNullMessagesPassesThroughAsync()
    {
        // Arrange — messages is null → passthrough
        TruncationCompactionStrategy strategy = new(CompactionTriggers.TokensExceed(100000));
        CompactionProvider provider = new(strategy);

        Mock<AIAgent> mockAgent = new() { CallBase = true };
        TestAgentSession session = new();
        AIContextProvider.InvokingContext context = new(
            mockAgent.Object,
            session,
            new AIContext { Messages = null });

        // Act
        AIContext result = await provider.InvokingAsync(context);

        // Assert — original context returned unchanged
        Assert.Null(result.Messages);
    }

    [Fact]
    public async Task InvokingAsyncAppliesCompactionWhenTriggeredAsync()
    {
        // Arrange — strategy that always triggers and keeps only 1 group
        TruncationCompactionStrategy strategy = new(_ => true, minimumPreservedGroups: 1);
        CompactionProvider provider = new(strategy);

        Mock<AIAgent> mockAgent = new() { CallBase = true };
        TestAgentSession session = new();
        List<ChatMessage> messages =
        [
            new ChatMessage(ChatRole.User, "Q1"),
            new ChatMessage(ChatRole.Assistant, "A1"),
            new ChatMessage(ChatRole.User, "Q2"),
        ];

        AIContextProvider.InvokingContext context = new(
            mockAgent.Object,
            session,
            new AIContext { Messages = messages });

        // Act
        AIContext result = await provider.InvokingAsync(context);

        // Assert — compaction should have reduced the message count
        Assert.NotNull(result.Messages);
        List<ChatMessage> resultList = [.. result.Messages!];
        Assert.True(resultList.Count < messages.Count);
    }

    [Theory]
    [InlineData(null, true)]
    [InlineData("", true)]
    [InlineData(" ", true)]
    [InlineData(PerServiceCallChatHistoryPersistingChatClient.LocalHistoryConversationId, true)]
    [InlineData("remote-conversation-id", false)]
    public async Task InvokingAsyncCompactsOnlyLocallyManagedHistoryAsync(string? conversationId, bool shouldCompact)
    {
        // Arrange
        TruncationCompactionStrategy strategy = new(CompactionTriggers.Always, minimumPreservedGroups: 1);
        CompactionProvider provider = new(strategy);
        Mock<AIAgent> mockAgent = new() { CallBase = true };
        ChatClientAgentSession session = new(conversationId);
        List<ChatMessage> messages =
        [
            new ChatMessage(ChatRole.User, "Q1"),
            new ChatMessage(ChatRole.Assistant, "A1"),
            new ChatMessage(ChatRole.User, "Q2"),
        ];
        AIContextProvider.InvokingContext context = new(
            mockAgent.Object,
            session,
            new AIContext { Messages = messages });

        // Act
        AIContext result = await provider.InvokingAsync(context);

        // Assert
        Assert.NotNull(result.Messages);
        if (shouldCompact)
        {
            Assert.Same(messages[2], Assert.Single(result.Messages));
        }
        else
        {
            Assert.Same(context.AIContext, result);
            Assert.Same(messages, result.Messages);
        }
    }

    [Fact]
    public async Task InvokingAsyncNoCompactionNeededReturnsOriginalMessagesAsync()
    {
        // Arrange — trigger never fires → no compaction
        TruncationCompactionStrategy strategy = new(CompactionTriggers.TokensExceed(100000));
        CompactionProvider provider = new(strategy);

        Mock<AIAgent> mockAgent = new() { CallBase = true };
        TestAgentSession session = new();
        List<ChatMessage> messages =
        [
            new ChatMessage(ChatRole.User, "Hello"),
        ];

        AIContextProvider.InvokingContext context = new(
            mockAgent.Object,
            session,
            new AIContext { Messages = messages });

        // Act
        AIContext result = await provider.InvokingAsync(context);

        // Assert — original messages passed through
        Assert.NotNull(result.Messages);
        List<ChatMessage> resultList = [.. result.Messages!];
        Assert.Single(resultList);
        Assert.Equal("Hello", resultList[0].Text);
    }

    [Fact]
    public async Task InvokingAsyncPreservesInstructionsAndToolsAsync()
    {
        // Arrange
        TruncationCompactionStrategy strategy = new(CompactionTriggers.TokensExceed(100000));
        CompactionProvider provider = new(strategy);

        Mock<AIAgent> mockAgent = new() { CallBase = true };
        TestAgentSession session = new();
        List<ChatMessage> messages = [new ChatMessage(ChatRole.User, "Hello")];
        AITool[] tools = [AIFunctionFactory.Create(() => "tool", "MyTool")];

        AIContextProvider.InvokingContext context = new(
            mockAgent.Object,
            session,
            new AIContext
            {
                Instructions = "Be helpful",
                Messages = messages,
                Tools = tools
            });

        // Act
        AIContext result = await provider.InvokingAsync(context);

        // Assert — instructions and tools are preserved
        Assert.Equal("Be helpful", result.Instructions);
        Assert.Same(tools, result.Tools);
    }

    [Fact]
    public async Task InvokingAsyncWithExistingIndexUpdatesAsync()
    {
        // Arrange — call twice to exercise the "existing index" path
        TruncationCompactionStrategy strategy = new(_ => true, minimumPreservedGroups: 1);
        CompactionProvider provider = new(strategy);

        Mock<AIAgent> mockAgent = new() { CallBase = true };
        TestAgentSession session = new();

        List<ChatMessage> messages1 =
        [
            new ChatMessage(ChatRole.User, "Q1"),
            new ChatMessage(ChatRole.Assistant, "A1"),
            new ChatMessage(ChatRole.User, "Q2"),
        ];

        AIContextProvider.InvokingContext context1 = new(
            mockAgent.Object,
            session,
            new AIContext { Messages = messages1 });

        // First call — initializes state
        await provider.InvokingAsync(context1);

        List<ChatMessage> messages2 =
        [
            new ChatMessage(ChatRole.User, "Q1"),
            new ChatMessage(ChatRole.Assistant, "A1"),
            new ChatMessage(ChatRole.User, "Q2"),
            new ChatMessage(ChatRole.Assistant, "A2"),
            new ChatMessage(ChatRole.User, "Q3"),
        ];

        AIContextProvider.InvokingContext context2 = new(
            mockAgent.Object,
            session,
            new AIContext { Messages = messages2 });

        // Act — second call exercises the update path
        AIContext result = await provider.InvokingAsync(context2);

        // Assert
        Assert.NotNull(result.Messages);
    }

    [Fact]
    public async Task InvokingAsyncIncludesNewUserMessageBeforeRepeatedTodoListAsync()
    {
        // Arrange — the todo list provider emits the same empty list after each user turn.
        const string TodoList = "### Current todo list\n- none yet";
        CompactionProvider provider = new(new TruncationCompactionStrategy(CompactionTriggers.TokensExceed(100000)));
        Mock<AIAgent> mockAgent = new() { CallBase = true };
        TestAgentSession session = new();
        List<ChatMessage> messages =
        [
            new ChatMessage(ChatRole.User, "Hello"),
            new ChatMessage(ChatRole.User, TodoList),
        ];

        await provider.InvokingAsync(new(mockAgent.Object, session, new AIContext { Messages = messages }));

        // Act
        messages.Add(new ChatMessage(ChatRole.User, "What is the weather today?"));
        messages.Add(new ChatMessage(ChatRole.User, TodoList));
        AIContext result = await provider.InvokingAsync(new(mockAgent.Object, session, new AIContext { Messages = messages }));

        // Assert
        Assert.NotNull(result.Messages);
        List<ChatMessage> resultMessages = [.. result.Messages];
        Assert.Equal(messages.Count, resultMessages.Count);
        Assert.Contains(resultMessages, message => message.Text == "What is the weather today?");
    }

    [Fact]
    public async Task InvokingAsyncIncludesNewUserMessageAfterInputSummaryAsync()
    {
        // Arrange — a summary already present in the input must count toward the saved append boundary.
        const string TodoList = "### Current todo list\n- none yet";
        CompactionProvider provider = new(new TruncationCompactionStrategy(CompactionTriggers.TokensExceed(100000)));
        Mock<AIAgent> mockAgent = new() { CallBase = true };
        TestAgentSession session = new();
        ChatMessage summary = new(ChatRole.Assistant, "Earlier conversation");
        (summary.AdditionalProperties ??= [])[CompactionMessageGroup.SummaryPropertyKey] = true;
        List<ChatMessage> messages = [summary, new ChatMessage(ChatRole.User, TodoList)];
        await provider.InvokingAsync(new(mockAgent.Object, session, new AIContext { Messages = messages }));
        var serializedState = session.StateBag.Serialize();
        Assert.Equal(2, serializedState.GetProperty(provider.StateKeys[0]).GetProperty("processedinputmessagecount").GetInt32());
        Assert.Equal(0, serializedState.GetProperty(provider.StateKeys[0]).GetProperty("inputsummarygroupindices")[0].GetInt32());
        TestAgentSession restoredSession = new(AgentSessionStateBag.Deserialize(serializedState));

        // Act
        messages.Add(new ChatMessage(ChatRole.User, "What is the weather today?"));
        messages.Add(new ChatMessage(ChatRole.User, TodoList));
        AIContext result = await provider.InvokingAsync(new(mockAgent.Object, restoredSession, new AIContext { Messages = messages }));

        // Assert
        Assert.NotNull(result.Messages);
        List<ChatMessage> resultMessages = [.. result.Messages];
        Assert.Equal(messages.Count, resultMessages.Count);
        Assert.Contains(resultMessages, message => message.Text == "What is the weather today?");
    }

    [Fact]
    public async Task InvokingAsyncRebuildsReplacedHistoryWithRepeatedBoundaryAsync()
    {
        // Arrange — restore session state with a saved todo boundary and replace the earlier input history.
        const string TodoList = "### Current todo list\n- none yet";
        CompactionProvider provider = new(new TruncationCompactionStrategy(CompactionTriggers.TokensExceed(100000)));
        Mock<AIAgent> mockAgent = new() { CallBase = true };
        TestAgentSession session = new();
        List<ChatMessage> originalMessages =
        [
            new ChatMessage(ChatRole.User, "Old question"),
            new ChatMessage(ChatRole.User, TodoList),
        ];
        await provider.InvokingAsync(new(mockAgent.Object, session, new AIContext { Messages = originalMessages }));
        TestAgentSession restoredSession = new(AgentSessionStateBag.Deserialize(session.StateBag.Serialize()));
        List<ChatMessage> replacement =
        [
            new ChatMessage(ChatRole.User, "New question"),
            new ChatMessage(ChatRole.User, TodoList),
            new ChatMessage(ChatRole.Assistant, "New answer"),
        ];

        // Act
        AIContext result = await provider.InvokingAsync(new(mockAgent.Object, restoredSession, new AIContext { Messages = replacement }));

        // Assert
        Assert.NotNull(result.Messages);
        List<ChatMessage> resultMessages = [.. result.Messages];
        Assert.Equal(replacement.Count, resultMessages.Count);
        Assert.Equal("New question", resultMessages[0].Text);
        Assert.Equal("New answer", resultMessages[2].Text);
    }

    [Fact]
    public async Task InvokingAsyncUsesSummaryProvenanceAfterSerializationAsync()
    {
        // Arrange — persist both summary origins, with the generated group preceding the input group.
        CompactionProvider provider = new(new TruncationCompactionStrategy(CompactionTriggers.TokensExceed(100000)));
        Mock<AIAgent> mockAgent = new() { CallBase = true };
        TestAgentSession session = new();
        ChatMessage inputSummary = new(ChatRole.Assistant, "S1");
        (inputSummary.AdditionalProperties ??= [])[CompactionMessageGroup.SummaryPropertyKey] = true;
        CompactionMessageIndex index = CompactionMessageIndex.Create([inputSummary, new ChatMessage(ChatRole.User, "U")]);
        ChatMessage generatedSummary = new(ChatRole.Assistant, "X");
        (generatedSummary.AdditionalProperties ??= [])[CompactionMessageGroup.SummaryPropertyKey] = true;
        index.InsertGroup(0, CompactionGroupKind.Summary, [generatedSummary]);
        CompactionProvider.State state = new()
        {
            MessageGroups = [.. index.Groups],
            ProcessedInputMessageCount = index.ProcessedInputMessageCount,
            InputSummaryGroupIndices = index.InputSummaryGroupIndices,
            InputPrefixFingerprint = index.InputPrefixFingerprint,
        };
        session.StateBag.SetValue(provider.StateKeys[0], state, AgentJsonUtilities.DefaultOptions);
        var serializedState = session.StateBag.Serialize();
        TestAgentSession unchangedSession = new(AgentSessionStateBag.Deserialize(serializedState));
        List<ChatMessage> appended = [inputSummary, new ChatMessage(ChatRole.User, "U"), new ChatMessage(ChatRole.User, "Follow-up")];
        ChatMessage replacementSummary = new(ChatRole.Assistant, "X");
        (replacementSummary.AdditionalProperties ??= [])[CompactionMessageGroup.SummaryPropertyKey] = true;
        List<ChatMessage> replacement = [replacementSummary, new ChatMessage(ChatRole.User, "U")];

        // Act — unchanged input preserves the generated summary after session serialization.
        AIContext appendedResult = await provider.InvokingAsync(new(mockAgent.Object, unchangedSession, new AIContext { Messages = appended }));

        // Assert
        Assert.NotNull(appendedResult.Messages);
        List<ChatMessage> appendedResultMessages = [.. appendedResult.Messages];
        Assert.Equal(4, appendedResultMessages.Count);
        Assert.Equal("X", appendedResultMessages[0].Text);
        Assert.Equal("S1", appendedResultMessages[1].Text);
        Assert.Equal("Follow-up", appendedResultMessages[3].Text);

        // Act — changed input matches the generated summary but must discard the stale input summary.
        TestAgentSession restoredSession = new(AgentSessionStateBag.Deserialize(serializedState));
        AIContext result = await provider.InvokingAsync(new(mockAgent.Object, restoredSession, new AIContext { Messages = replacement }));

        // Assert
        Assert.NotNull(result.Messages);
        List<ChatMessage> resultMessages = [.. result.Messages];
        Assert.Equal(2, resultMessages.Count);
        Assert.Equal("X", resultMessages[0].Text);
        Assert.Equal("U", resultMessages[1].Text);
    }

    [Fact]
    public async Task InvokingAsyncKeepsReducedHistoryWhenInputIsAppendedAfterSerializationAsync()
    {
        // Arrange — reduction leaves only C, while the fingerprint still validates the full original input.
        RecordingChatReducer reducer = new();
        CompactionProvider provider = new(new ChatReducerCompactionStrategy(reducer, CompactionTriggers.Always));
        Mock<AIAgent> mockAgent = new() { CallBase = true };
        TestAgentSession session = new();
        List<ChatMessage> firstInput =
        [
            new(ChatRole.User, "A"),
            new(ChatRole.Assistant, "B"),
            new(ChatRole.User, "C"),
        ];
        AIContext firstResult = await provider.InvokingAsync(new(mockAgent.Object, session, new AIContext { Messages = firstInput }));
        var serializedState = session.StateBag.Serialize();
        Assert.Equal(3, serializedState.GetProperty(provider.StateKeys[0]).GetProperty("processedinputmessagecount").GetInt32());
        TestAgentSession restoredSession = new(AgentSessionStateBag.Deserialize(serializedState));
        List<ChatMessage> appended =
        [
            new(ChatRole.User, "A"),
            new(ChatRole.Assistant, "B"),
            new(ChatRole.User, "C"),
            new(ChatRole.Assistant, "D"),
        ];

        // Act
        AIContext secondResult = await provider.InvokingAsync(new(mockAgent.Object, restoredSession, new AIContext { Messages = appended }));

        // Assert — the reducer sees the retained C plus D, not the full input again.
        Assert.Equal(["C"], firstResult.Messages!.Select(message => message.Text));
        Assert.Equal(["D"], secondResult.Messages!.Select(message => message.Text));
        Assert.Equal(2, reducer.Inputs.Count);
        Assert.Equal(["A", "B", "C"], reducer.Inputs[0].Select(message => message.Text));
        Assert.Equal(["C", "D"], reducer.Inputs[1].Select(message => message.Text));
        Assert.Equal(4, restoredSession.StateBag.Serialize().GetProperty(provider.StateKeys[0]).GetProperty("processedinputmessagecount").GetInt32());

        // Act & Assert — another serialized turn retains the new reduced boundary.
        TestAgentSession thirdSession = new(AgentSessionStateBag.Deserialize(restoredSession.StateBag.Serialize()));
        List<ChatMessage> thirdInput = [.. appended, new(ChatRole.User, "E")];
        AIContext thirdResult = await provider.InvokingAsync(new(mockAgent.Object, thirdSession, new AIContext { Messages = thirdInput }));
        Assert.Equal(["E"], thirdResult.Messages!.Select(message => message.Text));
        Assert.Equal(["D", "E"], reducer.Inputs[2].Select(message => message.Text));
    }

    [Fact]
    public async Task InvokingAsyncRebuildsReducedHistoryWhenInputPrefixChangesAsync()
    {
        // Arrange — the saved boundary C remains, but the earlier input is edited with the same MessageId.
        RecordingChatReducer reducer = new();
        CompactionProvider provider = new(new ChatReducerCompactionStrategy(reducer, CompactionTriggers.Always));
        Mock<AIAgent> mockAgent = new() { CallBase = true };
        TestAgentSession session = new();
        List<ChatMessage> firstInput =
        [
            new(ChatRole.User, "A") { MessageId = "message-1" },
            new(ChatRole.Assistant, "B"),
            new(ChatRole.User, "C"),
        ];
        await provider.InvokingAsync(new(mockAgent.Object, session, new AIContext { Messages = firstInput }));
        TestAgentSession restoredSession = new(AgentSessionStateBag.Deserialize(session.StateBag.Serialize()));
        List<ChatMessage> replacement =
        [
            new(ChatRole.User, "X") { MessageId = "message-1" },
            new(ChatRole.Assistant, "B"),
            new(ChatRole.User, "C"),
            new(ChatRole.Assistant, "D"),
        ];

        // Act
        AIContext result = await provider.InvokingAsync(new(mockAgent.Object, restoredSession, new AIContext { Messages = replacement }));

        // Assert — rebuilding is necessary because X changed the saved prefix.
        Assert.Equal(["D"], result.Messages!.Select(message => message.Text));
        Assert.Equal(2, reducer.Inputs.Count);
        Assert.Equal(["X", "B", "C", "D"], reducer.Inputs[1].Select(message => message.Text));
        Assert.Equal(4, restoredSession.StateBag.Serialize().GetProperty(provider.StateKeys[0]).GetProperty("processedinputmessagecount").GetInt32());
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task InvokingAsyncRebuildsReducedHistoryWhenMessageIdChangesAsync(bool serializeSession)
    {
        // Arrange
        RecordingChatReducer reducer = new();
        CompactionProvider provider = new(new ChatReducerCompactionStrategy(reducer, CompactionTriggers.Always));
        Mock<AIAgent> mockAgent = new() { CallBase = true };
        TestAgentSession session = new();
        ChatMessage retained = new(ChatRole.User, "Keep");
        List<ChatMessage> firstInput = [new(ChatRole.User, "Old") { MessageId = "old-id" }, retained];
        await provider.InvokingAsync(new(mockAgent.Object, session, new AIContext { Messages = firstInput }));
        if (serializeSession)
        {
            session = new(AgentSessionStateBag.Deserialize(session.StateBag.Serialize()));
        }

        ChatMessage replacement = new(ChatRole.User, "Old") { MessageId = "new-id" };
        List<ChatMessage> input = [replacement, retained, new(ChatRole.User, "New")];

        // Act
        await provider.InvokingAsync(new(mockAgent.Object, session, new AIContext { Messages = input }));

        // Assert — an identity change invalidates the saved reduction even when content is unchanged.
        Assert.Equal(2, reducer.Inputs.Count);
        Assert.Equal(["Old", "Keep", "New"], reducer.Inputs[1].Select(message => message.Text));
        Assert.Same(replacement, reducer.Inputs[1][0]);
        Assert.Equal("new-id", reducer.Inputs[1][0].MessageId);
    }

    [Fact]
    public async Task InvokingAsyncPreservesReducedHistoryWithUnchangedMessageIdsAfterSerializationAsync()
    {
        // Arrange — unchanged IDs in newly materialized messages must preserve a serialized reduction.
        RecordingChatReducer reducer = new();
        CompactionProvider provider = new(new ChatReducerCompactionStrategy(reducer, CompactionTriggers.Always));
        Mock<AIAgent> mockAgent = new() { CallBase = true };
        TestAgentSession session = new();
        List<ChatMessage> firstInput =
        [
            new(ChatRole.User, "Old") { MessageId = "message-1" },
            new(ChatRole.User, "Keep") { MessageId = "message-2" },
        ];
        await provider.InvokingAsync(new(mockAgent.Object, session, new AIContext { Messages = firstInput }));
        TestAgentSession restoredSession = new(AgentSessionStateBag.Deserialize(session.StateBag.Serialize()));
        List<ChatMessage> input =
        [
            new(ChatRole.User, "Old") { MessageId = "message-1" },
            new(ChatRole.User, "Keep") { MessageId = "message-2" },
            new(ChatRole.User, "New") { MessageId = "message-3" },
        ];

        // Act
        await provider.InvokingAsync(new(mockAgent.Object, restoredSession, new AIContext { Messages = input }));

        // Assert — the reducer receives the retained subset and new message, without the discarded history.
        Assert.Equal(2, reducer.Inputs.Count);
        Assert.Equal(["Keep", "New"], reducer.Inputs[1].Select(message => message.Text));
        Assert.Equal(["message-2", "message-3"], reducer.Inputs[1].Select(message => message.MessageId));
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task InvokingAsyncRebuildsReducedHistoryWhenInputIsMutatedAsync(bool serializeSession)
    {
        // Arrange
        RecordingChatReducer reducer = new();
        CompactionProvider provider = new(new ChatReducerCompactionStrategy(reducer, CompactionTriggers.Always));
        Mock<AIAgent> mockAgent = new() { CallBase = true };
        TestAgentSession session = new();
        List<ChatMessage> input = [new(ChatRole.User, "Old"), new(ChatRole.User, "Keep")];
        await provider.InvokingAsync(new(mockAgent.Object, session, new AIContext { Messages = input }));
        if (serializeSession)
        {
            session = new(AgentSessionStateBag.Deserialize(session.StateBag.Serialize()));
        }

        ((TextContent)input[0].Contents[0]).Text = "Edited";
        input.Add(new(ChatRole.User, "New"));

        // Act
        await provider.InvokingAsync(new(mockAgent.Object, session, new AIContext { Messages = input }));

        // Assert — the reducer sees the changed original input, rather than the stale retained subset.
        Assert.Equal(["Edited", "Keep", "New"], reducer.Inputs[1].Select(message => message.Text));
    }

    [Fact]
    public async Task InvokingAsyncStoresFixedSizeFingerprintAfterReductionAsync()
    {
        // Arrange — discarded content must not be retained solely to validate future input.
        CompactionProvider provider = new(new ChatReducerCompactionStrategy(new RecordingChatReducer(), CompactionTriggers.Always));
        Mock<AIAgent> mockAgent = new() { CallBase = true };
        TestAgentSession session = new();
        string discarded = new('x', 65536);
        List<ChatMessage> input = [new(ChatRole.User, discarded), new(ChatRole.User, "Keep")];

        // Act
        await provider.InvokingAsync(new(mockAgent.Object, session, new AIContext { Messages = input }));
        var serialized = session.StateBag.Serialize();
        var state = serialized.GetProperty(provider.StateKeys[0]);

        // Assert
        Assert.Equal(44, state.GetProperty("inputprefixfingerprint").GetString()!.Length);
        Assert.False(state.TryGetProperty("reducedinputprefix", out _));
        Assert.DoesNotContain(discarded, serialized.GetRawText());
        Assert.True(serialized.GetRawText().Length < 2048);
    }

    [Fact]
    public async Task InvokingAsyncPreservesToolExclusionAfterSessionSerializationAsync()
    {
        // Arrange — serialized tool payload values may deserialize as JsonElement instead of their original CLR types.
        CompactionProvider provider = new(new TruncationCompactionStrategy(CompactionTriggers.TokensExceed(100000)));
        Mock<AIAgent> mockAgent = new() { CallBase = true };
        TestAgentSession session = new();
        List<ChatMessage> firstInput =
        [
            new(ChatRole.Assistant, [new FunctionCallContent("call-1", "lookup", new Dictionary<string, object?> { ["query"] = "Seattle" })]),
            new(ChatRole.Tool, [new FunctionResultContent("call-1", 123)]),
            new(ChatRole.User, "Question"),
        ];
        CompactionMessageIndex index = CompactionMessageIndex.Create(firstInput);
        index.Groups[0].IsExcluded = true;
        CompactionProvider.State state = new()
        {
            MessageGroups = [.. index.Groups],
            ProcessedInputMessageCount = index.ProcessedInputMessageCount,
            InputSummaryGroupIndices = index.InputSummaryGroupIndices,
            InputPrefixFingerprint = index.InputPrefixFingerprint,
        };
        session.StateBag.SetValue(provider.StateKeys[0], state, AgentJsonUtilities.DefaultOptions);
        TestAgentSession restoredSession = new(AgentSessionStateBag.Deserialize(session.StateBag.Serialize()));
        List<ChatMessage> appended = [.. firstInput, new(ChatRole.User, "Follow-up")];

        // Act
        AIContext result = await provider.InvokingAsync(new(mockAgent.Object, restoredSession, new AIContext { Messages = appended }));

        // Assert — unchanged tool history remains excluded and only the new user message is appended.
        Assert.Equal(["Question", "Follow-up"], result.Messages!.Select(message => message.Text));
    }

    [Fact]
    public async Task InvokingAsyncKeepsEmptyReducedHistoryWhenInputIsAppendedAsync()
    {
        // Arrange — an empty reduction still needs its saved input boundary on the next turn.
        RecordingChatReducer reducer = new(keepLastMessage: false);
        CompactionProvider provider = new(new ChatReducerCompactionStrategy(reducer, CompactionTriggers.Always));
        Mock<AIAgent> mockAgent = new() { CallBase = true };
        TestAgentSession session = new();
        List<ChatMessage> firstInput = [new(ChatRole.User, "A"), new(ChatRole.Assistant, "B")];
        await provider.InvokingAsync(new(mockAgent.Object, session, new AIContext { Messages = firstInput }));
        var serializedState = session.StateBag.Serialize();
        Assert.Equal(0, serializedState.GetProperty(provider.StateKeys[0]).GetProperty("messagegroups").GetArrayLength());
        Assert.Equal(2, serializedState.GetProperty(provider.StateKeys[0]).GetProperty("processedinputmessagecount").GetInt32());
        TestAgentSession unchangedSession = new(AgentSessionStateBag.Deserialize(serializedState));
        TestAgentSession restoredSession = new(AgentSessionStateBag.Deserialize(serializedState));
        List<ChatMessage> appended = [new(ChatRole.User, "A"), new(ChatRole.Assistant, "B"), new(ChatRole.User, "C")];

        // Act
        AIContext unchangedResult = await provider.InvokingAsync(new(mockAgent.Object, unchangedSession, new AIContext { Messages = firstInput }));
        AIContext result = await provider.InvokingAsync(new(mockAgent.Object, restoredSession, new AIContext { Messages = appended }));

        // Assert — only C is indexed; a single non-system group does not trigger reduction.
        Assert.Empty(unchangedResult.Messages!);
        Assert.Equal(["C"], result.Messages!.Select(message => message.Text));
        Assert.Single(reducer.Inputs);
        Assert.Equal(3, restoredSession.StateBag.Serialize().GetProperty(provider.StateKeys[0]).GetProperty("processedinputmessagecount").GetInt32());

        // Act & Assert — after another append, the reducer sees only the retained C and new D.
        TestAgentSession thirdSession = new(AgentSessionStateBag.Deserialize(restoredSession.StateBag.Serialize()));
        List<ChatMessage> thirdInput = [.. appended, new(ChatRole.Assistant, "D")];
        AIContext thirdResult = await provider.InvokingAsync(new(mockAgent.Object, thirdSession, new AIContext { Messages = thirdInput }));
        Assert.Empty(thirdResult.Messages!);
        Assert.Equal(["C", "D"], reducer.Inputs[1].Select(message => message.Text));
    }

    [Fact]
    public async Task InvokingAsyncWithNonListEnumerableCreatesListCopyAsync()
    {
        // Arrange — pass IEnumerable (not List<ChatMessage>) to exercise the list copy branch
        TruncationCompactionStrategy strategy = new(CompactionTriggers.TokensExceed(100000));
        CompactionProvider provider = new(strategy);

        Mock<AIAgent> mockAgent = new() { CallBase = true };
        TestAgentSession session = new();

        // Use an IEnumerable (not a List) to trigger the copy path
        IEnumerable<ChatMessage> messages = [new ChatMessage(ChatRole.User, "Hello")];

        AIContextProvider.InvokingContext context = new(
            mockAgent.Object,
            session,
            new AIContext { Messages = messages });

        // Act
        AIContext result = await provider.InvokingAsync(context);

        // Assert
        Assert.NotNull(result.Messages);
        List<ChatMessage> resultList = [.. result.Messages!];
        Assert.Single(resultList);
        Assert.Equal("Hello", resultList[0].Text);
    }

    [Fact]
    public async Task CompactAsyncThrowsOnNullStrategyAsync()
    {
        List<ChatMessage> messages = [new ChatMessage(ChatRole.User, "Hello")];

        await Assert.ThrowsAsync<ArgumentNullException>(() => CompactionProvider.CompactAsync(null!, messages));
    }

    [Fact]
    public async Task CompactAsyncReturnsAllMessagesWhenTriggerDoesNotFireAsync()
    {
        // Arrange — trigger never fires → no compaction
        TruncationCompactionStrategy strategy = new(CompactionTriggers.TokensExceed(100000));
        List<ChatMessage> messages =
        [
            new ChatMessage(ChatRole.User, "Q1"),
            new ChatMessage(ChatRole.Assistant, "A1"),
            new ChatMessage(ChatRole.User, "Q2"),
        ];

        // Act
        IEnumerable<ChatMessage> result = await CompactionProvider.CompactAsync(strategy, messages);

        // Assert — all messages preserved
        List<ChatMessage> resultList = [.. result];
        Assert.Equal(messages.Count, resultList.Count);
        Assert.Equal("Q1", resultList[0].Text);
        Assert.Equal("A1", resultList[1].Text);
        Assert.Equal("Q2", resultList[2].Text);
    }

    [Fact]
    public async Task CompactAsyncReducesMessagesWhenTriggeredAsync()
    {
        // Arrange — strategy that always triggers and keeps only 1 group
        TruncationCompactionStrategy strategy = new(CompactionTriggers.Always, minimumPreservedGroups: 1);
        List<ChatMessage> messages =
        [
            new ChatMessage(ChatRole.User, "Q1"),
            new ChatMessage(ChatRole.Assistant, "A1"),
            new ChatMessage(ChatRole.User, "Q2"),
        ];

        // Act
        IEnumerable<ChatMessage> result = await CompactionProvider.CompactAsync(strategy, messages);

        // Assert — compaction should have reduced the message count
        List<ChatMessage> resultList = [.. result];
        Assert.True(resultList.Count < messages.Count);
    }

    [Fact]
    public async Task CompactAsyncHandlesEmptyMessageListAsync()
    {
        // Arrange
        TruncationCompactionStrategy strategy = new(CompactionTriggers.Always, minimumPreservedGroups: 1);
        List<ChatMessage> messages = [];

        // Act
        IEnumerable<ChatMessage> result = await CompactionProvider.CompactAsync(strategy, messages);

        // Assert
        Assert.Empty(result);
    }

    [Fact]
    public async Task CompactAsyncWorksWithNonListEnumerableAsync()
    {
        // Arrange — IEnumerable (not a List<ChatMessage>) to exercise the list copy branch
        TruncationCompactionStrategy strategy = new(CompactionTriggers.TokensExceed(100000));
        IEnumerable<ChatMessage> messages = [new ChatMessage(ChatRole.User, "Hello")];

        // Act
        IEnumerable<ChatMessage> result = await CompactionProvider.CompactAsync(strategy, messages);

        // Assert
        List<ChatMessage> resultList = [.. result];
        Assert.Single(resultList);
        Assert.Equal("Hello", resultList[0].Text);
    }

    [Fact]
    public void CompactionStateAssignment()
    {
        // Arrange
        CompactionProvider.State state = new();

        // Assert
        Assert.NotNull(state.MessageGroups);
        Assert.Empty(state.MessageGroups);

        // Act
        state.MessageGroups = [new CompactionMessageGroup(CompactionGroupKind.User, [], 0, 0, 0)];

        // Assert
        Assert.Single(state.MessageGroups);
    }

    [Fact]
    public async Task InvokingAsyncMarksOnlyPreviouslySeenMessagesAsChatHistoryAsync()
    {
        // Arrange — no-compaction strategy so we can observe marking behavior only
        TruncationCompactionStrategy strategy = new(CompactionTriggers.TokensExceed(100000));
        CompactionProvider provider = new(strategy);

        Mock<AIAgent> mockAgent = new() { CallBase = true };
        TestAgentSession session = new();

        // --- First invocation: [Q1, A1, Q2] ---
        ChatMessage q1 = new(ChatRole.User, "Q1");
        ChatMessage a1 = new(ChatRole.Assistant, "A1");
        ChatMessage q2 = new(ChatRole.User, "Q2");

        AIContextProvider.InvokingContext context1 = new(
            mockAgent.Object,
            session,
            new AIContext { Messages = new List<ChatMessage> { q1, a1, q2 } });

        AIContext result1 = await provider.InvokingAsync(context1);

        // Assert — on first invocation, no messages should be marked as ChatHistory
        List<ChatMessage> resultList1 = [.. result1.Messages!];
        Assert.Equal(3, resultList1.Count);
        foreach (ChatMessage message in resultList1)
        {
            Assert.NotEqual(AgentRequestMessageSourceType.ChatHistory, message.GetAgentRequestMessageSourceType());
        }

        // --- Second invocation: [Q1, A1, Q2, A2, Q3] ---
        ChatMessage a2 = new(ChatRole.Assistant, "A2");
        ChatMessage q3 = new(ChatRole.User, "Q3");

        AIContextProvider.InvokingContext context2 = new(
            mockAgent.Object,
            session,
            new AIContext { Messages = new List<ChatMessage> { q1, a1, q2, a2, q3 } });

        AIContext result2 = await provider.InvokingAsync(context2);

        // Assert — messages from the first invocation should be marked as ChatHistory,
        // while new messages should not.
        List<ChatMessage> resultList2 = [.. result2.Messages!];
        Assert.Equal(5, resultList2.Count);

        // Q1, A1, Q2 were already in the provider state — they should be ChatHistory
        Assert.Equal(AgentRequestMessageSourceType.ChatHistory, resultList2[0].GetAgentRequestMessageSourceType());
        Assert.Equal(AgentRequestMessageSourceType.ChatHistory, resultList2[1].GetAgentRequestMessageSourceType());
        Assert.Equal(AgentRequestMessageSourceType.ChatHistory, resultList2[2].GetAgentRequestMessageSourceType());

        // A2, Q3 are new to the provider — they should NOT be ChatHistory
        Assert.NotEqual(AgentRequestMessageSourceType.ChatHistory, resultList2[3].GetAgentRequestMessageSourceType());
        Assert.NotEqual(AgentRequestMessageSourceType.ChatHistory, resultList2[4].GetAgentRequestMessageSourceType());

        // --- Third invocation: [Q1, A1, Q2, A2, Q3, A3, Q4] ---
        ChatMessage a3 = new(ChatRole.Assistant, "A3");
        ChatMessage q4 = new(ChatRole.User, "Q4");

        AIContextProvider.InvokingContext context3 = new(
            mockAgent.Object,
            session,
            new AIContext { Messages = new List<ChatMessage> { q1, a1, q2, a2, q3, a3, q4 } });

        AIContext result3 = await provider.InvokingAsync(context3);

        // Assert — all previously seen messages should be ChatHistory, only brand-new ones should not
        List<ChatMessage> resultList3 = [.. result3.Messages!];
        Assert.Equal(7, resultList3.Count);

        // Q1, A1, Q2, A2, Q3 were already in the provider state — they should be ChatHistory
        for (int i = 0; i < 5; i++)
        {
            Assert.Equal(AgentRequestMessageSourceType.ChatHistory, resultList3[i].GetAgentRequestMessageSourceType());
        }

        // A3, Q4 are new — they should NOT be ChatHistory
        Assert.NotEqual(AgentRequestMessageSourceType.ChatHistory, resultList3[5].GetAgentRequestMessageSourceType());
        Assert.NotEqual(AgentRequestMessageSourceType.ChatHistory, resultList3[6].GetAgentRequestMessageSourceType());
    }

    private sealed class RecordingChatReducer : IChatReducer
    {
        private readonly bool _keepLastMessage;

        public RecordingChatReducer(bool keepLastMessage = true)
        {
            this._keepLastMessage = keepLastMessage;
        }

        public List<List<ChatMessage>> Inputs { get; } = [];

        public Task<IEnumerable<ChatMessage>> ReduceAsync(IEnumerable<ChatMessage> messages, System.Threading.CancellationToken cancellationToken = default)
        {
            List<ChatMessage> input = [.. messages];
            this.Inputs.Add(input);
            return Task.FromResult<IEnumerable<ChatMessage>>(this._keepLastMessage ? [input[^1]] : []);
        }
    }

    private sealed class TestAgentSession : AgentSession
    {
        public TestAgentSession()
        {
        }

        public TestAgentSession(AgentSessionStateBag stateBag)
            : base(stateBag)
        {
        }
    }
}
