// Copyright (c) Microsoft. All rights reserved.

using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Workflows;

namespace Microsoft.Agents.AI.Hosting.UnitTests;

/// <summary>
/// Builds a workflow whose start executor accepts a typed <see cref="WriterBrief"/> (not
/// <c>List&lt;ChatMessage&gt;</c>) and yields a formatted string. Used to demonstrate that an application can
/// adapt Responses input into a workflow's native start-executor input via the generic
/// <c>RunOrResumeAsync&lt;TInput&gt;</c>.
/// </summary>
internal static class BriefWorkflow
{
    internal sealed record WriterBrief(string Topic, string Style);

    internal static Workflow Build()
    {
        var writer = new BriefExecutor("brief");
        return new WorkflowBuilder(writer)
            .WithOutputFrom(writer)
            .Build();
    }

    private sealed class BriefExecutor(string id) : Executor(id)
    {
        protected override ProtocolBuilder ConfigureProtocol(ProtocolBuilder protocolBuilder)
            => protocolBuilder.ConfigureRoutes(routeBuilder => routeBuilder.AddHandler<WriterBrief>(this.HandleAsync))
                              .YieldsOutput<string>();

        private ValueTask HandleAsync(WriterBrief brief, IWorkflowContext context, CancellationToken cancellationToken = default)
            => context.YieldOutputAsync($"[{brief.Style}] {brief.Topic}", cancellationToken);
    }
}
