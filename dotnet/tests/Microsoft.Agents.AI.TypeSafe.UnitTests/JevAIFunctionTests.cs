// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.DependencyInjection;

namespace Microsoft.Agents.AI.TypeSafe.UnitTests;

public sealed class JevAIFunctionTests
{
    [Fact]
    public async Task InvokeAsync_ModelArguments_ReachTheMappingAsTypedRequestAsync()
    {
        // Arrange
        JevRequest? received = null;
        AIFunction tool = new JevAIToolBuilder().UseMapping((request, _, _) =>
        {
            received = request;
            return Task.FromResult(JevTestData.CreateResult());
        }).Build();

        // Act
        await tool.InvokeAsync(JevTestData.Arguments(JevTestData.RequestJson));

        // Assert
        Assert.NotNull(received);
        Assert.Equal(JevTestData.TicketText, received.State.Text);

        JevChoiceQuestion department = Assert.IsType<JevChoiceQuestion>(received.Questions["department"]);
        Assert.Equal("Which team should handle this", department.Instructions?.Text);
        Assert.Equal(["billing", "technical", "sales"], department.Criteria.Keys);
        Assert.True(department.Criteria["sales"].IsNull);

        JevScoreQuestion frustration = Assert.IsType<JevScoreQuestion>(received.Questions["frustration"]);
        Assert.Equal(3, frustration.Criteria.Count);
        Assert.Equal("Calm, just stating facts", frustration.Criteria[0].Text);

        JevNoulQuestion urgent = Assert.IsType<JevNoulQuestion>(received.Questions["is_urgent"]);
        Assert.Equal("Explicitly time-sensitive", urgent.Criteria!.True?.Text);
        Assert.Equal("No urgency expressed", urgent.Criteria.False?.Text);
    }

    [Fact]
    public async Task InvokeAsync_ReturnsTheResultAsJsonWithWireNamesAsync()
    {
        // Arrange
        AIFunction tool = new JevAIToolBuilder().UseMapping((_, _, _) => Task.FromResult(JevTestData.CreateResult())).Build();

        // Act
        object? result = await tool.InvokeAsync(JevTestData.Arguments(JevTestData.RequestJson));

        // Assert
        JsonElement json = Assert.IsType<JsonElement>(result);
        Assert.Equal("custom-model", json.GetProperty("model").GetString());
        JsonElement answers = json.GetProperty("answers");
        Assert.Equal("choice", answers.GetProperty("department").GetProperty("type").GetString());
        Assert.Equal("technical", answers.GetProperty("department").GetProperty("choice").GetString());
        Assert.Equal(0.78, answers.GetProperty("department").GetProperty("confidence").GetDouble());
        Assert.Equal("score", answers.GetProperty("frustration").GetProperty("type").GetString());
        Assert.Equal("Frustrated", answers.GetProperty("frustration").GetProperty("legend").GetProperty("1").GetString());
        Assert.Equal(0.97, answers.GetProperty("is_urgent").GetProperty("noul").GetDouble());
        Assert.Equal(10, json.GetProperty("usage").GetProperty("input_tokens").GetInt64());
        Assert.Equal(5, json.GetProperty("usage").GetProperty("output_tokens").GetInt64());
    }

    [Fact]
    public async Task InvokeAsync_TypeWrittenLastAndObjectState_AreAcceptedAsync()
    {
        // Arrange
        JevRequest? received = null;
        AIFunction tool = new JevAIToolBuilder().UseMapping((request, _, _) =>
        {
            received = request;
            return Task.FromResult(Result("paid", new JevNoulResponse { Noul = 0.1 }));
        }).Build();

        // Act
        await tool.InvokeAsync(JevTestData.Arguments("""
            {
              "questions": { "paid": { "instructions": "Was `order` paid?", "type": "noul" } },
              "state": { "order": { "id": "A-104", "status": "failed" } }
            }
            """));

        // Assert
        Assert.Equal(JsonValueKind.Object, received!.State.Kind);
        Assert.Equal("A-104", received.State.Json!.Value.GetProperty("order").GetProperty("id").GetString());
        Assert.IsType<JevNoulQuestion>(received.Questions["paid"]);
    }

