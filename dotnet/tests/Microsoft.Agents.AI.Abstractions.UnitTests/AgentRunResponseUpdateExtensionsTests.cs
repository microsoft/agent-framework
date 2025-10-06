// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Abstractions.UnitTests;

public class AgentRunResponseUpdateExtensionsTests
{
    public static IEnumerable<object[]> ToAgentRunResponseCoalescesVariousSequenceAndGapLengthsMemberData()
    {
        foreach (bool useAsync in new[] { false, true })
        {
            for (int numSequences = 1; numSequences <= 3; numSequences++)
            {
                for (int sequenceLength = 1; sequenceLength <= 3; sequenceLength++)
                {
                    for (int gapLength = 1; gapLength <= 3; gapLength++)
                    {
                        foreach (bool gapBeginningEnd in new[] { false, true })
                        {
                            yield return new object[] { useAsync, numSequences, sequenceLength, gapLength, false };
                        }
                    }
                }
            }
        }
    }

    [Fact]
    public void ToAgentRunResponseWithInvalidArgsThrows() =>
        Assert.Throws<ArgumentNullException>("updates", () => ((List<AgentRunResponseUpdate>)null!).ToAgentRunResponse());

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task ToAgentRunResponseSuccessfullyCreatesResponseAsync(bool useAsync)
    {
        AgentRunResponseUpdate[] updates =
        [
            new(ChatRole.Assistant, "Hello") { ResponseId = "someResponse", MessageId = "12345", CreatedAt = new DateTimeOffset(1, 2, 3, 4, 5, 6, TimeSpan.Zero), AgentId = "agentId" },
            new(new("human"), ", ") { AuthorName = "Someone", AdditionalProperties = new() { ["a"] = "b" } },
            new(null, "world!") { CreatedAt = new DateTimeOffset(2, 2, 3, 4, 5, 6, TimeSpan.Zero), AdditionalProperties = new() { ["c"] = "d" } },

            new() { Contents = [new UsageContent(new() { InputTokenCount = 1, OutputTokenCount = 2 })] },
            new() { Contents = [new UsageContent(new() { InputTokenCount = 4, OutputTokenCount = 5 })] },
        ];

        AgentRunResponse response = useAsync ?
            updates.ToAgentRunResponse() :
            await YieldAsync(updates).ToAgentRunResponseAsync();
        Assert.NotNull(response);

        Assert.Equal("agentId", response.AgentId);

        Assert.NotNull(response.Usage);
        Assert.Equal(5, response.Usage.InputTokenCount);
        Assert.Equal(7, response.Usage.OutputTokenCount);

        Assert.Equal("someResponse", response.ResponseId);
        Assert.Equal(new DateTimeOffset(2, 2, 3, 4, 5, 6, TimeSpan.Zero), response.CreatedAt);

        Assert.Equal(2, response.Messages.Count);

        ChatMessage message = response.Messages[0];
        Assert.Equal("12345", message.MessageId);
        Assert.Equal(ChatRole.Assistant, message.Role);
        Assert.Null(message.AuthorName);
        Assert.Null(message.AdditionalProperties);
        Assert.Single(message.Contents);
        Assert.Equal("Hello", Assert.IsType<TextContent>(message.Contents[0]).Text);

        message = response.Messages[1];
        Assert.Null(message.MessageId);
        Assert.Equal(new("human"), message.Role);
        Assert.Equal("Someone", message.AuthorName);
        Assert.Single(message.Contents);
        Assert.Equal(", world!", Assert.IsType<TextContent>(message.Contents[0]).Text);

        Assert.NotNull(response.AdditionalProperties);
        Assert.Equal(2, response.AdditionalProperties.Count);
        Assert.Equal("b", response.AdditionalProperties["a"]);
        Assert.Equal("d", response.AdditionalProperties["c"]);

        Assert.Equal("Hello" + Environment.NewLine + ", world!", response.Text);
    }

