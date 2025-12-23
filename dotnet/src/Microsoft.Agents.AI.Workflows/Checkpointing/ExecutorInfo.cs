// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.AI.Workflows.Checkpointing;

internal sealed record class ExecutorInfo(TypeId ExecutorType, string ExecutorId)
{
    public bool IsMatch<T>() where T : Executor =>
        this.ExecutorType.IsMatch<T>()
            && this.ExecutorId == typeof(T).Name;

    public bool IsMatch(Executor executor) =>
        this.ExecutorType.IsMatch(executor.GetType())
            && this.ExecutorId == executor.Id;

    public bool IsMatch(ExecutorBinding binding) =>
        this.ExecutorType.IsMatch(binding.ExecutorType)
            && this.ExecutorId == binding.Id;
}
