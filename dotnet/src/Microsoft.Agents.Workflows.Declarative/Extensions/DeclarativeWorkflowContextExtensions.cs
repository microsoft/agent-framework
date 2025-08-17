// Copyright (c) Microsoft. All rights reserved.

using Azure.AI.Agents.Persistent;
using Azure.Core.Pipeline;
using Microsoft.Agents.Workflows.Declarative.ObjectModel;
using Microsoft.Agents.Workflows.Declarative.PowerFx;

namespace Microsoft.Agents.Workflows.Declarative.Extensions;

internal static class DeclarativeWorkflowContextExtensions
{
    public static WorkflowExecutionContext CreateActionContext(this DeclarativeWorkflowContext context, string rootId, WorkflowScopes scopes) =>
        new(RecalcEngineFactory.Create(scopes, context.MaximumExpressionLength, context.MaximumCallDepth), scopes);

    public static PersistentAgentsClient CreateClient(this DeclarativeWorkflowContext context)
    {
        PersistentAgentsAdministrationClientOptions clientOptions = new();

        if (context.HttpClient is not null)
        {
            clientOptions.Transport = new HttpClientTransport(context.HttpClient);
        }

        return new PersistentAgentsClient(context.ProjectEndpoint, context.ProjectCredentials, clientOptions);
    }
}
