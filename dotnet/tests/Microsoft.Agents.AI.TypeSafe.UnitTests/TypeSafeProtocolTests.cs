// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.TypeSafe.UnitTests;

/// <summary>
/// Pins the System One wire shape without a network: what a request serializes to, and what the parser accepts and
/// refuses. The JSON fixtures follow the shapes documented in TypeSafe's API reference.
/// </summary>
public class TypeSafeProtocolTests
{
    private static JsonElement State(string text)
    {
        using JsonDocument document = JsonDocument.Parse(JsonSerializer.Serialize(text));
        return document.RootElement.Clone();
    }

    private static DecisionRequest Request(params DecisionQuestion[] questions) => new(State("I was charged twice."), questions);

    #region Request serialization

    [Fact]
    public void SerializeRequest_BinaryWithoutCriteria_WritesNoulAndOmitsCriteria()
    {
        var request = Request(new BinaryDecisionQuestion("refund", "Is the customer asking for money back?"));

        using JsonDocument doc = JsonDocument.Parse(TypeSafeProtocol.SerializeRequest(request, "jev-1.13.0"));
        JsonElement root = doc.RootElement;

        Assert.Equal("jev-1.13.0", root.GetProperty("model").GetString());
        Assert.Equal("I was charged twice.", root.GetProperty("state").GetString());
        JsonElement q = root.GetProperty("questions").GetProperty("refund");
        Assert.Equal("noul", q.GetProperty("type").GetString());
        Assert.Equal("Is the customer asking for money back?", q.GetProperty("instructions").GetString());
        Assert.False(q.TryGetProperty("criteria", out _));
    }

    [Fact]
    public void SerializeRequest_BinaryWithCriteria_WritesTrueAndFalse()
    {
        var request = Request(new BinaryDecisionQuestion("grounded", "Is it grounded?")
        {
            Criteria = new BinaryDecisionCriteria { TrueDescription = "Every claim is supported.", FalseDescription = "A claim is unsupported." },
        });

        using JsonDocument doc = JsonDocument.Parse(TypeSafeProtocol.SerializeRequest(request, "m"));
        JsonElement criteria = doc.RootElement.GetProperty("questions").GetProperty("grounded").GetProperty("criteria");

        Assert.Equal("Every claim is supported.", criteria.GetProperty("true").GetString());
        Assert.Equal("A claim is unsupported.", criteria.GetProperty("false").GetString());
    }

    [Fact]
    public void SerializeRequest_ChoiceAndScore_WriteMapAndArray()
    {
        var request = Request(
            new ChoiceDecisionQuestion("dept", "Which team?", [new("billing", "Payments"), new("tech", "Bugs"), new("other")]),
            new ScoreDecisionQuestion("mood", "How upset?", [new("calm"), new("concerned"), new("angry")]));

        using JsonDocument doc = JsonDocument.Parse(TypeSafeProtocol.SerializeRequest(request, "m"));
        JsonElement questions = doc.RootElement.GetProperty("questions");

        JsonElement dept = questions.GetProperty("dept");
        Assert.Equal("choice", dept.GetProperty("type").GetString());
        Assert.Equal("Payments", dept.GetProperty("criteria").GetProperty("billing").GetString());
        Assert.Equal("other", dept.GetProperty("criteria").GetProperty("other").GetString());

        JsonElement mood = questions.GetProperty("mood");
        Assert.Equal("score", mood.GetProperty("type").GetString());
        Assert.Equal(["calm", "concerned", "angry"], mood.GetProperty("criteria").EnumerateArray().Select(e => e.GetString()).ToArray());
    }

    [Fact]
    public void SerializeRequest_ObjectState_IsWrittenVerbatim()
    {
        using JsonDocument state = JsonDocument.Parse("{\"message\":\"hi\",\"order\":\"A-1\"}");
        var request = new DecisionRequest(state.RootElement.Clone(), [new BinaryDecisionQuestion("q", "?")]);

        using JsonDocument doc = JsonDocument.Parse(TypeSafeProtocol.SerializeRequest(request, "m"));

        Assert.Equal("A-1", doc.RootElement.GetProperty("state").GetProperty("order").GetString());
    }

    [Fact]
    public void SerializeRequest_NoQuestions_ThrowsInvalidRequest()
    {
        var request = new DecisionRequest(State("x"), []);

        var ex = Assert.Throws<DecisionClientException>(() => TypeSafeProtocol.SerializeRequest(request, "m"));

        Assert.Equal(DecisionFailureKind.InvalidRequest, ex.Kind);
    }

