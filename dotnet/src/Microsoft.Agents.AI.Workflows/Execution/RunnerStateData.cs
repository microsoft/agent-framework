// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using Microsoft.Agents.AI.Workflows.Checkpointing;

namespace Microsoft.Agents.AI.Workflows.Execution;

internal sealed class RunnerStateData(HashSet<string> instantiatedExecutors, Dictionary<string, List<PortableMessageEnvelope>> queuedMessages, List<ExternalRequest> outstandingRequests)
{
    public HashSet<string> InstantiatedExecutors { get; } = instantiatedExecutors;
    public Dictionary<string, List<PortableMessageEnvelope>> QueuedMessages { get; } = queuedMessages;
    public List<ExternalRequest> OutstandingRequests { get; } = outstandingRequests;
}
