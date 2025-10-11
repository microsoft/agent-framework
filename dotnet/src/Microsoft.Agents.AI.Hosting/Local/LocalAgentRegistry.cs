// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;

namespace Microsoft.Agents.AI.Hosting.Local;

internal sealed class LocalAgentRegistry
{
    public HashSet<string> AgentNames { get; } = [];
}
