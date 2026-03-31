// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.AI.Evaluation;

namespace Microsoft.Agents.AI.UnitTests;

/// <summary>
/// Tests for the evaluation types: <see cref="LocalEvaluator"/>, <see cref="FunctionEvaluator"/>,
/// <see cref="EvalChecks"/>, and <see cref="AgentEvaluationResults"/>.
/// </summary>
public sealed class EvaluationTests
{
    private static EvalItem CreateItem(
        string query = "What is the weather?",
        string response = "The weather in Seattle is sunny and 72°F.",
        IReadOnlyList<ChatMessage>? conversation = null)
    {
        conversation ??= new List<ChatMessage>
        {
            new(ChatRole.User, query),
            new(ChatRole.Assistant, response),
        };

        return new EvalItem(query, response, conversation);
    }

    // ---------------------------------------------------------------
    // EvalItem tests
    // ---------------------------------------------------------------

    [Fact]
    public void EvalItem_Constructor_SetsProperties()
    {
        // Arrange & Act
        var item = CreateItem();

        // Assert
        Assert.Equal("What is the weather?", item.Query);
        Assert.Equal("The weather in Seattle is sunny and 72°F.", item.Response);
        Assert.Equal(2, item.Conversation.Count);
        Assert.Null(item.ExpectedOutput);
        Assert.Null(item.Context);
        Assert.Null(item.Tools);
    }

    [Fact]
    public void EvalItem_OptionalProperties_CanBeSet()
    {
        // Arrange & Act
        var item = CreateItem();
        item.ExpectedOutput = "sunny";
        item.Context = "Weather data for Seattle";

        // Assert
        Assert.Equal("sunny", item.ExpectedOutput);
        Assert.Equal("Weather data for Seattle", item.Context);
    }

    // ---------------------------------------------------------------
    // LocalEvaluator tests
    // ---------------------------------------------------------------

    [Fact]
    public async Task LocalEvaluator_WithPassingCheck_ReturnsPassedResultAsync()
    {
        // Arrange
        var evaluator = new LocalEvaluator(
            FunctionEvaluator.Create("always_pass", (string _) => true));

        var items = new List<EvalItem> { CreateItem() };

        // Act
        var results = await evaluator.EvaluateAsync(items);

        // Assert
        Assert.Equal("LocalEvaluator", results.ProviderName);
        Assert.Equal(1, results.Total);
        Assert.Equal(1, results.Passed);
        Assert.Equal(0, results.Failed);
        Assert.True(results.AllPassed);
    }

    [Fact]
    public async Task LocalEvaluator_WithFailingCheck_ReturnsFailedResultAsync()
    {
        // Arrange
        var evaluator = new LocalEvaluator(
            FunctionEvaluator.Create("always_fail", (string _) => false));

        var items = new List<EvalItem> { CreateItem() };

        // Act
        var results = await evaluator.EvaluateAsync(items);

        // Assert
        Assert.Equal(1, results.Total);
        Assert.Equal(0, results.Passed);
        Assert.Equal(1, results.Failed);
        Assert.False(results.AllPassed);
    }

    [Fact]
    public async Task LocalEvaluator_WithMultipleChecks_AllChecksRunAsync()
    {
        // Arrange
        var evaluator = new LocalEvaluator(
            FunctionEvaluator.Create("check1", (string _) => true),
            FunctionEvaluator.Create("check2", (string _) => true));

        var items = new List<EvalItem> { CreateItem() };

        // Act
        var results = await evaluator.EvaluateAsync(items);

        // Assert
        Assert.Equal(1, results.Total);
        Assert.True(results.AllPassed);
        var itemResult = results.Items[0];
        Assert.Equal(2, itemResult.Metrics.Count);
        Assert.True(itemResult.Metrics.ContainsKey("check1"));
        Assert.True(itemResult.Metrics.ContainsKey("check2"));
    }

    [Fact]
    public async Task LocalEvaluator_WithMultipleItems_EvaluatesAllAsync()
    {
        // Arrange
        var evaluator = new LocalEvaluator(
            EvalChecks.KeywordCheck("weather"));

        var items = new List<EvalItem>
        {
            CreateItem(response: "The weather is sunny."),
            CreateItem(response: "I don't know about that topic."),
        };

        // Act
        var results = await evaluator.EvaluateAsync(items);

        // Assert
        Assert.Equal(2, results.Total);
        Assert.Equal(1, results.Passed);
        Assert.Equal(1, results.Failed);
    }

