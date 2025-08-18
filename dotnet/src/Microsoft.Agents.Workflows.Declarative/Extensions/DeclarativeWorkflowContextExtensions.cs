// Copyright (c) Microsoft. All rights reserved.

using Azure.AI.Agents.Persistent;
using Azure.Core.Pipeline;
using Microsoft.Agents.Workflows.Declarative.PowerFx;
using Microsoft.PowerFx;

namespace Microsoft.Agents.Workflows.Declarative.Extensions;

internal static class DeclarativeWorkflowContextExtensions
{
    public static RecalcEngine CreateRecalcEngine(this DeclarativeWorkflowOptions context) =>
        RecalcEngineFactory.Create(context.MaximumExpressionLength, context.MaximumCallDepth);

    public static PersistentAgentsClient CreateClient(this DeclarativeWorkflowOptions context)
    {
        PersistentAgentsAdministrationClientOptions clientOptions = new();

        if (context.HttpClient is not null)
        {
            clientOptions.Transport = new HttpClientTransport(context.HttpClient);
        }

        return new PersistentAgentsClient(context.ProjectEndpoint, context.ProjectCredentials, clientOptions);
    }
}
