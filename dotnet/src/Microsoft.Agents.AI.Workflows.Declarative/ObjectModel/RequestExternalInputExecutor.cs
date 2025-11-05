// Copyright (c) Microsoft. All rights reserved.

using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Workflows.Declarative.Events;
using Microsoft.Agents.AI.Workflows.Declarative.Extensions;
using Microsoft.Agents.AI.Workflows.Declarative.Interpreter;
using Microsoft.Agents.AI.Workflows.Declarative.PowerFx;
using Microsoft.Bot.ObjectModel;

namespace Microsoft.Agents.AI.Workflows.Declarative.ObjectModel;

internal sealed class RequestExternalInputExecutor(RequestExternalInput model, WorkflowFormulaState state)
    : DeclarativeActionExecutor<RequestExternalInput>(model, state)
{
    public static class Steps
    {
        public static string Input(string id) => $"{id}_{nameof(Input)}";
        public static string Capture(string id) => $"{id}_{nameof(Capture)}";
    }

    protected override bool IsDiscreteAction => false;
    protected override bool EmitResultEvent => false;

    protected override async ValueTask<object?> ExecuteAsync(IWorkflowContext context, CancellationToken cancellationToken = default)
    {
        ExternalInputRequest inputRequest = new(new AgentRunResponse());

        await context.SendMessageAsync(inputRequest, cancellationToken).ConfigureAwait(false);

        return default;
    }

    public async ValueTask CaptureResponseAsync(IWorkflowContext context, ExternalInputResponse response, CancellationToken cancellationToken)
    {
        await this.AssignAsync(this.Model.Variable?.Path, response.Messages.ToFormula(), context).ConfigureAwait(false);
    }
}