    // ---------------------------------------------------------------
    // FunctionEvaluator tests
    // ---------------------------------------------------------------

    [Fact]
    public async Task FunctionEvaluator_ResponseOnly_PassesResponseAsync()
    {
        // Arrange
        var check = FunctionEvaluator.Create("length_check",
            (string response) => response.Length > 10);

        var evaluator = new LocalEvaluator(check);
        var items = new List<EvalItem> { CreateItem() };

        // Act
        var results = await evaluator.EvaluateAsync(items);

        // Assert
        Assert.True(results.AllPassed);
    }

    [Fact]
    public async Task FunctionEvaluator_WithExpected_PassesExpectedAsync()
    {
        // Arrange
        var check = FunctionEvaluator.Create("contains_expected",
            (string response, string? expectedOutput) =>
                expectedOutput != null && response.Contains(expectedOutput, StringComparison.OrdinalIgnoreCase));

        var evaluator = new LocalEvaluator(check);
        var item = CreateItem();
        item.ExpectedOutput = "sunny";
        var items = new List<EvalItem> { item };

        // Act
        var results = await evaluator.EvaluateAsync(items);

        // Assert
        Assert.True(results.AllPassed);
    }

    [Fact]
    public async Task FunctionEvaluator_FullItem_AccessesAllFieldsAsync()
    {
        // Arrange
        var check = FunctionEvaluator.Create("full_check",
            (EvalItem item) => item.Query.Contains("weather", StringComparison.OrdinalIgnoreCase)
                && item.Response.Length > 0);

        var evaluator = new LocalEvaluator(check);
        var items = new List<EvalItem> { CreateItem() };

        // Act
        var results = await evaluator.EvaluateAsync(items);

        // Assert
        Assert.True(results.AllPassed);
    }

    [Fact]
    public async Task FunctionEvaluator_WithCheckResult_ReturnsCustomReasonAsync()
    {
        // Arrange
        var check = FunctionEvaluator.Create("custom_check",
            (EvalItem item) => new EvalCheckResult(true, "Custom reason", "custom_check"));

        var evaluator = new LocalEvaluator(check);
        var items = new List<EvalItem> { CreateItem() };

        // Act
        var results = await evaluator.EvaluateAsync(items);

        // Assert
        Assert.True(results.AllPassed);
        var metric = results.Items[0].Get<BooleanMetric>("custom_check");
        Assert.Equal("Custom reason", metric.Reason);
    }

    // ---------------------------------------------------------------
    // EvalChecks tests
    // ---------------------------------------------------------------

    [Fact]
    public async Task KeywordCheck_AllKeywordsPresent_PassesAsync()
    {
        // Arrange
        var evaluator = new LocalEvaluator(
            EvalChecks.KeywordCheck("weather", "sunny"));

        var items = new List<EvalItem> { CreateItem() };

        // Act
        var results = await evaluator.EvaluateAsync(items);

        // Assert
        Assert.True(results.AllPassed);
    }

    [Fact]
    public async Task KeywordCheck_MissingKeyword_FailsAsync()
    {
        // Arrange
        var evaluator = new LocalEvaluator(
            EvalChecks.KeywordCheck("snow"));

        var items = new List<EvalItem> { CreateItem() };

        // Act
        var results = await evaluator.EvaluateAsync(items);

        // Assert
        Assert.False(results.AllPassed);
    }

    [Fact]
    public async Task KeywordCheck_CaseInsensitiveByDefault_PassesAsync()
    {
        // Arrange
        var evaluator = new LocalEvaluator(
            EvalChecks.KeywordCheck("WEATHER", "SUNNY"));

        var items = new List<EvalItem> { CreateItem() };

        // Act
        var results = await evaluator.EvaluateAsync(items);

        // Assert
        Assert.True(results.AllPassed);
    }

    [Fact]
    public async Task KeywordCheck_CaseSensitive_FailsOnWrongCaseAsync()
    {
        // Arrange
        var evaluator = new LocalEvaluator(
            EvalChecks.KeywordCheck(caseSensitive: true, "WEATHER"));

        var items = new List<EvalItem> { CreateItem() };

        // Act
        var results = await evaluator.EvaluateAsync(items);

        // Assert
        Assert.False(results.AllPassed);
    }

