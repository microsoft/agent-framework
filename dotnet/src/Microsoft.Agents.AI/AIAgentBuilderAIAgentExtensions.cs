// Copyright (c) Microsoft. All rights reserved.

using System;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI;

/// <summary>Provides extension methods for working with <see cref="AIAgent"/> in the context of <see cref="AIAgentBuilder"/>.</summary>
public static class AIAgentBuilderAIAgentExtensions
{
    /// <summary>Creates a new <see cref="AIAgentBuilder"/> using <paramref name="innerAgent"/> as its inner agent.</summary>
    /// <param name="innerAgent">The agent to use as the inner agent.</param>
    /// <returns>The new <see cref="AIAgentBuilder"/> instance.</returns>
    /// <remarks>
    /// This method is equivalent to using the <see cref="AIAgentBuilder"/> constructor directly,
    /// specifying <paramref name="innerAgent"/> as the inner agent.
    /// </remarks>
    /// <exception cref="ArgumentNullException"><paramref name="innerAgent"/> is <see langword="null"/>.</exception>
    public static AIAgentBuilder AsBuilder(this AIAgent innerAgent)
    {
        _ = Throw.IfNull(innerAgent);

        return new AIAgentBuilder(innerAgent);
    }
}
