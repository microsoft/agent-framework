// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;

namespace Microsoft.Agents.AI.Workflows;

internal sealed class AIAgentIDEqualityComparer : IEqualityComparer<AIAgent>
{
    public static AIAgentIDEqualityComparer Instance { get; } = new();
    public bool Equals(AIAgent? x, AIAgent? y) => x?.Id == y?.Id;
    public int GetHashCode([DisallowNull] AIAgent obj) => obj?.GetHashCode() ?? 0;
}
