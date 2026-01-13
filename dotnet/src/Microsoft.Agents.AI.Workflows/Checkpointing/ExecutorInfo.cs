// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.AI.Workflows.Checkpointing;

/// <summary>
/// Represents information about an executor in a workflow, including its type and identifier.
/// </summary>
/// <param name="ExecutorType">The type identifier of the executor.</param>
/// <param name="ExecutorId">The unique identifier of the executor instance.</param>
public sealed record class ExecutorInfo(TypeId ExecutorType, string ExecutorId)
{
    /// <summary>
    /// Determines whether this executor info matches a specific executor type by generic parameter.
    /// </summary>
    /// <typeparam name="T">The executor type to match against.</typeparam>
    /// <returns><c>true</c> if the executor type and ID match; otherwise, <c>false</c>.</returns>
    public bool IsMatch<T>() where T : Executor =>
        this.ExecutorType.IsMatch<T>()
            && this.ExecutorId == typeof(T).Name;

    /// <summary>
    /// Determines whether this executor info matches a given executor instance.
    /// </summary>
    /// <param name="executor">The executor instance to match against.</param>
    /// <returns><c>true</c> if the executor type and ID match; otherwise, <c>false</c>.</returns>
    public bool IsMatch(Executor executor) =>
        this.ExecutorType.IsMatch(executor.GetType())
            && this.ExecutorId == executor.Id;

    /// <summary>
    /// Determines whether this executor info matches a given executor binding.
    /// </summary>
    /// <param name="binding">The executor binding to match against.</param>
    /// <returns><c>true</c> if the executor type and ID match; otherwise, <c>false</c>.</returns>
    public bool IsMatch(ExecutorBinding binding) =>
        this.ExecutorType.IsMatch(binding.ExecutorType)
            && this.ExecutorId == binding.Id;
}
