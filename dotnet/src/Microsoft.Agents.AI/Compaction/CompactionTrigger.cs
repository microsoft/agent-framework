// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics.CodeAnalysis;
using Microsoft.Shared.DiagnosticIds;

namespace Microsoft.Agents.AI.Compaction;

/// <summary>
/// Defines a condition based on <see cref="CompactionMessageIndex"/> metrics used by a <see cref="CompactionStrategy"/>
/// to determine when to trigger compaction and when the target compaction threshold has been met.
/// </summary>
/// <param name="index">An index over conversation messages that provides group, token, message, and turn metrics.</param>
/// <returns><see langword="true"/> to indicate the condition has been met; otherwise <see langword="false"/>.</returns>
[Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
public delegate bool CompactionTrigger(CompactionMessageIndex index);