    [Fact]
    public async Task InvokeAsync_StructuredEntries_AreAcceptedLikeTheSdkAsync()
    {
        // Arrange
        JevRequest? received = null;
        AIFunction tool = new JevAIToolBuilder().UseMapping((request, _, _) =>
        {
            received = request;
            return Task.FromResult(new JevResult
            {
                Model = "m",
                Answers = new Dictionary<string, JevResponse>
                {
                    ["same_person"] = new JevNoulResponse { Noul = 0.9 },
                    ["team"] = new JevChoiceResponse { Choice = "billing", Confidence = 1, Probabilities = new Dictionary<string, double> { ["billing"] = 1 } },
                },
                Usage = new JevUsage { InputTokens = 1, OutputTokens = 1 },
            });
        }).Build();

        // Act
        await tool.InvokeAsync(JevTestData.Arguments("""
            {
              "state": ["Hi", "The payment failed."],
              "questions": {
                "same_person": {
                  "type": "noul",
                  "instructions": { "potential_duplicate": { "name": "John Smith" }, "question": "Is the resume for the same person as `potential_duplicate`?" }
                },
                "team": { "type": "choice", "criteria": { "billing": { "covers": ["payments", "refunds"] } } }
              }
            }
            """));

        // Assert
        Assert.Equal(JsonValueKind.Array, received!.State.Kind);
        JevEntry instructions = Assert.IsType<JevNoulQuestion>(received.Questions["same_person"]).Instructions!.Value;
        Assert.Equal(JsonValueKind.Object, instructions.Kind);
        Assert.Equal("John Smith", instructions.Json!.Value.GetProperty("potential_duplicate").GetProperty("name").GetString());

        JevChoiceQuestion team = Assert.IsType<JevChoiceQuestion>(received.Questions["team"]);
        Assert.Null(team.Instructions);
        Assert.Equal(JsonValueKind.Object, team.Criteria["billing"].Kind);
    }

    [Fact]
    public async Task InvokeAsync_DotNetObjectArguments_AreAcceptedAsync()
    {
        // Arrange
        JevRequest? received = null;
        AIFunction tool = new JevAIToolBuilder().UseMapping((request, _, _) =>
        {
            received = request;
            return Task.FromResult(Result("q", new JevNoulResponse { Noul = 0.5 }));
        }).Build();

        // Act
        await tool.InvokeAsync(new AIFunctionArguments
        {
            ["state"] = "The payment failed.",
            ["questions"] = new Dictionary<string, JevQuestion> { ["q"] = new JevNoulQuestion { Instructions = "Did the payment fail?" } },
        });

        // Assert
        Assert.Equal("The payment failed.", received!.State.Text);
        Assert.Equal("Did the payment fail?", Assert.IsType<JevNoulQuestion>(received.Questions["q"]).Instructions?.Text);
    }

    [Theory]
    [InlineData("""{"questions":{"q":{"type":"noul","instructions":"x"}}}""", "state")]
    [InlineData("""{"state":42,"questions":{"q":{"type":"noul","instructions":"x"}}}""", "must be text, a JSON object or array, or null")]
    [InlineData("""{"state":null,"questions":{"q":{"type":"noul","instructions":"x"}}}""", "The state must be text or a JSON object or array")]
    [InlineData("""{"state":"x","questions":{}}""", "At least one question is required")]
    [InlineData("""{"state":"x","questions":{"q":{"type":"rank","instructions":"x"}}}""", "not a valid Jev request")]
    [InlineData("""{"state":"x","questions":{"q":{"instructions":"x"}}}""", "not a valid Jev request")]
    [InlineData("""{"state":"x","questions":{"q":null}}""", "Question 'q' is null")]
    [InlineData("""{"state":"x","questions":{"q":{"type":"noul","instructions":" "}}}""", "Noul question 'q' needs instructions or criteria")]
    [InlineData("""{"state":"x","questions":{"q":{"type":"noul","criteria":{"true":null}}}}""", "Noul question 'q' needs instructions or criteria")]
    [InlineData("""{"state":"x","questions":{"q":{"type":"choice","instructions":"x","criteria":{}}}}""", "has 0 alternatives; it needs from 1 to 255")]
    [InlineData("""{"state":"x","questions":{"q":{"type":"score","instructions":"x","criteria":["only"]}}}""", "has 1 criterion; it needs from 2 to 10")]
    [InlineData("""{"state":"x","questions":{"q":{"type":"score","instructions":"x","criteria":["0","1","2","3","4","5","6","7","8","9","10"]}}}""", "has 11 criteria")]
    [InlineData("""{"state":"x","questions":{"q":{"type":"score","instructions":"x","criteria":[1,2]}}}""", "must be text, a JSON object or array, or null")]
    [InlineData("""{"state":"x","questions":{"q":{"type":"score","instructions":"x","criteria":[null,"High"]}}}""", "has a null criterion at index 0")]
    public async Task InvokeAsync_InvalidArguments_FailBeforeCallingAsync(string arguments, string expectedMessage)
    {
        // Arrange
        int calls = 0;
        AIFunction tool = new JevAIToolBuilder().UseMapping((_, _, _) =>
        {
            calls++;
            return Task.FromResult(JevTestData.CreateResult());
        }).Build();

        // Act
        ArgumentException exception = await Assert.ThrowsAnyAsync<ArgumentException>(() => tool.InvokeAsync(JevTestData.Arguments(arguments)).AsTask());

        // Assert
        Assert.Contains(expectedMessage, exception.Message, StringComparison.Ordinal);
        Assert.Equal(0, calls);
    }

