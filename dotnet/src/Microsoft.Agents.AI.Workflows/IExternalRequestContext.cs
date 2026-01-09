// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI.Workflows.Execution;

namespace Microsoft.Agents.AI.Workflows;

internal interface IExternalRequestContext
{
    IExternalRequestSink RegisterPort(RequestPort port);
}
