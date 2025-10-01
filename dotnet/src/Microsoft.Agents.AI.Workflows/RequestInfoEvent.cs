// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.AI.Workflows;

/// <summary>
/// Event triggered when a workflow executor request external information.
/// </summary>
public sealed class RequestInfoEvent(ExternalRequest request) : WorkflowEvent(request)
{
    /// <summary>
    /// The request to be serviced and data payload associated with it.
    /// </summary>
    public ExternalRequest Request => request;
}