    [Fact]
    public async Task InvokeAsync_QuestionsWithoutInstructionsButWithCriteria_AreAcceptedAsync()
    {
        // Arrange
        int calls = 0;
        AIFunction tool = new JevAIToolBuilder().UseMapping((_, _, _) =>
        {
            calls++;
            return Task.FromResult(new JevResult
            {
                Model = "m",
                Answers = new Dictionary<string, JevResponse>
                {
                    ["urgent"] = new JevNoulResponse { Noul = 0.2 },
                    ["level"] = new JevScoreResponse
                    {
                        Score = 0,
                        Confidence = 1,
                        Legend = new Dictionary<string, JevEntry> { ["0"] = "Low", ["1"] = "High" },
                        Probabilities = new Dictionary<string, double> { ["0"] = 1, ["1"] = 0 },
                    },
                },
                Usage = new JevUsage { InputTokens = 1, OutputTokens = 1 },
            });
        }).Build();

        // Act
        await tool.InvokeAsync(JevTestData.Arguments("""
            {"state":"x","questions":{
              "urgent":{"type":"noul","criteria":{"true":"Explicitly urgent"}},
              "level":{"type":"score","criteria":["Low",{"level":"high","signals":["outage"]}]}}}
            """));

        // Assert
        Assert.Equal(1, calls);
    }

    [Fact]
    public async Task InvokeAsync_TooManyChoiceAlternatives_FailBeforeCallingAsync()
    {
        // Arrange
        string alternatives = string.Join(",", Enumerable.Range(0, 256).Select(static i => $"\"o{i}\":null"));
        string arguments = "{\"state\":\"x\",\"questions\":{\"q\":{\"type\":\"choice\",\"instructions\":\"x\",\"criteria\":{" + alternatives + "}}}}";
        AIFunction tool = new JevAIToolBuilder().UseMapping((_, _, _) => Task.FromResult(JevTestData.CreateResult())).Build();

        // Act
        ArgumentException exception = await Assert.ThrowsAsync<ArgumentException>(() => tool.InvokeAsync(JevTestData.Arguments(arguments)).AsTask());

        // Assert
        Assert.Contains("has 256 alternatives", exception.Message, StringComparison.Ordinal);
    }

