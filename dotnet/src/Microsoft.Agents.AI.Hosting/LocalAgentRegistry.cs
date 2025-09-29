// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;

namespace Microsoft.Agents.AI.Hosting;

internal sealed class LocalAgentRegistry
{
    public HashSet<string> AgentNames { get; } = [];
}
