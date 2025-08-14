// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;

namespace Microsoft.Agents.Workflows.Execution;

internal class RunnerCheckpointData(Dictionary<ExecutorIdentity, List<ExportedState>> queuedMessages, List<ExternalRequest> outstandingRequests)
{
    public Dictionary<ExecutorIdentity, List<ExportedState>> QueuedMessages { get; } = queuedMessages;
    public List<ExternalRequest> OutstandingRequests { get; } = outstandingRequests;
}