    [Fact]
    public async Task ToolCalledCheck_ToolPresent_PassesAsync()
    {
        // Arrange
        var conversation = new List<ChatMessage>
        {
            new(ChatRole.User, "What is the weather?"),
            new(ChatRole.Assistant, new List<AIContent>
            {
                new FunctionCallContent("call1", "get_weather", new Dictionary<string, object?> { ["city"] = "Seattle" }),
            }),
            new(ChatRole.Tool, new List<AIContent>
            {
                new FunctionResultContent("call1", "72°F and sunny"),
            }),
            new(ChatRole.Assistant, "The weather is sunny and 72°F."),
        };

        var item = CreateItem(conversation: conversation);
        var evaluator = new LocalEvaluator(
            EvalChecks.ToolCalledCheck("get_weather"));

        // Act
        var results = await evaluator.EvaluateAsync(new List<EvalItem> { item });

        // Assert
        Assert.True(results.AllPassed);
    }

    [Fact]
    public async Task ToolCalledCheck_ToolMissing_FailsAsync()
    {
        // Arrange
        var evaluator = new LocalEvaluator(
            EvalChecks.ToolCalledCheck("get_weather"));

        var items = new List<EvalItem> { CreateItem() };

        // Act
        var results = await evaluator.EvaluateAsync(items);

        // Assert
        Assert.False(results.AllPassed);
    }

    // ---------------------------------------------------------------
    // AgentEvaluationResults tests
    // ---------------------------------------------------------------

    [Fact]
    public void AgentEvaluationResults_AllPassed_WhenAllMetricsGood()
    {
        // Arrange
        var evalResult = new EvaluationResult();
        evalResult.Metrics["check"] = new BooleanMetric("check", true)
        {
            Interpretation = new EvaluationMetricInterpretation
            {
                Rating = EvaluationRating.Good,
                Failed = false,
            },
        };

        // Act
        var results = new AgentEvaluationResults("test", new[] { evalResult });

        // Assert
        Assert.True(results.AllPassed);
        Assert.Equal(1, results.Passed);
        Assert.Equal(0, results.Failed);
    }

    [Fact]
    public void AgentEvaluationResults_NotAllPassed_WhenMetricFailed()
    {
        // Arrange
        var evalResult = new EvaluationResult();
        evalResult.Metrics["check"] = new BooleanMetric("check", false)
        {
            Interpretation = new EvaluationMetricInterpretation
            {
                Rating = EvaluationRating.Unacceptable,
                Failed = true,
            },
        };

        // Act
        var results = new AgentEvaluationResults("test", new[] { evalResult });

        // Assert
        Assert.False(results.AllPassed);
        Assert.Equal(0, results.Passed);
        Assert.Equal(1, results.Failed);
    }

    [Fact]
    public void AssertAllPassed_ThrowsOnFailure()
    {
        // Arrange
        var evalResult = new EvaluationResult();
        evalResult.Metrics["check"] = new BooleanMetric("check", false)
        {
            Interpretation = new EvaluationMetricInterpretation
            {
                Rating = EvaluationRating.Unacceptable,
                Failed = true,
            },
        };

        var results = new AgentEvaluationResults("test", new[] { evalResult });

        // Act & Assert
        var ex = Assert.Throws<InvalidOperationException>(() => results.AssertAllPassed());
        Assert.Contains("0 passed", ex.Message);
        Assert.Contains("1 failed", ex.Message);
    }

    [Fact]
    public void AssertAllPassed_DoesNotThrowOnSuccess()
    {
        // Arrange
        var evalResult = new EvaluationResult();
        evalResult.Metrics["check"] = new BooleanMetric("check", true)
        {
            Interpretation = new EvaluationMetricInterpretation
            {
                Rating = EvaluationRating.Good,
                Failed = false,
            },
        };

        var results = new AgentEvaluationResults("test", new[] { evalResult });

        // Act & Assert (no exception)
        results.AssertAllPassed();
    }

    [Fact]
    public void AgentEvaluationResults_NumericMetric_HighScorePasses()
    {
        // Arrange
        var evalResult = new EvaluationResult();
        evalResult.Metrics["relevance"] = new NumericMetric("relevance", 4.5);

        // Act
        var results = new AgentEvaluationResults("test", new[] { evalResult });

        // Assert
        Assert.True(results.AllPassed);
    }

