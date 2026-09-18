// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics.CodeAnalysis;
using Microsoft.Shared.DiagnosticIds;

namespace Microsoft.Agents.AI.Hosting;

/// <summary>
/// Provides a compatibility wrapper for <see cref="AI.InMemoryAgentSessionStore"/>.
/// </summary>
/// <remarks>
/// New applications can use the core store directly without a hosting package dependency.
/// Sessions are partitioned by agent ID and the complete <see cref="AgentSessionStoreKey"/>.
/// </remarks>
[Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
public sealed class InMemoryAgentSessionStore : AI.InMemoryAgentSessionStore;
