// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Threading;
using System.Threading.Tasks;
using A2A;
using Microsoft.Extensions.Logging;

namespace Microsoft.Extensions.AI.Agents.A2A.Internal;

internal class A2AAgentTaskProcessor : A2AAgentCardProvider, IA2AAgentTaskProcessor
{
    public A2AAgentTaskProcessor(
        ILogger<A2AAgentTaskProcessor> logger,
        AIAgent agent)
        : base(logger, agent)
    {
    }

    public Task CreateTaskAsync(AgentTask task, CancellationToken token)
    {
        throw new System.NotImplementedException();
    }

    public Task UpdateTaskAsync(AgentTask task, CancellationToken token)
    {
        throw new System.NotImplementedException();
    }

    public Task CancelTaskAsync(AgentTask task, CancellationToken token)
    {
        throw new NotImplementedException();
    }
}
