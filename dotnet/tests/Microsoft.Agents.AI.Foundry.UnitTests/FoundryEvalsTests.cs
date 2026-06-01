// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Linq;
using System.Text.Json;

namespace Microsoft.Agents.AI.Foundry.UnitTests;

/// <summary>
/// Tests for <see cref="FoundryEvals"/> internal helpers.
/// </summary>
public sealed class FoundryEvalsTests
{
    [Fact]
    public void FilterToolEvaluators_AllToolEvaluators_NoTools_ThrowsArgumentException()
    {
        // All configured evaluators are tool-type, but no items have tools.
        var evaluators = new FoundryEvaluatorSpec[] { "tool_call_accuracy", "tool_selection" };

        var ex = Assert.Throws<ArgumentException>(
            () => FoundryEvals.FilterToolEvaluators(evaluators, hasTools: false));

        Assert.Contains("tool definitions", ex.Message);
    }

    [Fact]
    public void FilterToolEvaluators_MixedEvaluators_NoTools_FiltersToolOnes()
    {
        var evaluators = new FoundryEvaluatorSpec[] { "relevance", "tool_call_accuracy", "coherence" };

        var result = FoundryEvals.FilterToolEvaluators(evaluators, hasTools: false);

        Assert.Equal(2, result.Length);
        Assert.Contains((FoundryEvaluatorSpec)"relevance", result);
        Assert.Contains((FoundryEvaluatorSpec)"coherence", result);
        Assert.DoesNotContain((FoundryEvaluatorSpec)"tool_call_accuracy", result);
    }

    [Fact]
    public void FilterToolEvaluators_HasTools_ReturnsAllEvaluators()
    {
        var evaluators = new FoundryEvaluatorSpec[] { "relevance", "tool_call_accuracy" };

        var result = FoundryEvals.FilterToolEvaluators(evaluators, hasTools: true);

        Assert.Equal(evaluators, result);
    }

    [Fact]
    public void FilterToolEvaluators_PreservesRubricRefs_WhenNoTools()
    {
        // Rubric refs are tool-aware but never tool-required, so they must survive filtering
        // when no items carry tool definitions.
        var rubric = new GeneratedEvaluatorRef("policy-rubric", Version: "3");
        var evaluators = new FoundryEvaluatorSpec[] { "relevance", rubric, "tool_call_accuracy" };

        var result = FoundryEvals.FilterToolEvaluators(evaluators, hasTools: false);

        Assert.Equal(2, result.Length);
        Assert.Contains((FoundryEvaluatorSpec)"relevance", result);
        Assert.Contains(result, s => s.IsRubric && s.GeneratedRef!.Name == "policy-rubric");
        Assert.DoesNotContain((FoundryEvaluatorSpec)"tool_call_accuracy", result);
    }

    // ---------------------------------------------------------------
    // FoundryEvals.ParseRubricScores tests
    // ---------------------------------------------------------------

    [Fact]
    public void ParseRubricScores_CanonicalDimensionScoresKey_ParsesAllFields()
    {
        // Per Microsoft Learn docs, runtime output uses properties.dimension_scores.
        const string Json = """
        {
          "properties": {
            "dimension_scores": [
              { "id": "intent_recognition", "score": 5, "applicable": true, "weight": 9, "reason": "Identified correctly." },
              { "id": "general_quality",    "score": 4, "applicable": true, "weight": 5, "reason": "Strong overall." }
            ]
          }
        }
        """;
        using var doc = JsonDocument.Parse(Json);

        var result = FoundryEvals.ParseRubricScores(doc.RootElement);

        Assert.NotNull(result);
        Assert.Equal(2, result!.Count);
        Assert.Equal(["intent_recognition", "general_quality"], result.Select(r => r.Id));
        Assert.Equal([5, 4], result.Select(r => r.Score));
        Assert.Equal([9, 5], result.Select(r => r.Weight));
        Assert.True(result[0].Applicable);
        Assert.Equal("Identified correctly.", result[0].Reason);
    }

    [Fact]
    public void ParseRubricScores_LegacyRubricScoresKey_StillSupported()
    {
        // Preview builds used the rubric_scores key; we still accept it for back-compat.
        const string Json = """
        {
          "properties": {
            "rubric_scores": [
              { "id": "a", "score": 3, "applicable": true, "weight": 1, "reason": "r" }
            ]
          }
        }
        """;
        using var doc = JsonDocument.Parse(Json);

        var result = FoundryEvals.ParseRubricScores(doc.RootElement);

        Assert.NotNull(result);
        Assert.Single(result!);
        Assert.Equal("a", result[0].Id);
    }

    [Fact]
    public void ParseRubricScores_TopLevelKey_FallsBack()
    {
        // Defensive fallback when SDK shape omits the 'properties' wrapper.
        const string Json = """
        {
          "dimension_scores": [
            { "id": "x", "score": 2, "applicable": true, "weight": 1, "reason": "" }
          ]
        }
        """;
        using var doc = JsonDocument.Parse(Json);

        var result = FoundryEvals.ParseRubricScores(doc.RootElement);

        Assert.NotNull(result);
        Assert.Single(result!);
        Assert.Equal("x", result[0].Id);
    }

    [Fact]
    public void ParseRubricScores_NoRubricKeys_ReturnsNull()
    {
        const string Json = """
        { "properties": { "other_field": [] } }
        """;
        using var doc = JsonDocument.Parse(Json);

        var result = FoundryEvals.ParseRubricScores(doc.RootElement);

        Assert.Null(result);
    }

    [Fact]
    public void ParseRubricScores_SkipsMalformedEntries()
    {
        // Entries missing weight or applicable are skipped, but well-formed siblings are kept.
        const string Json = """
        {
          "properties": {
            "dimension_scores": [
              { "id": "good", "score": 3, "applicable": true, "weight": 1, "reason": "ok" },
              { "id": "bad-no-weight", "score": 2, "applicable": true, "reason": "x" },
              { "id": "bad-no-applicable", "score": 2, "weight": 1, "reason": "x" }
            ]
          }
        }
        """;
        using var doc = JsonDocument.Parse(Json);

        var result = FoundryEvals.ParseRubricScores(doc.RootElement);

        Assert.NotNull(result);
        Assert.Single(result!);
        Assert.Equal("good", result[0].Id);
    }

    [Fact]
    public void ParseRubricScores_NonApplicableDimension_KeepsNullScoreWhenMissing()
    {
        // Non-applicable dimensions can legitimately omit score (or set it to null).
        const string Json = """
        {
          "properties": {
            "dimension_scores": [
              { "id": "skipped", "applicable": false, "weight": 5, "reason": "n/a" }
            ]
          }
        }
        """;
        using var doc = JsonDocument.Parse(Json);

        var result = FoundryEvals.ParseRubricScores(doc.RootElement);

        Assert.NotNull(result);
        Assert.Single(result!);
        Assert.Equal("skipped", result[0].Id);
        Assert.False(result[0].Applicable);
        Assert.Null(result[0].Score);
    }
}
