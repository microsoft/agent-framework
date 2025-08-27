// Copyright (c) Microsoft. All rights reserved.

using System;
using Microsoft.Shared.Diagnostics;

using ExecutorFactoryF = System.Func<Microsoft.Agents.Workflows.Executor>;

namespace Microsoft.Agents.Workflows;

internal class ExecutorRegistration(string id, Type executorType, ExecutorFactoryF provider, object? rawData)
{
    public string Id { get; } = Throw.IfNullOrEmpty(id);
    public Type ExecutorType { get; } = Throw.IfNull(executorType);
    public ExecutorFactoryF Provider { get; } = Throw.IfNull(provider);

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

    public Executor CreateInstance() => this.CheckId(this.Provider());
}
