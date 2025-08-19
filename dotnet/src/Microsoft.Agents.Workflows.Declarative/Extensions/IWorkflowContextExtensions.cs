// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.Workflows.Declarative.PowerFx;
using Microsoft.Bot.ObjectModel;

namespace Microsoft.Agents.Workflows.Declarative.Extensions;

internal static class IWorkflowContextExtensions
{
    private const string ScopesKey = "__workflow__";

    public static async Task<WorkflowScopes> GetScopedStateAsync(this IWorkflowContext context, CancellationToken cancellationToken)
    {
        IEnumerable<Task<WorkflowScope?>> readTasks =
            VariableScopeNames.AllScopes.Select(
                scopeName => context.ReadStateAsync<WorkflowScope>(scopeName, ScopesKey).AsTask());

        WorkflowScope?[] scopes = await Task.WhenAll(readTasks).ConfigureAwait(false);
        Dictionary<string, WorkflowScope> scopesMap = scopes.OfType<WorkflowScope>().ToDictionary(scope => scope!.Name, scope => scope);

        return new WorkflowScopes(VariableScopeNames.AllScopes.ToDictionary(scopeName => scopeName, scopeName => GetScope(scopeName)));

        WorkflowScope GetScope(string scopeName)
        {
            if (!scopesMap.TryGetValue(scopeName, out WorkflowScope? scope))
            {
                scope = new WorkflowScope(scopeName);
            }
            return scope;
        }
    }

    public static async Task SetScopedStateAsync(this IWorkflowContext context, WorkflowScopes scopes, CancellationToken cancellationToken)
    {
        IEnumerable<Task> writeTasks = scopes.Select(scope => context.QueueStateUpdateAsync(scope.Name, scope, ScopesKey).AsTask());

        await Task.WhenAll(writeTasks).ConfigureAwait(false);
    }
}