    [Theory]
    [MemberData(nameof(ToAgentRunResponseCoalescesVariousSequenceAndGapLengthsMemberData))]
    public async Task ToAgentRunResponseCoalescesVariousSequenceAndGapLengthsAsync(bool useAsync, int numSequences, int sequenceLength, int gapLength, bool gapBeginningEnd)
    {
        List<AgentRunResponseUpdate> updates = [];

        List<string> expected = [];

        if (gapBeginningEnd)
        {
            AddGap();
        }

        for (int sequenceNum = 0; sequenceNum < numSequences; sequenceNum++)
        {
            StringBuilder sb = new();
            for (int i = 0; i < sequenceLength; i++)
            {
                string text = $"{(char)('A' + sequenceNum)}{i}";
                updates.Add(new(null, text));
                sb.Append(text);
            }

            expected.Add(sb.ToString());

            if (sequenceNum < numSequences - 1)
            {
                AddGap();
            }
        }

        if (gapBeginningEnd)
        {
            AddGap();
        }

        void AddGap()
        {
            for (int i = 0; i < gapLength; i++)
            {
                updates.Add(new() { Contents = [new DataContent("data:image/png;base64,aGVsbG8=")] });
            }
        }

        AgentRunResponse response = useAsync ? await YieldAsync(updates).ToAgentRunResponseAsync() : updates.ToAgentRunResponse();
        Assert.NotNull(response);

        ChatMessage message = response.Messages.Single();
        Assert.NotNull(message);

        Assert.Equal(expected.Count + (gapLength * (numSequences - 1 + (gapBeginningEnd ? 2 : 0))), message.Contents.Count);

        TextContent[] contents = message.Contents.OfType<TextContent>().ToArray();
        Assert.Equal(expected.Count, contents.Length);
        for (int i = 0; i < expected.Count; i++)
        {
            Assert.Equal(expected[i], contents[i].Text);
        }
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task ToAgentRunResponseCoalescesTextContentAndTextReasoningContentSeparatelyAsync(bool useAsync)
    {
        AgentRunResponseUpdate[] updates =
        [
            new(null, "A"),
            new(null, "B"),
            new(null, "C"),
            new() { Contents = [new TextReasoningContent("D")] },
            new() { Contents = [new TextReasoningContent("E")] },
            new() { Contents = [new TextReasoningContent("F")] },
            new(null, "G"),
            new(null, "H"),
            new() { Contents = [new TextReasoningContent("I")] },
            new() { Contents = [new TextReasoningContent("J")] },
            new(null, "K"),
            new() { Contents = [new TextReasoningContent("L")] },
            new(null, "M"),
            new(null, "N"),
            new() { Contents = [new TextReasoningContent("O")] },
            new() { Contents = [new TextReasoningContent("P")] },
        ];

        AgentRunResponse response = useAsync ? await YieldAsync(updates).ToAgentRunResponseAsync() : updates.ToAgentRunResponse();
        ChatMessage message = Assert.Single(response.Messages);
        Assert.Equal(8, message.Contents.Count);
        Assert.Equal("ABC", Assert.IsType<TextContent>(message.Contents[0]).Text);
        Assert.Equal("DEF", Assert.IsType<TextReasoningContent>(message.Contents[1]).Text);
        Assert.Equal("GH", Assert.IsType<TextContent>(message.Contents[2]).Text);
        Assert.Equal("IJ", Assert.IsType<TextReasoningContent>(message.Contents[3]).Text);
        Assert.Equal("K", Assert.IsType<TextContent>(message.Contents[4]).Text);
        Assert.Equal("L", Assert.IsType<TextReasoningContent>(message.Contents[5]).Text);
        Assert.Equal("MN", Assert.IsType<TextContent>(message.Contents[6]).Text);
        Assert.Equal("OP", Assert.IsType<TextReasoningContent>(message.Contents[7]).Text);
    }

    [Fact]
    public async Task ToAgentRunResponseUsesContentExtractedFromContentsAsync()
    {
        AgentRunResponseUpdate[] updates =
        [
            new(null, "Hello, "),
            new(null, "world!"),
            new() { Contents = [new UsageContent(new() { TotalTokenCount = 42 })] },
        ];

        AgentRunResponse response = await YieldAsync(updates).ToAgentRunResponseAsync();

        Assert.NotNull(response);

        Assert.NotNull(response.Usage);
        Assert.Equal(42, response.Usage.TotalTokenCount);

        Assert.Equal("Hello, world!", Assert.IsType<TextContent>(Assert.Single(Assert.Single(response.Messages).Contents)).Text);
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task ToAgentRunResponse_AlternativeTimestampsAsync(bool useAsync)
    {
        DateTimeOffset early = new(2024, 1, 1, 10, 0, 0, TimeSpan.Zero);
        DateTimeOffset middle = new(2024, 1, 1, 11, 0, 0, TimeSpan.Zero);
        DateTimeOffset late = new(2024, 1, 1, 12, 0, 0, TimeSpan.Zero);
        DateTimeOffset unixEpoch = new(1970, 1, 1, 0, 0, 0, TimeSpan.Zero);

        AgentRunResponseUpdate[] updates =
        [

            // Start with an early timestamp
            new(ChatRole.Tool, "a") { MessageId = "4", CreatedAt = early },

            // Unix epoch (as "null") should not overwrite
            new(null, "b") { CreatedAt = unixEpoch },

            // Newer timestamp should overwrite
            new(null, "c") { CreatedAt = middle },

            // Older timestamp should not overwrite
            new(null, "d") { CreatedAt = early },

            // Even newer timestamp should overwrite
            new(null, "e") { CreatedAt = late },

            // Unix epoch should not overwrite again
            new(null, "f") { CreatedAt = unixEpoch },

            // null should not overwrite
            new(null, "g") { CreatedAt = null },
        ];

        AgentRunResponse response = useAsync ?
            updates.ToAgentRunResponse() :
            await YieldAsync(updates).ToAgentRunResponseAsync();
        Assert.Single(response.Messages);

        Assert.Equal("abcdefg", response.Messages[0].Text);
        Assert.Equal(ChatRole.Tool, response.Messages[0].Role);
        Assert.Equal(late, response.Messages[0].CreatedAt);
        Assert.Equal(late, response.CreatedAt);
    }

    public static IEnumerable<object?[]> ToAgentRunResponse_TimestampFolding_MemberData()
    {
        // Base test cases
        var testCases = new (string? timestamp1, string? timestamp2, string? expectedTimestamp)[]
        {
            (null, null, null),
            ("2024-01-01T10:00:00Z", null, "2024-01-01T10:00:00Z"),
            (null, "2024-01-01T10:00:00Z", "2024-01-01T10:00:00Z"),
            ("2024-01-01T10:00:00Z", "2024-01-01T11:00:00Z", "2024-01-01T11:00:00Z"),
            ("2024-01-01T11:00:00Z", "2024-01-01T10:00:00Z", "2024-01-01T11:00:00Z"),
            ("2024-01-01T10:00:00Z", "1970-01-01T00:00:00Z", "2024-01-01T10:00:00Z"),
            ("1970-01-01T00:00:00Z", "2024-01-01T10:00:00Z", "2024-01-01T10:00:00Z"),
        };

        // Yield each test case twice, once for useAsync = false and once for useAsync = true
        foreach (var (timestamp1, timestamp2, expectedTimestamp) in testCases)
        {
            yield return new object?[] { false, timestamp1, timestamp2, expectedTimestamp };
            yield return new object?[] { true, timestamp1, timestamp2, expectedTimestamp };
        }
    }

    [Theory]
    [MemberData(nameof(ToAgentRunResponse_TimestampFolding_MemberData))]
    public async Task ToAgentRunResponse_TimestampFoldingAsync(bool useAsync, string? timestamp1, string? timestamp2, string? expectedTimestamp)
    {
        DateTimeOffset? first = timestamp1 is not null ? DateTimeOffset.Parse(timestamp1) : null;
        DateTimeOffset? second = timestamp2 is not null ? DateTimeOffset.Parse(timestamp2) : null;
        DateTimeOffset? expected = expectedTimestamp is not null ? DateTimeOffset.Parse(expectedTimestamp) : null;

        AgentRunResponseUpdate[] updates =
        [
            new(ChatRole.Assistant, "a") { CreatedAt = first },
            new(null, "b") { CreatedAt = second },
        ];

        AgentRunResponse response = useAsync ?
            updates.ToAgentRunResponse() :
            await YieldAsync(updates).ToAgentRunResponseAsync();

        Assert.Single(response.Messages);
        Assert.Equal("ab", response.Messages[0].Text);
        Assert.Equal(expected, response.Messages[0].CreatedAt);
        Assert.Equal(expected, response.CreatedAt);
    }

    private static async IAsyncEnumerable<AgentRunResponseUpdate> YieldAsync(IEnumerable<AgentRunResponseUpdate> updates)
    {
        foreach (AgentRunResponseUpdate update in updates)
        {
            await Task.Yield();
            yield return update;
        }
    }
}
