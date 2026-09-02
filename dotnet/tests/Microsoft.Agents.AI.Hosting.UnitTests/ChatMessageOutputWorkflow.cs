// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Workflows;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Hosting.UnitTests;

internal static class ChatMessageOutputWorkflow
{
    internal static Workflow Build(string name)
    {
        var output = new OutputExecutor("output");
        return new WorkflowBuilder(output)
            .WithName(name)
            .WithOutputFrom(output)
            .Build();
    }

    private sealed class OutputExecutor(string id) : ChatProtocolExecutor(id)
    {
        protected override ValueTask TakeTurnAsync(
            List<ChatMessage> messages,
            IWorkflowContext context,
            bool? emitEvents,
            CancellationToken cancellationToken = default)
            => context.AddEventAsync(
                new WorkflowOutputEvent(new ChatMessage(ChatRole.Assistant, "workflow output"), this.Id),
                cancellationToken);
    }
}
