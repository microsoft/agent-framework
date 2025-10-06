// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Threading.Tasks;
using Microsoft.Shared.Diagnostics;

using ExecutorFactoryF = System.Func<string, System.Threading.Tasks.ValueTask<Microsoft.Agents.AI.Workflows.Executor>>;

namespace Microsoft.Agents.AI.Workflows;

internal sealed class ExecutorRegistration(string id, Type executorType, ExecutorFactoryF provider, object? rawData)
{
    public string Id { get; } = Throw.IfNullOrEmpty(id);
    public Type ExecutorType { get; } = Throw.IfNull(executorType);
    private ExecutorFactoryF ProviderAsync { get; } = Throw.IfNull(provider);
    public bool IsNotExecutorInstance { get; } = rawData is not Executor;
    public bool IsUnresettableSharedInstance { get; } = rawData is Executor && rawData is not IResettableExecutor;

    internal async ValueTask<bool> TryResetAsync()
    {
        if (this.IsUnresettableSharedInstance)
        {
            return false;
        }

        // If this is not an executor instance, this is a factory, and the expectation is that the factory will
        // create separate instances of executors.
        if (this.IsNotExecutorInstance)
        {
            return true;
        }

        // Technically we definitely know this is true, since if rawData is an Executor, if it was not resettable
        // then we would have returned in the first condition, and if rawData is not an Executor, we would have
        // returned in the second condition. That only leaves the possibility of rawData is Executor and also
        // IResettableExecutor.
        if (this.RawExecutorishData is IResettableExecutor resettableExecutor)
        {
            await resettableExecutor.ResetAsync().ConfigureAwait(false);
            return true;
        }

        return false;
    }

    internal object? RawExecutorishData { get; } = rawData;

    public override string ToString() => $"{this.ExecutorType.Name}({this.Id})";

    private Executor CheckId(Executor executor)
    {
        if (executor.Id != this.Id)
        {
            throw new InvalidOperationException(
                $"Executor ID mismatch: expected '{this.Id}', but got '{executor.Id}'.");
        }

        return executor;
    }

    public async ValueTask<Executor> CreateInstanceAsync(string runId) => this.CheckId(await this.ProviderAsync(runId).ConfigureAwait(false));
}
