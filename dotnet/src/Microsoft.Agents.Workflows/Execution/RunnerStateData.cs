// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using Microsoft.Agents.Workflows.Checkpointing;

namespace Microsoft.Agents.Workflows.Execution;

internal class RunnerStateData(HashSet<string> instantiatedExecutors, Dictionary<ExecutorIdentity, List<ExportedState>> queuedMessages, List<ExternalRequest> outstandingRequests)
{
    public HashSet<string> InstantiatedExecutors { get; } = instantiatedExecutors;
    public Dictionary<ExecutorIdentity, List<ExportedState>> QueuedMessages { get; } = queuedMessages;
    public List<ExternalRequest> OutstandingRequests { get; } = outstandingRequests;
}
