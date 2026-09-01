// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
using System.Text.Json.Serialization;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Compaction;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.UnitTests.Compaction;

/// <summary>
/// Contains tests for the <see cref="ToolResultReductionStrategy"/> class.
/// </summary>
public partial class ToolResultReductionStrategyTests
{
    [Fact]
    public async Task CompactAsyncTriggerNotMetReturnsFalseAsync()
    {
        // Arrange — trigger requires > 1000 tokens
        ToolResultReductionStrategy strategy = new(
            new Dictionary<string, Func<object?, object?>>
            {
                ["fn"] = result => "reduced",
            },
            CompactionTriggers.TokensExceed(1000));

        CompactionMessageIndex index = CompactionMessageIndex.Create(
        [
            new ChatMessage(ChatRole.User, "Q1"),
            new ChatMessage(ChatRole.Assistant, [new FunctionCallContent("c1", "fn")]),
            new ChatMessage(ChatRole.Tool, [new FunctionResultContent("c1", "short")]),
        ]);

        // Act
        bool result = await strategy.CompactAsync(index);

        // Assert
        Assert.False(result);
    }

    [Fact]
    public async Task CompactAsyncAppliesReducerToRegisteredToolAsync()
    {
        // Arrange — register a reducer that uppercases weather results
        ToolResultReductionStrategy strategy = new(
            new Dictionary<string, Func<object?, object?>>
            {
                ["get_weather"] = result => result?.ToString()!.ToUpperInvariant(),
            },
            trigger: _ => true);

        CompactionMessageIndex index = CompactionMessageIndex.Create(
        [
            new ChatMessage(ChatRole.User, "Q1"),
            new ChatMessage(ChatRole.Assistant, [new FunctionCallContent("c1", "get_weather")]),
            new ChatMessage(ChatRole.Tool, [new FunctionResultContent("c1", "Sunny and 72°F")]),
        ]);

        // Act
        bool result = await strategy.CompactAsync(index);

        // Assert — result reduced but message structure preserved
        Assert.True(result);

        List<ChatMessage> included = [.. index.GetIncludedMessages()];
        Assert.Equal(3, included.Count);
        Assert.Equal(ChatRole.User, included[0].Role);
        Assert.Equal(ChatRole.Assistant, included[1].Role);
        Assert.Equal(ChatRole.Tool, included[2].Role);

        FunctionResultContent? frc = included[2].Contents.OfType<FunctionResultContent>().SingleOrDefault();
        Assert.NotNull(frc);
        Assert.Equal("SUNNY AND 72°F", frc.Result?.ToString());
    }

    [Fact]
    public async Task CompactAsyncPreservesUnregisteredToolResultsAsync()
    {
        // Arrange — reducer registered for search_docs only; get_weather is unregistered
        ToolResultReductionStrategy strategy = new(
            new Dictionary<string, Func<object?, object?>>
            {
                ["search_docs"] = result => $"({result?.ToString()!.Split('\n').Length} results)",
            },
            trigger: _ => true);

        ChatMessage multiToolCall = new(ChatRole.Assistant,
        [
            new FunctionCallContent("c1", "search_docs"),
            new FunctionCallContent("c2", "get_weather"),
        ]);

        CompactionMessageIndex index = CompactionMessageIndex.Create(
        [
            new ChatMessage(ChatRole.User, "Q1"),
            multiToolCall,
            new ChatMessage(ChatRole.Tool, [new FunctionResultContent("c1", "doc1\ndoc2\ndoc3")]),
            new ChatMessage(ChatRole.Tool, [new FunctionResultContent("c2", "Sunny")]),
        ]);

        // Act
        await strategy.CompactAsync(index);

        // Assert — search_docs reduced, get_weather preserved as-is
        List<ChatMessage> included = [.. index.GetIncludedMessages()];
        Assert.Equal(4, included.Count);

        FunctionResultContent searchResult = included[2].Contents.OfType<FunctionResultContent>().Single();
        Assert.Equal("(3 results)", searchResult.Result?.ToString());

        FunctionResultContent weatherResult = included[3].Contents.OfType<FunctionResultContent>().Single();
        Assert.Equal("Sunny", weatherResult.Result?.ToString());
    }

