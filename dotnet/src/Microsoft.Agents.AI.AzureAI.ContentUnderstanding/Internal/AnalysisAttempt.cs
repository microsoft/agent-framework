// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Threading;
using System.Threading.Tasks;

namespace Microsoft.Agents.AI.AzureAI.ContentUnderstanding;

/// <summary>
/// One foreground analysis attempt plus, when the attempt timed out before the LRO reached a
/// terminal state, a <paramref name="Continuation"/> the background runner can resume to drive
/// the same operation to completion. Continuation is <see langword="null"/> when there is no
/// further polling work (success / failure / caller-cancelled).
/// </summary>
internal sealed record AnalysisAttempt(
    AnalysisOutcome Outcome,
    Func<CancellationToken, Task<AnalysisOutcome>>? Continuation);
