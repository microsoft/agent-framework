// Copyright (c) Microsoft. All rights reserved.

using System;

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
}
