// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;

namespace Microsoft.Agents.AI.AzureAI.ContentUnderstanding.UnitTests;

/// <summary>
/// Returns canned <see cref="AnalysisOutcome"/>s keyed on the detected filename. Counts how
/// many times the analyze pipeline was invoked so unsupported-attachment / no-call assertions
/// can be made. Pair with <see cref="FakeResumer"/> when a test needs to drive the cross-turn
/// resume path.
/// </summary>
internal sealed class FakeAnalyzer
{
    private readonly Dictionary<string, Func<DetectedAttachment, AnalysisOutcome>> _byFilename = new(StringComparer.Ordinal);

    public int CallCount { get; private set; }

    public List<(string Filename, string AnalyzerId)> Calls { get; } = new();

    /// <summary>Pin a fixed outcome to the given filename.</summary>
    public FakeAnalyzer Returns(string filename, AnalysisOutcome outcome)
    {
        this._byFilename[filename] = _ => outcome;
        return this;
    }

    /// <summary>Factory variant so each invocation can synthesize a fresh outcome.</summary>
    public FakeAnalyzer Returns(string filename, Func<DetectedAttachment, AnalysisOutcome> factory)
    {
        this._byFilename[filename] = factory;
        return this;
    }

    public Task<AnalysisOutcome> AnalyzeAsync(
        DetectedAttachment attachment,
        string analyzerId,
        TimeSpan maxWait,
        CancellationToken cancellationToken)
    {
        _ = maxWait;
        _ = cancellationToken;

        this.CallCount++;
        this.Calls.Add((attachment.Filename, analyzerId));

        if (!this._byFilename.TryGetValue(attachment.Filename, out Func<DetectedAttachment, AnalysisOutcome>? factory))
        {
            throw new InvalidOperationException(
                $"FakeAnalyzer was not configured for filename '{attachment.Filename}'.");
        }

        return Task.FromResult(factory(attachment));
    }
}
