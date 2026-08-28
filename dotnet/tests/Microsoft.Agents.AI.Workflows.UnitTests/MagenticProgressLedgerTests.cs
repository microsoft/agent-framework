// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Text.Json;
using Microsoft.Agents.AI.Workflows.Specialized.Magentic;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Workflows.UnitTests;

public class MagenticProgressLedgerTests
{
    public record KVPair(string key);
    public record AnswerReasonPair(bool answer, string reason);

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public void Test_ExtractJson_SucceedsWhenInBlockQuote(bool isTagged)
    {
        // Arrange
        string json = isTagged
                    ? "```json\n{\"key\": \"value\"}\n```"
                    : "```{\"key\": \"value\"}```";

        string embedded = $"Some text before the JSON block.\n{json}\nSome text after the JSON block.";
        ChatMessage message = new(ChatRole.Assistant, embedded);

        // Act
        JsonElement element = message.ExtractJson();

        // Assert
        KVPair? result = element.Deserialize<KVPair>();

        Assert.NotNull(result);
        Assert.Equal("value", result.key);
    }

    [Fact]
    public void Test_ExtractJson_SucceedsWhenScanning()
    {
        // Arrange
        ChatMessage message = new(ChatRole.Assistant,
"""
    Some text before the JSON embed.
    {"key": "value"}

    Some text after the JSON embed.        
""");

        // Act
        JsonElement element = message.ExtractJson();

        // Assert
        KVPair? result = element.Deserialize<KVPair>();

        Assert.NotNull(result);
        Assert.Equal("value", result.key);
    }

    [Fact]
    public void Test_ExtractJson_FailsWhenUnbalanced()
    {
        // Arrange
        ChatMessage message = new(ChatRole.Assistant,
"""
    Some text before the JSON embed.
    {"key": { "key2": "value" }

    Some text after the JSON embed.
""");

        // Act
        void action() => _ = message.ExtractJson();

        // Assert
        Assert.ThrowsAny<Exception>(action);
    }

    [Fact]
    public void Test_ExtractJson_FailsWhenNoJson()
    {
        // Arrange
        ChatMessage message = new(ChatRole.Assistant,
"""
    Some text, without JSON
""");

        // Act
        void action() => _ = message.ExtractJson();

        // Assert
        Assert.ThrowsAny<Exception>(action);
    }

    [Fact]
    public void Test_ExtractJson_SuceedsWithQuotesBrackets()
    {
        // Arrange
        ChatMessage message = new(ChatRole.Assistant,
"""
    {"reason":"the output contained }", "answer": false}
""");

        // Act
        JsonElement element = message.ExtractJson();

        // Assert
        AnswerReasonPair? result = element.Deserialize<AnswerReasonPair>();

        Assert.NotNull(result);
        Assert.Equal("the output contained }", result.reason);
        Assert.False(result.answer);
    }

    public static readonly string TestTeamNames = string.Join(", ", ["CodingAgent", "CodeExecutor", "WebSurferAgent", "FileSurferAgent"]);

    [Fact]
    public void Test_ProgressLedgerState_IsEmptyWhenStarted()
    {
        // Arrange/Act
        MagenticProgressLedger ledger = new(TestTeamNames, []);

        // Assert
        Assert.Null(ledger.State);
        Assert.False(ledger.IsStarted);

        Assert.False(ledger.TryGetCurrentSlotValue(TestProgressLedgerState.CustomSlot1, out _));
        Assert.False(ledger.TryGetCurrentSlotValue(TestProgressLedgerState.CustomSlot2, out _));
    }

    [Theory]
    [InlineData(0, "RequiredOnly")]
    [InlineData(1, "IncludeCustom")]
    public void Test_ProgressLedgerState_IsNotEmptyWhenRestored(int caseIndex, string _)
    {
        // Arrange
        TestProgressLedgerState state = TestProgressLedgerState.Working[caseIndex];
        JsonElement element = state.ToJson();

        // Act
        MagenticProgressLedger ledger = new(TestTeamNames, [], element);

        // Assert
        Assert.Equal(element, ledger.State);
        state.Validate(ledger);
    }

    [Theory]
    [InlineData(0, "RequiredOnly")]
    [InlineData(1, "IncludeCustom")]
    public void Test_ProgressLedgerState_SwitchesToStartedWhenStateUpdates(int caseIndex, string _)
    {
        // Arrange
        MagenticProgressLedger ledger = new(TestTeamNames, []);
        TestProgressLedgerState targetState = TestProgressLedgerState.Working[caseIndex];
        JsonElement element = targetState.ToJson();
        Assert.Null(ledger.State);

        // Act
        Assert.True(ledger.TryUpdateState(element));

        // Assert
        Assert.Equal(element, ledger.State);
        targetState.Validate(ledger);
    }

    [Theory]
    [InlineData(0, "is_request_satisfied")]
    [InlineData(1, "is_in_loop")]
    [InlineData(2, "is_progress_being_made")]
    [InlineData(3, "instruction_or_question")]
    [InlineData(4, "next_speaker")]
    public void Test_ProgressLedgerState_FailsToUpdateWhenRequiredAnswersMissing(int caseIndex, string _)
    {
        // Arrange
        MagenticProgressLedger ledger = new(TestTeamNames, []);
        TestProgressLedgerState targetState = TestProgressLedgerState.MissingRequired[caseIndex];
        JsonElement element = targetState.ToJson();
        Assert.Null(ledger.State);

        // Act
        Assert.False(ledger.TryUpdateState(element));
        Assert.Null(ledger.State);
    }

    [Theory]
    [InlineData(true)]
    [InlineData(false)]
    public void Test_ProgressLedgerState_GeneratesCorrectSchema(bool includeCustom)
    {
        // Arrange
        MagenticProgressLedger ledger = new(TestTeamNames, includeCustom
                                                           ? [TestProgressLedgerState.CustomSlot1, TestProgressLedgerState.CustomSlot2]
                                                           : []);

        // Act
        (string questionBlock, string answerSchema) = ledger.FormatQuestions();

        foreach (ProgressLedgerSlot slot in ledger.Slots)
        {
            // Best-efforts validation: I do not want to make it super-brittle and check for 1:1: with the template
            // since that is effectively checking that string formatting works right to some extent.
            Assert.Contains(slot.Question, questionBlock);
            Assert.Contains(slot.Key, answerSchema);
            Assert.Contains(slot.SchemaType, answerSchema);

            if (!string.IsNullOrWhiteSpace(slot.SchemaTypeSuffix))
            {
                Assert.Contains(slot.SchemaTypeSuffix, answerSchema);
            }
        }
    }
}
