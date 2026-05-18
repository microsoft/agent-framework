// Copyright (c) Microsoft. All rights reserved.

using System;
using Azure.AI.ContentUnderstanding;

namespace Microsoft.Agents.AI.AzureAI.ContentUnderstanding;

/// <summary>
/// Result of one analysis attempt. <see cref="Completed"/> distinguishes "finished within
/// MaxWait" (Result is set) from "timed out" (OperationId may be set for Phase 6 resumption)
/// from "failed" (Error is set).
/// </summary>
internal sealed record AnalysisOutcome(
    bool Completed,
    AnalysisResult? Result,
    string? OperationId,
    Exception? Error,
    TimeSpan Duration);