    [Fact]
    public async Task CompactAsyncPreservesMessageStructureAsync()
    {
        // Arrange — reducer that truncates long results
        ToolResultReductionStrategy strategy = new(
            new Dictionary<string, Func<object?, object?>>
            {
                ["retrieval_api"] = result => { var s = result?.ToString()!; return s.Length > 20 ? s[..20] + "..." : s; },
            },
            trigger: _ => true);

        CompactionMessageIndex index = CompactionMessageIndex.Create(
        [
            new ChatMessage(ChatRole.User, "Find relevant documents"),
            new ChatMessage(ChatRole.Assistant, [new FunctionCallContent("c1", "retrieval_api")]),
            new ChatMessage(ChatRole.Tool, [new FunctionResultContent("c1", "This is a very long result that exceeds twenty characters")]),
        ]);

        // Act
        await strategy.CompactAsync(index);

        // Assert — structure preserved: User + Assistant (with FunctionCallContent) + Tool (with FunctionResultContent)
        List<ChatMessage> included = [.. index.GetIncludedMessages()];
        Assert.Equal(3, included.Count);
        Assert.Equal(ChatRole.Assistant, included[1].Role);
        Assert.IsType<FunctionCallContent>(included[1].Contents[0]);
        Assert.Equal(ChatRole.Tool, included[2].Role);

        FunctionResultContent frc = included[2].Contents.OfType<FunctionResultContent>().Single();
        Assert.Equal("c1", frc.CallId);
        Assert.Equal("This is a very long ...", frc.Result?.ToString());
    }

    [Fact]
    public async Task CompactAsyncReducesCurrentTurnByDefaultAsync()
    {
        // Arrange — minimumPreservedGroups defaults to 0, so current turn is eligible
        ToolResultReductionStrategy strategy = new(
            new Dictionary<string, Func<object?, object?>>
            {
                ["fn"] = result => result?.ToString()!.ToUpperInvariant(),
            },
            trigger: _ => true);

        CompactionMessageIndex index = CompactionMessageIndex.Create(
        [
            new ChatMessage(ChatRole.User, "Q1"),
            new ChatMessage(ChatRole.Assistant, [new FunctionCallContent("c1", "fn")]),
            new ChatMessage(ChatRole.Tool, [new FunctionResultContent("c1", "hello")]),
        ]);

        // Act
        bool result = await strategy.CompactAsync(index);

        // Assert — even the only/current tool group was reduced
        Assert.True(result);
        List<ChatMessage> included = [.. index.GetIncludedMessages()];
        FunctionResultContent frc = included[2].Contents.OfType<FunctionResultContent>().Single();
        Assert.Equal("HELLO", frc.Result?.ToString());
    }

    [Fact]
    public async Task CompactAsyncPreservesRecentToolGroupsAsync()
    {
        // Arrange — protect 3 recent groups (tool group + user message = protected)
        ToolResultReductionStrategy strategy = new(
            new Dictionary<string, Func<object?, object?>>
            {
                ["fn"] = result => "SHOULD NOT APPEAR",
            },
            trigger: _ => true,
            minimumPreservedGroups: 3);

        CompactionMessageIndex index = CompactionMessageIndex.Create(
        [
            new ChatMessage(ChatRole.User, "Q1"),
            new ChatMessage(ChatRole.Assistant, [new FunctionCallContent("c1", "fn")]),
            new ChatMessage(ChatRole.Tool, [new FunctionResultContent("c1", "result")]),
            new ChatMessage(ChatRole.User, "Q2"),
        ]);

        // Act
        bool result = await strategy.CompactAsync(index);

        // Assert — all groups in protected window, nothing reduced
        Assert.False(result);
    }

