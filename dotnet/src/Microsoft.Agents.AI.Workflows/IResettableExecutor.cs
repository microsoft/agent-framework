// Copyright (c) Microsoft. All rights reserved.

using System.Threading.Tasks;

namespace Microsoft.Agents.AI.Workflows;

/// <summary>
/// Provides a mechanism to return an executor to a 'reset' state, allowing a workflow containing
/// shared instances of it to be resued after a run is disposed.
/// </summary>
public interface IResettableExecutor
{
    /// <summary>
    /// Reset the executor
    /// </summary>
    /// <returns>A <see cref="ValueTask"/> representing the completion of the reset operation.</returns>
    ValueTask ResetAsync()
#if NET
    {
        return default;
    }
#else
    ;
#endif
}
