// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using Azure.AI.ContentUnderstanding;

namespace Microsoft.Agents.AI.AzureAI.ContentUnderstanding.UnitTests;

/// <summary>
/// Returns canned <see cref="AnalysisAttempt"/>s keyed on the detected filename. Counts how
/// many times the analyze pipeline was invoked so unsupported-attachment / no-call assertions
/// can be made.
/// </summary>
/// <remarks>
/// Each per-filename setup is a factory of <see cref="AnalysisAttempt"/>, which lets a test
/// freshly construct continuation tasks if the same filename is configured for multiple
/// invocations (rare in v1 because of the duplicate-filename guard).
/// </remarks>
internal sealed class FakeAnalyzer
{
    private readonly Dictionary<string, Func<DetectedAttachment, AnalysisAttempt>> _byFilename = new(StringComparer.Ordinal);

    public int CallCount { get; private set; }

    public List<(string Filename, string AnalyzerId)> Calls { get; } = new();

    /// <summary>Shorthand: foreground attempt with no background continuation.</summary>
    public FakeAnalyzer Returns(string filename, AnalysisOutcome outcome)
    {
        this._byFilename[filename] = _ => new AnalysisAttempt(outcome, Continuation: null);
        return this;
    }

    public FakeAnalyzer Returns(string filename, Func<DetectedAttachment, AnalysisOutcome> factory)
    {
        this._byFilename[filename] = att => new AnalysisAttempt(factory(att), Continuation: null);
        return this;
    }

    /// <summary>Configure both the foreground outcome and the background continuation.</summary>
    public FakeAnalyzer ReturnsAttempt(string filename, AnalysisAttempt attempt)
    {
        this._byFilename[filename] = _ => attempt;
        return this;
    }

    public FakeAnalyzer ReturnsAttempt(string filename, Func<DetectedAttachment, AnalysisAttempt> factory)
    {
        this._byFilename[filename] = factory;
        return this;
    }

    public Task<AnalysisAttempt> AnalyzeAsync(
        DetectedAttachment attachment,
        string analyzerId,
        TimeSpan maxWait,
        CancellationToken cancellationToken)
    {
        _ = maxWait;
        _ = cancellationToken;

        this.CallCount++;
        this.Calls.Add((attachment.Filename, analyzerId));

        if (!this._byFilename.TryGetValue(attachment.Filename, out Func<DetectedAttachment, AnalysisAttempt>? factory))
        {
            throw new InvalidOperationException(
                $"FakeAnalyzer was not configured for filename '{attachment.Filename}'.");
        }

        return Task.FromResult(factory(attachment));
    }
}