    [Fact]
    public async Task CompactAsyncOnlyTargetsGroupsWithRegisteredReducersAsync()
    {
        // Arrange — reducer for search_docs only; get_weather-only group is skipped
        ToolResultReductionStrategy strategy = new(
            new Dictionary<string, Func<object?, object?>>
            {
                ["search_docs"] = result => "reduced",
            },
            trigger: _ => true);

        CompactionMessageIndex index = CompactionMessageIndex.Create(
        [
            new ChatMessage(ChatRole.User, "Q1"),
            new ChatMessage(ChatRole.Assistant, [new FunctionCallContent("c1", "get_weather")]),
            new ChatMessage(ChatRole.Tool, [new FunctionResultContent("c1", "Sunny")]),
            new ChatMessage(ChatRole.User, "Q2"),
            new ChatMessage(ChatRole.Assistant, [new FunctionCallContent("c2", "search_docs")]),
            new ChatMessage(ChatRole.Tool, [new FunctionResultContent("c2", "doc1")]),
        ]);

        // Act
        bool result = await strategy.CompactAsync(index);

        // Assert — only search_docs group reduced; get_weather group untouched
        Assert.True(result);

        int reducedToolGroups = 0;
        int preservedToolGroups = 0;
        foreach (CompactionMessageGroup group in index.Groups)
        {
            if (group.Kind == CompactionGroupKind.ToolCall)
            {
                if (group.IsExcluded)
                {
                    reducedToolGroups++;
                }
                else
                {
                    preservedToolGroups++;
                }
            }
        }

        Assert.Equal(1, reducedToolGroups);
        Assert.Equal(2, preservedToolGroups); // get_weather unchanged + search_docs reduced replacement
    }

    [Fact]
    public async Task CompactAsyncTargetStopsReducingEarlyAsync()
    {
        // Arrange — 2 eligible tool groups, target met after first reduction
        int reduceCount = 0;
        bool TargetAfterOne(CompactionMessageIndex _) => ++reduceCount >= 1;

        ToolResultReductionStrategy strategy = new(
            new Dictionary<string, Func<object?, object?>>
            {
                ["fn1"] = result => "reduced1",
                ["fn2"] = result => "reduced2",
            },
            trigger: _ => true,
            target: TargetAfterOne);

        CompactionMessageIndex index = CompactionMessageIndex.Create(
        [
            new ChatMessage(ChatRole.User, "Q1"),
            new ChatMessage(ChatRole.Assistant, [new FunctionCallContent("c1", "fn1")]),
            new ChatMessage(ChatRole.Tool, [new FunctionResultContent("c1", "result1")]),
            new ChatMessage(ChatRole.User, "Q2"),
            new ChatMessage(ChatRole.Assistant, [new FunctionCallContent("c2", "fn2")]),
            new ChatMessage(ChatRole.Tool, [new FunctionResultContent("c2", "result2")]),
        ]);

        // Act
        bool result = await strategy.CompactAsync(index);

        // Assert — only first tool group reduced
        Assert.True(result);

        int reducedToolGroups = 0;
        foreach (CompactionMessageGroup group in index.Groups)
        {
            if (group.IsExcluded && group.Kind == CompactionGroupKind.ToolCall)
            {
                reducedToolGroups++;
            }
        }

        Assert.Equal(1, reducedToolGroups);
    }

