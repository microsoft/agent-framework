// Copyright (c) Microsoft. All rights reserved.

using System;

namespace Microsoft.Agents.AI.AgentHooks.UnitTests;

/// <summary>An argument value whose serialization throws (drives projection-failure halts).</summary>
internal sealed class PoisonedValue
{
    public string Boom => throw new ArgumentException("poisoned getter");
}
