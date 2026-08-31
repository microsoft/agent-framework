// Copyright (c) Microsoft. All rights reserved.

using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Workflows;

namespace Microsoft.Agents.AI.Hosting.UnitTests;

/// <summary>
/// Builds a minimal non-chat-protocol workflow whose single executor accepts a <see cref="string"/> and yields
/// it back as output. Used to exercise the resume path for workflows whose start executor does not accept
/// <c>List&lt;ChatMessage&gt;</c> (so no <see cref="TurnToken"/> is sent).
/// </summary>
internal static class StringEchoWorkflow
{
    internal static Workflow Build()
    {
        var echo = new StringEchoExecutor("echo");
        return new WorkflowBuilder(echo)
            .WithOutputFrom(echo)
            .Build();
    }

    private sealed class StringEchoExecutor(string id) : Executor(id)
    {
        protected override ProtocolBuilder ConfigureProtocol(ProtocolBuilder protocolBuilder)
            => protocolBuilder.ConfigureRoutes(routeBuilder => routeBuilder.AddHandler<string>(this.HandleAsync))
                              .YieldsOutput<string>();

        private ValueTask HandleAsync(string input, IWorkflowContext context, CancellationToken cancellationToken = default)
            => context.YieldOutputAsync($"echo:{input}", cancellationToken);
    }
}
