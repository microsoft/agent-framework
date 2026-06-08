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
        var evaluators = new[] { "tool_call_accuracy", "tool_selection" };

        var ex = Assert.Throws<ArgumentException>(
            () => FoundryEvals.FilterToolEvaluators(evaluators, hasTools: false));

        Assert.Contains("tool definitions", ex.Message);
    }

    [Fact]
    public void FilterToolEvaluators_MixedEvaluators_NoTools_FiltersToolOnes()
    {
        var evaluators = new[] { "relevance", "tool_call_accuracy", "coherence" };

        var result = FoundryEvals.FilterToolEvaluators(evaluators, hasTools: false);

        Assert.Equal(2, result.Length);
        Assert.Contains("relevance", result);
        Assert.Contains("coherence", result);
        Assert.DoesNotContain("tool_call_accuracy", result);
    }

    [Fact]
    public void FilterToolEvaluators_HasTools_ReturnsAllEvaluators()
    {
        var evaluators = new[] { "relevance", "tool_call_accuracy" };

        var result = FoundryEvals.FilterToolEvaluators(evaluators, hasTools: true);

        Assert.Equal(evaluators, result);
    }
}