    public static TheoryData<string, Func<JevResult, JevResult>, string> InvalidResults => new()
    {
        { "no answer", static r => Without(r, "is_urgent"), "no answer for question 'is_urgent'" },
        { "wrong kind", static r => With(r, "department", new JevNoulResponse { Noul = 0.5 }), "is a Noul answer, but the question is a Choice question" },
        { "unknown label", static r => With(r, "department", Choice("refunds", 0.9)), "chose 'refunds', which is not one of its labels" },
        { "confidence out of range", static r => With(r, "department", Choice("technical", 1.2)), "has confidence 1.2, which is outside the range 0 to 1" },
        { "score out of range", static r => With(r, "frustration", Score(3)), "has score 3, which is outside the range 0 to 2" },
        { "noul as percent", static r => With(r, "is_urgent", new JevNoulResponse { Noul = 97 }), "has noul 97, which is outside the range 0 to 1" },
        { "no answers", static r => new JevResult { Model = r.Model, Answers = null!, Usage = r.Usage }, "has no answers" },
        { "probability for a label not offered", static r => With(r, "department", ChoiceWith("technical", new() { ["TECHNICAL"] = 1 })), "has probabilities for 'TECHNICAL', which is not one of its labels" },
        { "probability above one", static r => With(r, "department", ChoiceWith("technical", new() { ["technical"] = 42 })), "has probability 'technical' 42, which is outside the range 0 to 1" },
        { "probability not a number", static r => With(r, "department", ChoiceWith("technical", new() { ["technical"] = double.NaN })), "has probability 'technical' NaN" },
        { "score probability for a missing score", static r => With(r, "frustration", ScoreWith(new() { ["3"] = 1 }, [])), "has probabilities for '3', which is not a score from 0 to 2" },
        { "legend for a missing score", static r => With(r, "frustration", ScoreWith([], new() { ["high"] = "Very angry" })), "has legend for 'high', which is not a score from 0 to 2" },
    };

    [Theory]
    [MemberData(nameof(InvalidResults))]
    public async Task InvokeAsync_InvalidMappingResult_FailsAsync(string scenario, Func<JevResult, JevResult> corrupt, string expectedMessage)
    {
        // Arrange
        AIFunction tool = new JevAIToolBuilder().UseMapping((_, _, _) => Task.FromResult(corrupt(JevTestData.CreateResult()))).Build();

        // Act
        InvalidOperationException exception = await Assert.ThrowsAsync<InvalidOperationException>(() => tool.InvokeAsync(JevTestData.Arguments(JevTestData.RequestJson)).AsTask());

        // Assert
        Assert.True(exception.Message.Contains(expectedMessage, StringComparison.Ordinal), $"{scenario}: {exception.Message}");
    }

    [Fact]
    public async Task InvokeAsync_MappingReturnsNull_FailsAsync()
    {
        // Arrange
        AIFunction tool = new JevAIToolBuilder().UseMapping((_, _, _) => Task.FromResult<JevResult>(null!)).Build();

        // Act
        InvalidOperationException exception = await Assert.ThrowsAsync<InvalidOperationException>(() => tool.InvokeAsync(JevTestData.Arguments(JevTestData.RequestJson)).AsTask());

        // Assert
        Assert.Contains("returned no result", exception.Message, StringComparison.Ordinal);
    }

    [Fact]
    public async Task InvokeAsync_PassesTheCancellationTokenToTheMappingAsync()
    {
        // Arrange
        using var cancellation = new CancellationTokenSource();
        CancellationToken received = default;
        AIFunction tool = new JevAIToolBuilder().UseMapping((_, _, cancellationToken) =>
        {
            received = cancellationToken;
            return Task.FromResult(JevTestData.CreateResult());
        }).Build();

        // Act
        await tool.InvokeAsync(JevTestData.Arguments(JevTestData.RequestJson), cancellation.Token);

        // Assert
        Assert.Equal(cancellation.Token, received);
    }

    [Fact]
    public async Task UseClient_MapsBetweenTheContractAndTheClientTypesAsync()
    {
        // Arrange
        var client = new LabelClient(label: "technical");
        AIFunction tool = new JevAIToolBuilder().UseClient(
            client.ClassifyAsync,
            inputMapper: static request =>
            {
                (string id, JevQuestion question) = request.Questions.Single();
                return new LabelRequest(id, request.State.Text!, ((JevChoiceQuestion)question).Criteria.Keys.ToList());
            },
            outputMapper: static response => Result(response.QuestionId, Choice(response.Label, response.Score))).Build();

        // Act
        object? result = await tool.InvokeAsync(JevTestData.Arguments("""
            {"state":"My integration keeps failing","questions":{"team":{"type":"choice","instructions":"Which team?","criteria":{"billing":null,"technical":null}}}}
            """));

        // Assert
        Assert.Equal(new LabelRequest("team", "My integration keeps failing", ["billing", "technical"]), client.Received, LabelRequestComparer.Instance);
        JsonElement answer = Assert.IsType<JsonElement>(result).GetProperty("answers").GetProperty("team");
        Assert.Equal("technical", answer.GetProperty("choice").GetString());
    }

