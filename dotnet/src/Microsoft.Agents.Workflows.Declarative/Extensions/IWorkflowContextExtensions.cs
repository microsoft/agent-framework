// Copyright (c) Microsoft. All rights reserved.

using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.Workflows.Declarative.PowerFx;

namespace Microsoft.Agents.Workflows.Declarative.Extensions;

internal static class IWorkflowContextExtensions
{
    private const string ScopesKey = "__scopes__";

    public static async Task<WorkflowScopes> GetScopedStateAsync(this IWorkflowContext context, CancellationToken cancellationToken) =>
        await context.ReadWorkflowStateAsync<WorkflowScopes>(ScopesKey).ConfigureAwait(false) ??
        new();

    public static async Task SetScopedStateAsync(this IWorkflowContext context, WorkflowScopes scopes, CancellationToken cancellationToken) =>
        await context.QueueWorkflowStateUpdateAsync(ScopesKey, scopes).ConfigureAwait(false);
}