    [Fact]
    public async Task CompactAsyncPreservesSystemMessagesAsync()
    {
        // Arrange
        ToolResultReductionStrategy strategy = new(
            new Dictionary<string, Func<object?, object?>>
            {
                ["fn"] = result => "reduced",
            },
            trigger: _ => true);

        CompactionMessageIndex index = CompactionMessageIndex.Create(
        [
            new ChatMessage(ChatRole.System, "You are helpful."),
            new ChatMessage(ChatRole.User, "Q1"),
            new ChatMessage(ChatRole.Assistant, [new FunctionCallContent("c1", "fn")]),
            new ChatMessage(ChatRole.Tool, [new FunctionResultContent("c1", "result")]),
        ]);

        // Act
        await strategy.CompactAsync(index);

        // Assert
        List<ChatMessage> included = [.. index.GetIncludedMessages()];
        Assert.Equal("You are helpful.", included[0].Text);
        Assert.False(index.Groups[0].IsExcluded);
    }

    [Fact]
    public async Task CompactAsyncNoToolGroupsReturnsFalseAsync()
    {
        // Arrange — trigger fires but no tool groups to reduce
        ToolResultReductionStrategy strategy = new(
            new Dictionary<string, Func<object?, object?>>
            {
                ["fn"] = result => "reduced",
            },
            trigger: _ => true);

        CompactionMessageIndex index = CompactionMessageIndex.Create(
        [
            new ChatMessage(ChatRole.User, "Hello"),
            new ChatMessage(ChatRole.Assistant, "Hi!"),
        ]);

        // Act
        bool result = await strategy.CompactAsync(index);

        // Assert
        Assert.False(result);
    }

    [Fact]
    public async Task CompactAsyncSkipsPreExcludedAndSystemGroupsAsync()
    {
        // Arrange — pre-excluded and system groups in the enumeration
        ToolResultReductionStrategy strategy = new(
            new Dictionary<string, Func<object?, object?>>
            {
                ["fn"] = result => "reduced",
            },
            CompactionTriggers.Always);

        List<ChatMessage> messages =
        [
            new ChatMessage(ChatRole.System, "System prompt"),
            new ChatMessage(ChatRole.User, "Q0"),
            new ChatMessage(ChatRole.Assistant, [new FunctionCallContent("c1", "fn")]),
            new ChatMessage(ChatRole.Tool, [new FunctionResultContent("c1", "Result 1")]),
            new ChatMessage(ChatRole.User, "Q1"),
        ];

        CompactionMessageIndex index = CompactionMessageIndex.Create(messages);
        // Pre-exclude the last user group
        index.Groups[index.Groups.Count - 1].IsExcluded = true;

        // Act
        bool result = await strategy.CompactAsync(index);

        // Assert — system never excluded, pre-excluded skipped
        Assert.True(result);
        Assert.False(index.Groups[0].IsExcluded); // System stays
    }

    [Fact]
    public async Task CompactAsyncComposesWithCompactionInPipelineAsync()
    {
        // Arrange — reduction first, then compaction in a pipeline
        ToolResultReductionStrategy reductionStrategy = new(
            new Dictionary<string, Func<object?, object?>>
            {
                ["search"] = result => $"[{result?.ToString()!.Split('\n').Length} results]",
            },
            trigger: _ => true);

        ToolResultCompactionStrategy compactionStrategy = new(
            trigger: _ => true,
            minimumPreservedGroups: 1);

        PipelineCompactionStrategy pipeline = new(reductionStrategy, compactionStrategy);

        CompactionMessageIndex index = CompactionMessageIndex.Create(
        [
            new ChatMessage(ChatRole.User, "Q1"),
            new ChatMessage(ChatRole.Assistant, [new FunctionCallContent("c1", "search")]),
            new ChatMessage(ChatRole.Tool, [new FunctionResultContent("c1", "doc1\ndoc2\ndoc3")]),
            new ChatMessage(ChatRole.User, "Q2"),
        ]);

        // Act
        await pipeline.CompactAsync(index);

        // Assert — reduction applied first (3 results), then compacted to YAML
        List<ChatMessage> included = [.. index.GetIncludedMessages()];
        Assert.Equal(3, included.Count); // Q1, collapsed summary, Q2
        Assert.Contains("[3 results]", included[1].Text);
        Assert.Contains("[Tool Calls]", included[1].Text);
    }