    [Fact]
    public void AgentEvaluationResults_NumericMetric_WithFailedInterpretation_Fails()
    {
        // Arrange — numeric metric with Interpretation.Failed = true should fail.
        var evalResult = new EvaluationResult();
        evalResult.Metrics["relevance"] = new NumericMetric("relevance", 2.0)
        {
            Interpretation = new EvaluationMetricInterpretation
            {
                Rating = EvaluationRating.Unacceptable,
                Failed = true,
            },
        };

        // Act
        var results = new AgentEvaluationResults("test", new[] { evalResult });

        // Assert
        Assert.False(results.AllPassed);
    }

    [Fact]
    public void AgentEvaluationResults_NumericMetric_WithoutInterpretation_Passes()
    {
        // Arrange — numeric metric without Interpretation is informational; should not fail.
        var evalResult = new EvaluationResult();
        evalResult.Metrics["relevance"] = new NumericMetric("relevance", 2.0);

        // Act
        var results = new AgentEvaluationResults("test", new[] { evalResult });

        // Assert
        Assert.True(results.AllPassed);
    }

    [Fact]
    public void AgentEvaluationResults_SubResults_AllPassedChecksChildren()
    {
        // Arrange
        var passResult = new EvaluationResult();
        passResult.Metrics["check"] = new BooleanMetric("check", true)
        {
            Interpretation = new EvaluationMetricInterpretation
            {
                Rating = EvaluationRating.Good,
                Failed = false,
            },
        };

        var failResult = new EvaluationResult();
        failResult.Metrics["check"] = new BooleanMetric("check", false)
        {
            Interpretation = new EvaluationMetricInterpretation
            {
                Rating = EvaluationRating.Unacceptable,
                Failed = true,
            },
        };

        var results = new AgentEvaluationResults("test", Array.Empty<EvaluationResult>())
        {
            SubResults = new Dictionary<string, AgentEvaluationResults>
            {
                ["agent1"] = new("test", new[] { passResult }),
                ["agent2"] = new("test", new[] { failResult }),
            },
        };

        // Assert
        Assert.False(results.AllPassed);
    }

    // ---------------------------------------------------------------
    // Mixed evaluator tests
    // ---------------------------------------------------------------

    [Fact]
    public async Task LocalEvaluator_MixedChecks_ReportsCorrectCountsAsync()
    {
        // Arrange
        var evaluator = new LocalEvaluator(
            EvalChecks.KeywordCheck("weather"),
            EvalChecks.KeywordCheck("snow"),
            FunctionEvaluator.Create("is_long", (string r) => r.Length > 5));

        var items = new List<EvalItem> { CreateItem() };

        // Act
        var results = await evaluator.EvaluateAsync(items);

        // Assert
        Assert.Equal(1, results.Total);

        // One item with 3 checks: "weather" passes, "snow" fails, "is_long" passes
        // The item has one failed metric so it should count as failed
        Assert.Equal(0, results.Passed);
        Assert.Equal(1, results.Failed);
    }

    // ---------------------------------------------------------------
    // Conversation Split tests
    // ---------------------------------------------------------------

    private static List<ChatMessage> CreateMultiTurnConversation()
    {
        return new List<ChatMessage>
        {
            new(ChatRole.User, "What's the weather in Seattle?"),
            new(ChatRole.Assistant, "Seattle is 62°F and cloudy."),
            new(ChatRole.User, "And Paris?"),
            new(ChatRole.Assistant, "Paris is 68°F and partly sunny."),
            new(ChatRole.User, "Compare them."),
            new(ChatRole.Assistant, "Seattle is cooler; Paris is warmer and sunnier."),
        };
    }

    [Fact]
    public void Split_LastTurn_SplitsAtLastUserMessage()
    {
        // Arrange
        var conversation = CreateMultiTurnConversation();
        var item = new EvalItem("Compare them.", "Seattle is cooler; Paris is warmer and sunnier.", conversation);

        // Act
        var (query, response) = item.Split(ConversationSplitters.LastTurn);

        // Assert — query includes everything up to and including "Compare them."
        Assert.Equal(5, query.Count);
        Assert.Equal(ChatRole.User, query[query.Count - 1].Role);
        Assert.Contains("Compare", query[query.Count - 1].Text);

        // Response is the final assistant message
        Assert.Single(response);
        Assert.Equal(ChatRole.Assistant, response[0].Role);
    }

    [Fact]
    public void Split_Full_SplitsAtFirstUserMessage()
    {
        // Arrange
        var conversation = CreateMultiTurnConversation();
        var item = new EvalItem("What's the weather in Seattle?", "Full trajectory", conversation);

        // Act
        var (query, response) = item.Split(ConversationSplitters.Full);

        // Assert — query is just the first user message
        Assert.Single(query);
        Assert.Contains("Seattle", query[0].Text);

        // Response is everything after
        Assert.Equal(5, response.Count);
    }

