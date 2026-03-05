// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics.CodeAnalysis;
using Microsoft.Shared.DiagnosticIds;

namespace Microsoft.Agents.AI.Compaction;

/// <summary>
/// A predicate that evaluates whether compaction should proceed based on current <see cref="MessageIndex"/> metrics.
/// </summary>
/// <param name="index">The current message index with group, token, message, and turn metrics.</param>
/// <returns><see langword="true"/> if compaction should proceed; <see langword="false"/> to skip.</returns>
[Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
public delegate bool CompactionTrigger(MessageIndex index);
