// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;

namespace Microsoft.Agents.AI.AzureAI.ContentUnderstanding.UnitTests;

/// <summary>
/// Returns canned <see cref="AnalysisOutcome"/>s keyed on the in-flight CU operation id.
/// Drives <see cref="ContentUnderstandingContextProvider.ResumeOverride"/> in the same way
/// <see cref="FakeAnalyzer"/> drives <c>AnalyzeOverride</c>.
/// </summary>
internal sealed class FakeResumer
{
    private readonly Dictionary<string, Func<AnalysisOutcome>> _byOperationId = new(StringComparer.Ordinal);

    public int CallCount { get; private set; }

    public List<(string OperationId, string AnalyzerId)> Calls { get; } = new();

    public FakeResumer Returns(string operationId, AnalysisOutcome outcome)
    {
        this._byOperationId[operationId] = () => outcome;
        return this;
    }

    public FakeResumer Returns(string operationId, Func<AnalysisOutcome> factory)
    {
        this._byOperationId[operationId] = factory;
        return this;
    }

    public Task<AnalysisOutcome> ResumeAsync(
        string operationId,
        string rehydrationTokenJson,
        string analyzerId,
        TimeSpan maxWait,
        CancellationToken cancellationToken)
    {
        _ = rehydrationTokenJson;
        _ = maxWait;
        _ = cancellationToken;

        this.CallCount++;
        this.Calls.Add((operationId, analyzerId));

        if (!this._byOperationId.TryGetValue(operationId, out Func<AnalysisOutcome>? factory))
        {
            throw new InvalidOperationException(
                $"FakeResumer was not configured for operationId '{operationId}'.");
        }

        return Task.FromResult(factory());
    }
}