    [Fact]
    public void Split_Full_IncludesSystemMessagesInQuery()
    {
        // Arrange
        var conversation = new List<ChatMessage>
        {
            new(ChatRole.System, "You are a weather assistant."),
            new(ChatRole.User, "What's the weather?"),
            new(ChatRole.Assistant, "It's sunny."),
        };

        var item = new EvalItem("What's the weather?", "It's sunny.", conversation);

        // Act
        var (query, response) = item.Split(ConversationSplitters.Full);

        // Assert — system message + first user message
        Assert.Equal(2, query.Count);
        Assert.Equal(ChatRole.System, query[0].Role);
        Assert.Equal(ChatRole.User, query[1].Role);
        Assert.Single(response);
    }

    [Fact]
    public void Split_DefaultIsLastTurn()
    {
        // Arrange
        var conversation = CreateMultiTurnConversation();
        var item = new EvalItem("Compare them.", "response", conversation);

        // Act — no split specified
        var (query, response) = item.Split();

        // Assert — same as LastTurn
        Assert.Equal(5, query.Count);
        Assert.Single(response);
    }

    [Fact]
    public void Split_SplitterProperty_UsedWhenNoExplicitSplit()
    {
        // Arrange
        var conversation = CreateMultiTurnConversation();
        var item = new EvalItem("query", "response", conversation)
        {
            Splitter = ConversationSplitters.Full,
        };

        // Act — no explicit split, should use Splitter
        var (query, response) = item.Split();

        // Assert — Full split
        Assert.Single(query);
        Assert.Equal(5, response.Count);
    }

    [Fact]
    public void Split_ExplicitSplitter_OverridesSplitterProperty()
    {
        // Arrange
        var conversation = CreateMultiTurnConversation();
        var item = new EvalItem("query", "response", conversation)
        {
            Splitter = ConversationSplitters.Full,
        };

        // Act — explicit LastTurn overrides Full
        var (query, response) = item.Split(ConversationSplitters.LastTurn);

        // Assert — LastTurn behavior
        Assert.Equal(5, query.Count);
        Assert.Single(response);
    }

    [Fact]
    public void Split_WithToolMessages_PreservesToolPairs()
    {
        // Arrange
        var conversation = new List<ChatMessage>
        {
            new(ChatRole.User, "What's the weather?"),
            new(ChatRole.Assistant, new List<AIContent>
            {
                new FunctionCallContent("c1", "get_weather", new Dictionary<string, object?> { ["city"] = "Seattle" }),
            }),
            new(ChatRole.Tool, new List<AIContent>
            {
                new FunctionResultContent("c1", "62°F, cloudy"),
            }),
            new(ChatRole.Assistant, "Seattle is 62°F and cloudy."),
            new(ChatRole.User, "Thanks!"),
            new(ChatRole.Assistant, "You're welcome!"),
        };

        var item = new EvalItem("Thanks!", "You're welcome!", conversation);

        // Act
        var (query, response) = item.Split(ConversationSplitters.LastTurn);

        // Assert — tool messages stay in query context
        Assert.Equal(5, query.Count);
        Assert.Equal(ChatRole.Tool, query[2].Role);
        Assert.Single(response);
    }

    [Fact]
    public void ConversationSplitters_LastTurn_CanBeUsedAsCustomFallback()
    {
        // Arrange
        var conversation = CreateMultiTurnConversation();

        // Act — use ConversationSplitters.LastTurn directly
        var (query, response) = ConversationSplitters.LastTurn.Split(conversation);

        // Assert
        Assert.Equal(5, query.Count);
        Assert.Single(response);
    }

    // ---------------------------------------------------------------
    // PerTurnItems tests
    // ---------------------------------------------------------------

    [Fact]
    public void PerTurnItems_SplitsMultiTurnConversation()
    {
        // Arrange
        var conversation = CreateMultiTurnConversation();

        // Act
        var items = EvalItem.PerTurnItems(conversation);

        // Assert — 3 user messages = 3 items
        Assert.Equal(3, items.Count);

        // First turn: "What's the weather in Seattle?"
        Assert.Contains("Seattle", items[0].Query);
        Assert.Contains("62°F", items[0].Response);
        Assert.Equal(2, items[0].Conversation.Count);

        // Second turn: "And Paris?"
        Assert.Contains("Paris", items[1].Query);
        Assert.Contains("68°F", items[1].Response);
        Assert.Equal(4, items[1].Conversation.Count);

        // Third turn: "Compare them."
        Assert.Contains("Compare", items[2].Query);
        Assert.Contains("cooler", items[2].Response);
        Assert.Equal(6, items[2].Conversation.Count);
    }

