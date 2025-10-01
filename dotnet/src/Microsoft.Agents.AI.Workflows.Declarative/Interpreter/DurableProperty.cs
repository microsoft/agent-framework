// Copyright (c) Microsoft. All rights reserved.

using System.Threading.Tasks;

namespace Microsoft.Agents.AI.Workflows.Declarative.Interpreter;

internal sealed class DurableProperty<TValue>(string name) where TValue : struct
{
    public async ValueTask<TValue> ReadAsync(IWorkflowContext context)
    {
        TValue? storedValue = await context.ReadStateAsync<TValue>(name).ConfigureAwait(false);
        return storedValue ?? default;
    }

    public ValueTask WriteAsync(IWorkflowContext context, TValue value) =>
        context.QueueStateUpdateAsync(name, value);
}
