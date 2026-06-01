// Copyright (c) Microsoft. All rights reserved.

using A2A;

namespace Microsoft.Agents.AI.Hosting.A2A;

/// <summary>
/// Provides context for a custom A2A run mode decision.
/// </summary>
public sealed class A2ARunDecisionContext
{
    internal A2ARunDecisionContext(RequestContext requestContext)
    {
        this.RequestContext = requestContext;
    }

    /// <summary>
    /// Gets the request context of the incoming A2A request that triggered this run.
    /// </summary>
    public RequestContext RequestContext { get; }
}