    [Fact]
    public async Task UseClient_MapperReturnsALabelThatWasNotOffered_FailsAsync()
    {
        // Arrange
        var client = new LabelClient(label: "TECHNICAL");
        AIFunction tool = new JevAIToolBuilder().UseClient(
            client.ClassifyAsync,
            static request => new LabelRequest("team", request.State.Text!, ["billing", "technical"]),
            static response => Result("team", Choice(response.Label, response.Score))).Build();

        // Act
        InvalidOperationException exception = await Assert.ThrowsAsync<InvalidOperationException>(() => tool.InvokeAsync(JevTestData.Arguments("""
            {"state":"x","questions":{"team":{"type":"choice","instructions":"Which team?","criteria":{"billing":null,"technical":null}}}}
            """)).AsTask());

        // Assert
        Assert.Contains("chose 'TECHNICAL'", exception.Message, StringComparison.Ordinal);
    }

    [Fact]
    public async Task UseMapping_ReceivesTheServicesOfTheCallAsync()
    {
        // Arrange
        using ServiceProvider services = new ServiceCollection().BuildServiceProvider();
        IServiceProvider? received = null;
        AIFunction tool = new JevAIToolBuilder().UseMapping((_, callServices, _) =>
        {
            received = callServices;
            return Task.FromResult(JevTestData.CreateResult());
        }).Build();

        AIFunctionArguments arguments = JevTestData.Arguments(JevTestData.RequestJson);
        arguments.Services = services;

        // Act
        await tool.InvokeAsync(arguments);

        // Assert
        Assert.Same(services, received);
    }

    [Fact]
    public async Task UseClient_RegisteredClient_IsResolvedFromTheServicesOnEveryCallAsync()
    {
        // Arrange
        int created = 0;
        using ServiceProvider services = new ServiceCollection()
            .AddTransient(_ =>
            {
                created++;
                return new LabelClient(label: "technical");
            })
            .BuildServiceProvider();

        AIFunction tool = new JevAIToolBuilder().UseClient<LabelClient, LabelRequest, LabelResponse>(
            static (client, request, cancellationToken) => client.ClassifyAsync(request, cancellationToken),
            static request => new LabelRequest("team", request.State.Text!, ["billing", "technical"]),
            static response => Result("team", Choice(response.Label, response.Score))).Build();

        AIFunctionArguments arguments = JevTestData.Arguments("""
            {"state":"x","questions":{"team":{"type":"choice","instructions":"Which team?","criteria":{"billing":null,"technical":null}}}}
            """);
        arguments.Services = services;

        // Act
        await tool.InvokeAsync(arguments);
        object? result = await tool.InvokeAsync(arguments);

        // Assert
        Assert.Equal(2, created);
        Assert.Equal("technical", Assert.IsType<JsonElement>(result).GetProperty("answers").GetProperty("team").GetProperty("choice").GetString());
    }

    [Theory]
    [InlineData(false, "this call has none")]
    [InlineData(true, "LabelClient is not registered")]
    public async Task UseClient_ClientNotAvailable_FailsWithWhatIsMissingAsync(bool withServices, string expectedMessage)
    {
        // Arrange
        using ServiceProvider services = new ServiceCollection().BuildServiceProvider();
        AIFunction tool = new JevAIToolBuilder().UseClient<LabelClient, LabelRequest, LabelResponse>(
            static (client, request, cancellationToken) => client.ClassifyAsync(request, cancellationToken),
            static request => new LabelRequest("q", "x", []),
            static response => JevTestData.CreateResult()).Build();

        AIFunctionArguments arguments = JevTestData.Arguments(JevTestData.RequestJson);
        arguments.Services = withServices ? services : null;

        // Act
        InvalidOperationException exception = await Assert.ThrowsAsync<InvalidOperationException>(() => tool.InvokeAsync(arguments).AsTask());

        // Assert
        Assert.Contains(expectedMessage, exception.Message, StringComparison.Ordinal);
    }