    [Fact]
    public void SerializeRequest_DuplicateIdsAddedAfterConstruction_ThrowsInvalidRequest()
    {
        var request = Request(new BinaryDecisionQuestion("a", "?"));
        request.Questions.Add(new BinaryDecisionQuestion("a", "again?"));

        var ex = Assert.Throws<DecisionClientException>(() => TypeSafeProtocol.SerializeRequest(request, "m"));

        Assert.Equal(DecisionFailureKind.InvalidRequest, ex.Kind);
        Assert.Contains("'a'", ex.Message);
    }

    [Fact]
    public void SerializeRequest_ChoiceAboveProviderMaximum_ThrowsInvalidRequestBeforeSending()
    {
        var choices = Enumerable.Range(0, TypeSafeProtocol.MaxChoices + 1).Select(i => new DecisionChoice($"c{i}"));
        var request = Request(new ChoiceDecisionQuestion("c", "Which?", choices));

        var ex = Assert.Throws<DecisionClientException>(() => TypeSafeProtocol.SerializeRequest(request, "m"));

        Assert.Equal(DecisionFailureKind.InvalidRequest, ex.Kind);
        Assert.False(ex.IsTransient);
    }

    [Fact]
    public void SerializeRequest_ScoreAboveProviderMaximum_ThrowsInvalidRequestBeforeSending()
    {
        var levels = Enumerable.Range(0, TypeSafeProtocol.MaxScoreLevels + 1).Select(i => new DecisionScoreLevel($"level {i}"));
        var request = Request(new ScoreDecisionQuestion("s", "How much?", levels));

        var ex = Assert.Throws<DecisionClientException>(() => TypeSafeProtocol.SerializeRequest(request, "m"));

        Assert.Equal(DecisionFailureKind.InvalidRequest, ex.Kind);
    }

    #endregion

    [Fact]
    public void SerializeRequest_ChoicesMutatedAfterConstruction_ThrowsInvalidRequest()
    {
        var question = new ChoiceDecisionQuestion("c", "Which?", [new("a"), new("b")]);
        question.Choices.Add(new DecisionChoice("a"));
        var duplicate = Request(question);

        var emptied = new ChoiceDecisionQuestion("c", "Which?", [new("a"), new("b")]);
        emptied.Choices.Clear();
        var empty = Request(emptied);

        Assert.Equal(DecisionFailureKind.InvalidRequest, Assert.Throws<DecisionClientException>(() => TypeSafeProtocol.SerializeRequest(duplicate, "m")).Kind);
        Assert.Equal(DecisionFailureKind.InvalidRequest, Assert.Throws<DecisionClientException>(() => TypeSafeProtocol.SerializeRequest(empty, "m")).Kind);
    }

    [Fact]
    public void SerializeRequest_LevelsMutatedAfterConstruction_ThrowsInvalidRequest()
    {
        var question = new ScoreDecisionQuestion("s", "How much?", [new("lo"), new("hi")]);
        question.Levels.Clear();
        question.Levels.Add(new DecisionScoreLevel("only"));

        var ex = Assert.Throws<DecisionClientException>(() => TypeSafeProtocol.SerializeRequest(Request(question), "m"));

        Assert.Equal(DecisionFailureKind.InvalidRequest, ex.Kind);
    }

    #region Response parsing

    private const string MixedResponse = """
        {
          "model": "jev-1.13.0",
          "answers": {
            "refund": { "type": "noul", "noul": 0.98 },
            "dept": { "type": "choice", "choice": "billing", "probabilities": { "billing": 0.82, "tech": 0.12, "other": 0.06 }, "confidence": 0.7 },
            "mood": { "type": "score", "score": 1.3, "legend": { "0": "calm", "1": "concerned", "2": "angry" }, "probabilities": { "0": 0.0, "1": 0.7, "2": 0.3 }, "confidence": 0.6 }
          },
          "usage": { "input_tokens": 120, "output_tokens": 0 }
        }
        """;

    private static DecisionRequest MixedRequest() => Request(
        new BinaryDecisionQuestion("refund", "?"),
        new ChoiceDecisionQuestion("dept", "?", [new("billing"), new("tech"), new("other")]),
        new ScoreDecisionQuestion("mood", "?", [new("calm"), new("concerned"), new("angry")]));