    [Fact]
    public void PerTurnItems_PropagatesToolsAndContext()
    {
        // Arrange
        var conversation = CreateMultiTurnConversation();

        // Act
        var items = EvalItem.PerTurnItems(
            conversation,
            context: "Weather database");

        // Assert
        Assert.All(items, item => Assert.Equal("Weather database", item.Context));
    }

    [Fact]
    public void PerTurnItems_SingleTurn_ReturnsOneItem()
    {
        // Arrange
        var conversation = new List<ChatMessage>
        {
            new(ChatRole.User, "Hello"),
            new(ChatRole.Assistant, "Hi there!"),
        };

        // Act
        var items = EvalItem.PerTurnItems(conversation);

        // Assert
        Assert.Single(items);
        Assert.Equal("Hello", items[0].Query);
        Assert.Equal("Hi there!", items[0].Response);
    }

    // ---------------------------------------------------------------
    // Custom IConversationSplitter tests
    // ---------------------------------------------------------------

    [Fact]
    public void Split_CustomSplitter_IsUsed()
    {
        // Arrange — splitter that splits before a tool call message
        var conversation = new List<ChatMessage>
        {
            new(ChatRole.User, "Remember this"),
            new(ChatRole.Assistant, "Storing..."),
            new(ChatRole.User, "What did I say?"),
            new(ChatRole.Assistant, new List<AIContent>
            {
                new FunctionCallContent("c1", "retrieve_memory"),
            }),
            new(ChatRole.Tool, new List<AIContent>
            {
                new FunctionResultContent("c1", "You said: Remember this"),
            }),
            new(ChatRole.Assistant, "You said 'Remember this'."),
        };

        var splitter = new MemorySplitter();
        var item = new EvalItem("What did I say?", "You said 'Remember this'.", conversation);

        // Act
        var (query, response) = item.Split(splitter);

        // Assert — split before the tool call
        Assert.Equal(3, query.Count);
        Assert.Equal(3, response.Count);
    }

    [Fact]
    public void Split_CustomSplitter_WorksAsItemProperty()
    {
        // Arrange — custom splitter set on the item (simulating call-site override)
        var conversation = new List<ChatMessage>
        {
            new(ChatRole.User, "Remember this"),
            new(ChatRole.Assistant, "Storing..."),
            new(ChatRole.User, "What did I say?"),
            new(ChatRole.Assistant, new List<AIContent>
            {
                new FunctionCallContent("c1", "retrieve_memory"),
            }),
            new(ChatRole.Tool, new List<AIContent>
            {
                new FunctionResultContent("c1", "You said: Remember this"),
            }),
            new(ChatRole.Assistant, "You said 'Remember this'."),
        };

        var item = new EvalItem("What did I say?", "You said 'Remember this'.", conversation)
        {
            Splitter = new MemorySplitter(),
        };

        // Act — no explicit splitter, uses item.Splitter
        var (query, response) = item.Split();

        // Assert — custom splitter was used
        Assert.Equal(3, query.Count);
        Assert.Equal(3, response.Count);
    }

    private sealed class MemorySplitter : IConversationSplitter
    {
        public (IReadOnlyList<ChatMessage> QueryMessages, IReadOnlyList<ChatMessage> ResponseMessages) Split(
            IReadOnlyList<ChatMessage> conversation)
        {
            for (int i = 0; i < conversation.Count; i++)
            {
                var msg = conversation[i];
                if (msg.Role == ChatRole.Assistant && msg.Contents != null)
                {
                    foreach (var content in msg.Contents)
                    {
                        if (content is FunctionCallContent fc && fc.Name == "retrieve_memory")
                        {
                            return (
                                conversation.Take(i).ToList(),
                                conversation.Skip(i).ToList());
                        }
                    }
                }
            }

            // Fallback to last-turn split
            return ConversationSplitters.LastTurn.Split(conversation);
        }
    }

    // ---------------------------------------------------------------
    // ExpectedToolCall tests
    // ---------------------------------------------------------------