    [Fact]
    public async Task CompactAsyncRetrievalApiSelectsHighestRelevantWithinBudgetAsync()
    {
        // Arrange — simulate a retrieval API returning JSON chunks with relevance scores.
        // The reducer deserializes, orders by relevance, selects top chunks within a
        // character budget, and re-serializes — the canonical RAG compaction scenario.
        const string RetrievalResult =
            """
            [
              {"chunk": "Irrelevant filler content that wastes tokens", "relevance": 0.2},
              {"chunk": "Highly relevant answer about the product pricing model", "relevance": 0.95},
              {"chunk": "Somewhat relevant context about product history", "relevance": 0.6},
              {"chunk": "Very relevant details about current pricing tiers", "relevance": 0.9},
              {"chunk": "Noise from unrelated document section", "relevance": 0.1},
              {"chunk": "Moderately relevant competitor comparison", "relevance": 0.7}
            ]
            """;

        // Only keep chunks whose combined text fits within ~100 chars.
        // Top-2 by relevance: 0.95 (55 chars) + 0.90 (49 chars) = 104 chars — over budget.
        // So only the top-1 (0.95) fits.
        const int CharBudget = 100;

        ToolResultReductionStrategy strategy = new(
            new Dictionary<string, Func<object?, object?>>
            {
                ["retrieval_api"] = result =>
                {
                    var chunks = JsonSerializer.Deserialize(result?.ToString()!, ChunkSerializerContext.Default.ListChunkResult)!;
                    var selected = new List<ChunkResult>();
                    int totalChars = 0;

                    foreach (var chunk in chunks.OrderByDescending(c => c.Relevance))
                    {
                        if (totalChars + chunk.Chunk.Length > CharBudget)
                        {
                            break;
                        }

                        selected.Add(chunk);
                        totalChars += chunk.Chunk.Length;
                    }

                    return JsonSerializer.Serialize(selected, ChunkSerializerContext.Default.ListChunkResult);
                },
            },
            trigger: _ => true);

        CompactionMessageIndex index = CompactionMessageIndex.Create(
        [
            new ChatMessage(ChatRole.User, "What are the pricing tiers?"),
            new ChatMessage(ChatRole.Assistant, [new FunctionCallContent("c1", "retrieval_api")]),
            new ChatMessage(ChatRole.Tool, [new FunctionResultContent("c1", RetrievalResult)]),
        ]);

        // Act
        bool result = await strategy.CompactAsync(index);

        // Assert — reduced to only the highest-relevance chunk(s) within budget
        Assert.True(result);

        List<ChatMessage> included = [.. index.GetIncludedMessages()];
        Assert.Equal(3, included.Count);
        Assert.Equal(ChatRole.Tool, included[2].Role);

        FunctionResultContent frc = included[2].Contents.OfType<FunctionResultContent>().Single();
        string reducedJson = frc.Result!.ToString()!;

        var reducedChunks = JsonSerializer.Deserialize(reducedJson, ChunkSerializerContext.Default.ListChunkResult)!;

        // Should contain only the top chunk(s) that fit the budget
        Assert.True(reducedChunks.Count >= 1, "Should select at least one chunk");
        Assert.True(reducedChunks.All(c => c.Relevance >= 0.9), "Should only contain high-relevance chunks");
        Assert.Equal(0.95, reducedChunks[0].Relevance);

        // Verify total is within budget
        int totalLength = reducedChunks.Sum(c => c.Chunk.Length);
        Assert.True(totalLength <= CharBudget, $"Total chunk length {totalLength} should be within budget {CharBudget}");
    }

