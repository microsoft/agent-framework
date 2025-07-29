// Copyright (c) Microsoft. All rights reserved.

using System.Threading.Tasks;

namespace Microsoft.Agents.Workflows.Core;

/// <summary>
/// Helper class to work around lack of proper ValueTask support in .NET Framework.
/// </summary>
internal static class CompletedValueTaskSource
{
    internal static ValueTask Completed =>
#if NET5_0_OR_GREATER
        ValueTask.CompletedTask;
#else
        new(Task.CompletedTask);
#endif

    internal static ValueTask<T> FromResult<T>(T result)
    {
#if NET5_0_OR_GREATER
        return new ValueTask<T>(result);
#else
        return new ValueTask<T>(Task.FromResult(result));
#endif
    }
}