    [Fact]
    public void ExpectedToolCall_NameOnly()
    {
        var tc = new ExpectedToolCall("get_weather");
        Assert.Equal("get_weather", tc.Name);
        Assert.Null(tc.Arguments);
    }

    [Fact]
    public void ExpectedToolCall_NameAndArgs()
    {
        var args = new Dictionary<string, object> { ["location"] = "NYC" };
        var tc = new ExpectedToolCall("get_weather", args);
        Assert.Equal("get_weather", tc.Name);
        Assert.NotNull(tc.Arguments);
        Assert.Equal("NYC", tc.Arguments["location"]);
    }

    [Fact]
    public void EvalItem_ExpectedToolCalls_DefaultNull()
    {
        var item = CreateItem();
        Assert.Null(item.ExpectedToolCalls);
    }

    [Fact]
    public void EvalItem_ExpectedToolCalls_CanBeSet()
    {
        var item = CreateItem();
        item.ExpectedToolCalls = new List<ExpectedToolCall>
        {
            new("get_weather", new Dictionary<string, object> { ["location"] = "NYC" }),
            new("book_flight"),
        };

        Assert.NotNull(item.ExpectedToolCalls);
        Assert.Equal(2, item.ExpectedToolCalls.Count);
        Assert.Equal("get_weather", item.ExpectedToolCalls[0].Name);
        Assert.Null(item.ExpectedToolCalls[1].Arguments);
    }

    [Fact]
    public async Task LocalEvaluator_PopulatesInputItems_ForAuditingAsync()
    {
        // Arrange
        var check = FunctionEvaluator.Create("is_sunny",
            (string response) => response.Contains("sunny", StringComparison.OrdinalIgnoreCase));

        var evaluator = new LocalEvaluator(check);
        var items = new List<EvalItem>
        {
            CreateItem(query: "Weather?", response: "It's sunny!"),
            CreateItem(query: "Temp?", response: "72 degrees"),
        };

        // Act
        var results = await evaluator.EvaluateAsync(items);

        // Assert — InputItems carries the original query/response for auditing
        Assert.NotNull(results.InputItems);
        Assert.Equal(2, results.InputItems.Count);
        Assert.Equal("Weather?", results.InputItems[0].Query);
        Assert.Equal("It's sunny!", results.InputItems[0].Response);
        Assert.Equal("Temp?", results.InputItems[1].Query);
        Assert.Equal("72 degrees", results.InputItems[1].Response);

        // Results and InputItems are positionally correlated
        Assert.Equal(results.Items.Count, results.InputItems.Count);
    }

    // ---------------------------------------------------------------
    // AgentEvaluationResults tests
    // ---------------------------------------------------------------

    [Fact]
    public void AllPassed_EmptyItems_NoSubResults_ReturnsFalseAsync()
    {
        var results = new AgentEvaluationResults("test", Array.Empty<EvaluationResult>());
        Assert.False(results.AllPassed);
        Assert.Equal(0, results.Total);
    }

    [Fact]
    public void AllPassed_SubResultsAllPass_OverallFails_ReturnsFalseAsync()
    {
        // Overall has a failing item
        var failMetric = new BooleanMetric("check", false)
        {
            Interpretation = new EvaluationMetricInterpretation
            {
                Rating = EvaluationRating.Unacceptable,
                Failed = true,
            },
        };
        var failResult = new EvaluationResult();
        failResult.Metrics["check"] = failMetric;

        var overall = new AgentEvaluationResults("test", new[] { failResult });

        // Sub-results all pass
        var passMetric = new BooleanMetric("check", true)
        {
            Interpretation = new EvaluationMetricInterpretation
            {
                Rating = EvaluationRating.Good,
                Failed = false,
            },
        };
        var passResult = new EvaluationResult();
        passResult.Metrics["check"] = passMetric;

        overall.SubResults = new Dictionary<string, AgentEvaluationResults>
        {
            ["agent1"] = new AgentEvaluationResults("sub", new[] { passResult }),
        };

        // Overall has a failing item, so AllPassed should be false
        Assert.False(overall.AllPassed);
    }

    // ---------------------------------------------------------------
    // BuildItemsFromResponses validation tests
    // ---------------------------------------------------------------

