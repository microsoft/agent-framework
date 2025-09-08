// Copyright (c) Microsoft. All rights reserved.

using System.Threading;

#pragma warning disable CS0419 // Ambiguous reference in cref attribute

namespace Microsoft.Extensions.AI.Agents;

/// <summary>
/// Temporary place-holder for new middleware contexts
/// </summary>
public sealed class OtherCallbackContext : CallbackContext
{
    /// <summary>
    /// Temporary for further contexts
    /// </summary>
    /// <param name="agent">Agent</param>
    /// <param name="cancellationToken"></param>
    internal OtherCallbackContext(AIAgent agent, CancellationToken cancellationToken) : base(agent, cancellationToken)
    {
    }
}