    [Fact]
    public async Task CompactAsyncPreservesMessageMetadataAsync()
    {
        // Arrange — message has AuthorName and MessageId that should survive reduction
        ToolResultReductionStrategy strategy = new(
            new Dictionary<string, Func<object?, object?>>
            {
                ["fn"] = result => "reduced",
            },
            trigger: _ => true);

        ChatMessage toolResultMessage = new(ChatRole.Tool, [new FunctionResultContent("c1", "original")])
        {
            AuthorName = "tool-author",
            MessageId = "msg-42",
        };

        CompactionMessageIndex index = CompactionMessageIndex.Create(
        [
            new ChatMessage(ChatRole.User, "Q1"),
            new ChatMessage(ChatRole.Assistant, [new FunctionCallContent("c1", "fn")]),
            toolResultMessage,
        ]);

        // Act
        await strategy.CompactAsync(index);

        // Assert — metadata preserved on the reduced message
        List<ChatMessage> included = [.. index.GetIncludedMessages()];
        ChatMessage reduced = included[2];
        Assert.Equal("tool-author", reduced.AuthorName);
        Assert.Equal("msg-42", reduced.MessageId);

        FunctionResultContent frc = reduced.Contents.OfType<FunctionResultContent>().Single();
        Assert.Equal("reduced", frc.Result?.ToString());
    }

    [Fact]
    public async Task CompactAsyncDoesNotReReduceAlreadyReducedGroupsAsync()
    {
        // Arrange — calling CompactAsync twice should not re-reduce
        int callCount = 0;
        ToolResultReductionStrategy strategy = new(
            new Dictionary<string, Func<object?, object?>>
            {
                ["fn"] = result => { callCount++; return $"reduced-{callCount}"; },
            },
            trigger: _ => true);

        CompactionMessageIndex index = CompactionMessageIndex.Create(
        [
            new ChatMessage(ChatRole.User, "Q1"),
            new ChatMessage(ChatRole.Assistant, [new FunctionCallContent("c1", "fn")]),
            new ChatMessage(ChatRole.Tool, [new FunctionResultContent("c1", "original")]),
        ]);

        // Act — reduce twice
        bool first = await strategy.CompactAsync(index);
        bool second = await strategy.CompactAsync(index);

        // Assert — first call reduces, second is a no-op
        Assert.True(first);
        Assert.False(second);
        Assert.Equal(1, callCount);

        List<ChatMessage> included = [.. index.GetIncludedMessages()];
        FunctionResultContent frc = included[2].Contents.OfType<FunctionResultContent>().Single();
        Assert.Equal("reduced-1", frc.Result?.ToString());
    }

    [Fact]
    public async Task CompactAsyncSkipsGroupWithCallButNoMatchingResultAsync()
    {
        // Arrange — group has a registered FunctionCallContent but no FunctionResultContent
        // (tool result is plain text, not FunctionResultContent)
        ToolResultReductionStrategy strategy = new(
            new Dictionary<string, Func<object?, object?>>
            {
                ["fn"] = result => "should not be called",
            },
            trigger: _ => true);

        CompactionMessageIndex index = CompactionMessageIndex.Create(
        [
            new ChatMessage(ChatRole.User, "Q1"),
            new ChatMessage(ChatRole.Assistant, [new FunctionCallContent("c1", "fn")]),
            new ChatMessage(ChatRole.Tool, "Plain text result without FunctionResultContent"),
        ]);

        // Act
        bool result = await strategy.CompactAsync(index);

        // Assert — group is ineligible, no reduction
        Assert.False(result);
    }

    /// <summary>
    /// Represents a retrieval API chunk with relevance score, matching the JSON structure
    /// returned by a typical RAG tool.
    /// </summary>
    private sealed class ChunkResult
    {
        [JsonPropertyName("chunk")]
        public string Chunk { get; set; } = string.Empty;

        [JsonPropertyName("relevance")]
        public double Relevance { get; set; }
    }

    [JsonSerializable(typeof(List<ChunkResult>))]
    private sealed partial class ChunkSerializerContext : JsonSerializerContext;
}