    [Fact]
    public async Task UseClient_ScopedClientFromTheRootProvider_GetsAScopePerCallAsync()
    {
        // Arrange
        var created = new List<ScopedLabelClient>();
        using ServiceProvider root = new ServiceCollection()
            .AddScoped(_ =>
            {
                var client = new ScopedLabelClient();
                created.Add(client);
                return client;
            })
            .BuildServiceProvider(new ServiceProviderOptions { ValidateScopes = true });

        AIFunction tool = new JevAIToolBuilder().UseClient<ScopedLabelClient, string, string>(
            static (client, text, _) => Task.FromResult(client.IsDisposed ? "disposed" : "technical"),
            static request => request.State.Text!,
            static label => Result("team", Choice(label, 0.9))).Build();

        AIFunctionArguments arguments = JevTestData.Arguments("""
            {"state":"x","questions":{"team":{"type":"choice","instructions":"Which team?","criteria":{"billing":null,"technical":null}}}}
            """);
        arguments.Services = root;

        // Act
        await tool.InvokeAsync(arguments);
        await tool.InvokeAsync(arguments);

        // Assert
        Assert.Equal(2, created.Count);
        Assert.All(created, static client => Assert.True(client.IsDisposed));
    }

    private static JevResult Result(string id, JevResponse answer) => new()
    {
        Model = "custom-model",
        Answers = new Dictionary<string, JevResponse> { [id] = answer },
        Usage = new JevUsage { InputTokens = 1, OutputTokens = 1 },
    };

    private static JevChoiceResponse Choice(string choice, double confidence) => new()
    {
        Choice = choice,
        Confidence = confidence,
        Probabilities = new Dictionary<string, double> { [choice] = confidence },
    };

    private static JevScoreResponse Score(double score) => new()
    {
        Score = score,
        Confidence = 1,
        Legend = new Dictionary<string, JevEntry>(),
        Probabilities = new Dictionary<string, double>(),
    };

    private static JevChoiceResponse ChoiceWith(string choice, Dictionary<string, double> probabilities) => new()
    {
        Choice = choice,
        Confidence = 0.5,
        Probabilities = probabilities,
    };

    private static JevScoreResponse ScoreWith(Dictionary<string, double> probabilities, Dictionary<string, JevEntry> legend) => new()
    {
        Score = 1,
        Confidence = 1,
        Legend = legend,
        Probabilities = probabilities,
    };

    private static JevResult With(JevResult result, string id, JevResponse answer)
    {
        var answers = new Dictionary<string, JevResponse>(result.Answers) { [id] = answer };
        return new JevResult { Model = result.Model, Answers = answers, Usage = result.Usage };
    }

    private static JevResult Without(JevResult result, string id)
    {
        var answers = new Dictionary<string, JevResponse>(result.Answers);
        answers.Remove(id);
        return new JevResult { Model = result.Model, Answers = answers, Usage = result.Usage };
    }

    /// <summary>The request type of a hypothetical third-party classification client.</summary>
    private sealed record LabelRequest(string QuestionId, string Text, List<string> Labels);

    /// <summary>The response type of a hypothetical third-party classification client.</summary>
    private sealed record LabelResponse(string QuestionId, string Label, double Score);

    private sealed class LabelClient(string label)
    {
        public LabelRequest? Received { get; private set; }

        public Task<LabelResponse> ClassifyAsync(LabelRequest request, CancellationToken cancellationToken)
        {
            this.Received = request;
            return Task.FromResult(new LabelResponse(request.QuestionId, label, 0.9));
        }
    }

    /// <summary>A disposable client registered as scoped, as clients holding per-request resources usually are.</summary>
    private sealed class ScopedLabelClient : IDisposable
    {
        public bool IsDisposed { get; private set; }

        public void Dispose() => this.IsDisposed = true;
    }

    private sealed class LabelRequestComparer : IEqualityComparer<LabelRequest?>
    {
        public static LabelRequestComparer Instance { get; } = new();

        public bool Equals(LabelRequest? x, LabelRequest? y) =>
            x is not null && y is not null && x.QuestionId == y.QuestionId && x.Text == y.Text && x.Labels.SequenceEqual(y.Labels);

        public int GetHashCode(LabelRequest? obj) => obj?.QuestionId.GetHashCode(StringComparison.Ordinal) ?? 0;
    }
}