    [Fact]
    public void BuildEvalItem_SetsPropertiesCorrectly()
    {
        var userMsg = new ChatMessage(ChatRole.User, "test query");
        var assistantMsg = new ChatMessage(ChatRole.Assistant, "response");
        var inputMessages = new List<ChatMessage> { userMsg };
        var response = new AgentResponse(assistantMsg);

        var item = AgentEvaluationExtensions.BuildEvalItem("test query", response, inputMessages, null!);

        Assert.Equal("test query", item.Query);
        Assert.NotNull(item.RawResponse);
    }

    [Fact]
    public void BuildEvalItem_DoesNotMutateInputMessages()
    {
        // Arrange
        var userMsg = new ChatMessage(ChatRole.User, "hello");
        var assistantMsg = new ChatMessage(ChatRole.Assistant, "world");
        var inputMessages = new List<ChatMessage> { userMsg };
        var response = new AgentResponse(assistantMsg);

        // Act
        var item = AgentEvaluationExtensions.BuildEvalItem("hello", response, inputMessages, null!);

        // Assert — input list is not mutated
        Assert.Single(inputMessages);
        Assert.Equal(userMsg, inputMessages[0]);

        // But the EvalItem's conversation includes the response message
        Assert.Equal(2, item.Conversation.Count);
    }

    // ---------------------------------------------------------------
    // BuildItemsFromResponses validation tests
    // ---------------------------------------------------------------

    [Fact]
    public void BuildItemsFromResponses_MismatchedQueryAndResponseCount_Throws()
    {
        var queries = new[] { "q1", "q2" };
        var responses = new[] { new AgentResponse(new ChatMessage(ChatRole.Assistant, "a1")) };

        var ex = Assert.Throws<ArgumentException>(
            () => AgentEvaluationExtensions.BuildItemsFromResponses(null!, responses, queries, null, null));
        Assert.Contains("queries", ex.Message);
        Assert.Contains("responses", ex.Message);
    }

    [Fact]
    public void BuildItemsFromResponses_MismatchedExpectedOutput_Throws()
    {
        var queries = new[] { "q1" };
        var responses = new[] { new AgentResponse(new ChatMessage(ChatRole.Assistant, "a1")) };
        var expectedOutput = new[] { "e1", "e2" };

        var ex = Assert.Throws<ArgumentException>(
            () => AgentEvaluationExtensions.BuildItemsFromResponses(null!, responses, queries, expectedOutput, null));
        Assert.Contains("expectedOutput", ex.Message);
    }

    [Fact]
    public void BuildItemsFromResponses_MismatchedExpectedToolCalls_Throws()
    {
        var queries = new[] { "q1" };
        var responses = new[] { new AgentResponse(new ChatMessage(ChatRole.Assistant, "a1")) };
        var expectedToolCalls = new[] { new[] { new ExpectedToolCall("t1") }, new[] { new ExpectedToolCall("t2") } };

        var ex = Assert.Throws<ArgumentException>(
            () => AgentEvaluationExtensions.BuildItemsFromResponses(
                null!, responses, queries, null, expectedToolCalls));
        Assert.Contains("expectedToolCalls", ex.Message);
    }

    // ---------------------------------------------------------------
    // FoundryEvalConverter tests
    // ---------------------------------------------------------------

    [Fact]
    public void ResolveEvaluator_QualityShortNames_ResolvesToBuiltin()
    {
        Assert.Equal("builtin.relevance", AzureAI.FoundryEvalConverter.ResolveEvaluator("relevance"));
        Assert.Equal("builtin.coherence", AzureAI.FoundryEvalConverter.ResolveEvaluator("coherence"));
    }

    [Fact]
    public void ResolveEvaluator_FullyQualifiedName_ReturnsSame()
    {
        Assert.Equal("builtin.relevance", AzureAI.FoundryEvalConverter.ResolveEvaluator("builtin.relevance"));
    }

    [Fact]
    public void ResolveEvaluator_UnknownName_ThrowsArgumentException()
    {
        var ex = Assert.Throws<ArgumentException>(
            () => AzureAI.FoundryEvalConverter.ResolveEvaluator("gobblygook"));
        Assert.Contains("gobblygook", ex.Message);
    }

    [Fact]
    public void ResolveEvaluator_AgentEvaluators_ResolveCorrectly()
    {
        Assert.Equal("builtin.intent_resolution", AzureAI.FoundryEvalConverter.ResolveEvaluator("intent_resolution"));
        Assert.Equal("builtin.tool_call_accuracy", AzureAI.FoundryEvalConverter.ResolveEvaluator("tool_call_accuracy"));
    }
}