    [Fact]
    public void ParseResponse_MixedBatch_MapsEveryAnswerKind()
    {
        DecisionResponse response = TypeSafeProtocol.ParseResponse(MixedResponse, MixedRequest(), "h");

        Assert.Equal("jev-1.13.0", response.ModelId);
        Assert.Equal(3, response.Answers.Count);

        var refund = Assert.IsType<BinaryDecisionAnswer>(response.Answers["refund"]);
        Assert.Equal(0.98, refund.TrueProbability, precision: 6);

        var dept = Assert.IsType<ChoiceDecisionAnswer>(response.Answers["dept"]);
        Assert.Equal("billing", dept.SelectedChoice);
        Assert.Equal(0.12, dept.Probabilities["tech"], precision: 6);
        Assert.Equal(0.7, dept.Confidence!.Value, precision: 6);

        var mood = Assert.IsType<ScoreDecisionAnswer>(response.Answers["mood"]);
        Assert.Equal(1.3, mood.Score, precision: 6);
        Assert.Equal(0.7, mood.Probabilities[1], precision: 6);
        Assert.Equal(0.6, mood.Confidence!.Value, precision: 6);
        Assert.NotNull(mood.AdditionalProperties);
        Assert.True(mood.AdditionalProperties!.ContainsKey("legend"));

        Assert.NotNull(response.Usage);
        Assert.Equal(120, response.Usage!.InputTokenCount);
        Assert.Equal(0, response.Usage.OutputTokenCount);
        Assert.Equal(120, response.Usage.TotalTokenCount);
        Assert.IsType<JsonElement>(response.RawRepresentation);
        Assert.IsType<JsonElement>(refund.RawRepresentation);
    }

    [Fact]
    public void ParseResponse_OpenRouterExtras_SurfaceIdAndCost()
    {
        const string body = """
            { "id": "gen-1", "model": "typesafe/jev-1.13", "answers": { "q": { "type": "noul", "noul": 0.5 } }, "usage": { "input_tokens": 10, "output_tokens": 0, "cost": 0.00042 } }
            """;

        DecisionResponse response = TypeSafeProtocol.ParseResponse(body, Request(new BinaryDecisionQuestion("q", "?")), "h");

        Assert.Equal("gen-1", response.ResponseId);
        Assert.Equal(0.00042, Assert.IsType<double>(response.AdditionalProperties!["cost"]), precision: 8);
    }

    [Fact]
    public void ParseResponse_BinaryAnswer_HasNoConfidence()
    {
        const string body = """{ "model": "m", "answers": { "q": { "type": "noul", "noul": 0.5 } } }""";

        DecisionResponse response = TypeSafeProtocol.ParseResponse(body, Request(new BinaryDecisionQuestion("q", "?")), "h");

        var answer = Assert.IsType<BinaryDecisionAnswer>(response.Answers["q"]);
        Assert.Equal(0.5, answer.TrueProbability);
        Assert.Null(response.Usage);
    }

    [Theory]
    [InlineData("""{ "model": "m", "answers": { } }""", "no answer")]
    [InlineData("""{ "model": "m", "answers": { "q": { "type": "choice", "choice": "x", "probabilities": { "x": 1 } } } }""", "'choice' answer to a 'noul'")]
    [InlineData("""{ "model": "m", "answers": { "q": { "type": "noul", "noul": 1.5 } } }""", "out of range")]
    [InlineData("""{ "model": "m", "answers": { "q": { "type": "noul", "noul": "high" } } }""", "no numeric 'noul'")]
    [InlineData("""{ "answers": { "q": { "type": "noul", "noul": 0.5 } } }""", "'model'")]
    [InlineData("""{ "model": "m" }""", "'answers'")]
    [InlineData("""not json""", "not JSON")]
    [InlineData("""[1,2]""", "not an object")]
    public void ParseResponse_UnusableBody_ThrowsInvalidResponse(string body, string expectedFragment)
    {
        var ex = Assert.Throws<DecisionClientException>(() => TypeSafeProtocol.ParseResponse(body, Request(new BinaryDecisionQuestion("q", "?")), "h"));

        Assert.Equal(DecisionFailureKind.InvalidResponse, ex.Kind);
        Assert.False(ex.IsTransient);
        Assert.Contains(expectedFragment, ex.Message);
    }

    [Fact]
    public void ParseResponse_ChoiceSelectingUnknownChoice_ThrowsInvalidResponse()
    {
        const string body = """{ "model": "m", "answers": { "c": { "type": "choice", "choice": "nope", "probabilities": { "a": 0.5, "b": 0.5 } } } }""";
        var request = Request(new ChoiceDecisionQuestion("c", "?", [new("a"), new("b")]));

        var ex = Assert.Throws<DecisionClientException>(() => TypeSafeProtocol.ParseResponse(body, request, "h"));

        Assert.Contains("not one of the requested choices", ex.Message);
    }

    [Fact]
    public void ParseResponse_ChoiceSelectingExtraReturnedOption_ThrowsInvalidResponse()
    {
        // The provider returns a probability for an option that was never asked and selects it.
        const string body = """{ "model": "m", "answers": { "c": { "type": "choice", "choice": "nope", "probabilities": { "a": 0.3, "b": 0.3, "nope": 0.4 } } } }""";
        var request = Request(new ChoiceDecisionQuestion("c", "?", [new("a"), new("b")]));

        var ex = Assert.Throws<DecisionClientException>(() => TypeSafeProtocol.ParseResponse(body, request, "h"));

        Assert.Contains("not one of the requested choices", ex.Message);
    }

    [Theory]
    [InlineData(-0.1)]
    [InlineData(1.5)]
    public void ParseResponse_ScoreOutsideRequestedScale_ThrowsInvalidResponse(double score)
    {
        string body = $$"""{ "model": "m", "answers": { "s": { "type": "score", "score": {{score.ToString(System.Globalization.CultureInfo.InvariantCulture)}}, "probabilities": { "0": 0.5, "1": 0.5 }, "confidence": 0.5 } } }""";
        var request = Request(new ScoreDecisionQuestion("s", "?", [new("lo"), new("hi")]));

        var ex = Assert.Throws<DecisionClientException>(() => TypeSafeProtocol.ParseResponse(body, request, "h"));

        Assert.Contains("outside the requested scale", ex.Message);
    }

    [Fact]
    public void ParseResponse_ChoiceMissingAProbability_ThrowsInvalidResponse()
    {
        const string body = """{ "model": "m", "answers": { "c": { "type": "choice", "choice": "a", "probabilities": { "a": 1.0 } } } }""";
        var request = Request(new ChoiceDecisionQuestion("c", "?", [new("a"), new("b")]));

        var ex = Assert.Throws<DecisionClientException>(() => TypeSafeProtocol.ParseResponse(body, request, "h"));

        Assert.Contains("no probability for choice 'b'", ex.Message);
    }

    [Fact]
    public void ParseResponse_ScoreWithUnknownLevel_ThrowsInvalidResponse()
    {
        const string body = """{ "model": "m", "answers": { "s": { "type": "score", "score": 0.5, "probabilities": { "0": 0.5, "1": 0.5, "5": 0.0 }, "confidence": 0.5 } } }""";
        var request = Request(new ScoreDecisionQuestion("s", "?", [new("lo"), new("hi")]));

        var ex = Assert.Throws<DecisionClientException>(() => TypeSafeProtocol.ParseResponse(body, request, "h"));

        Assert.Contains("unknown level '5'", ex.Message);
    }

    #endregion

    #region Answer construction invariants

    [Fact]
    public void ChoiceDecisionAnswer_InvalidDistributionAtConstruction_Throws()
    {
        Assert.Throws<ArgumentOutOfRangeException>(() => new ChoiceDecisionAnswer("a", new Dictionary<string, double> { ["a"] = 1.5 }));
        Assert.Throws<ArgumentException>(() => new ChoiceDecisionAnswer("a", new Dictionary<string, double> { [" "] = 0.5 }));
        Assert.Throws<ArgumentOutOfRangeException>(() => new ScoreDecisionAnswer(0.5, new Dictionary<int, double> { [0] = double.NaN }));
    }

    #endregion

    #region Failure classification

    [Theory]
    [InlineData(401, DecisionFailureKind.Authentication, false)]
    [InlineData(403, DecisionFailureKind.Authentication, false)]
    [InlineData(400, DecisionFailureKind.InvalidRequest, false)]
    [InlineData(422, DecisionFailureKind.InvalidRequest, false)]
    [InlineData(429, DecisionFailureKind.RateLimited, true)]
    [InlineData(529, DecisionFailureKind.Overloaded, true)]
    [InlineData(500, DecisionFailureKind.ProviderUnavailable, true)]
    [InlineData(503, DecisionFailureKind.ProviderUnavailable, true)]
    [InlineData(418, DecisionFailureKind.Unknown, false)]
    public void ClassifyFailure_MapsStatusToKindAndTransience(int status, DecisionFailureKind kind, bool transient)
    {
        DecisionClientException ex = TypeSafeProtocol.ClassifyFailure(status, "{\"error\":\"x\"}", "h");

        Assert.Equal(kind, ex.Kind);
        Assert.Equal(transient, ex.IsTransient);
        Assert.Equal(status, ex.StatusCode);
        Assert.Contains($"HTTP {status}", ex.Message);
    }

    [Fact]
    public void ClassifyFailure_LongBody_IsExcerptedAndFlattened()
    {
        string body = "line1\nline2 " + new string('x', 2000);

        DecisionClientException ex = TypeSafeProtocol.ClassifyFailure(500, body, "h");

        Assert.DoesNotContain("\n", ex.Message);
        Assert.True(ex.Message.Length < 700);
    }

    #endregion
}
