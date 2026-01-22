// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;

namespace Microsoft.Agents.AI;

/// <summary>
/// Abstract base class for shell command execution.
/// </summary>
/// <remarks>
/// <para>
/// Implementations of this class handle the actual execution of shell commands.
/// The base class is designed to be extensible for different execution contexts
/// (local, SSH, container, etc.).
/// </para>
/// <para>
/// Executors return raw <see cref="ShellExecutorOutput"/> objects, which are
/// converted to <see cref="ShellCommandOutput"/> by <see cref="ShellTool"/>.
/// </para>
/// </remarks>
public abstract class ShellExecutor
{
    /// <summary>
    /// Executes the specified shell commands.
    /// </summary>
    /// <param name="commands">The commands to execute.</param>
    /// <param name="options">The options controlling execution behavior.</param>
    /// <param name="cancellationToken">The cancellation token.</param>
    /// <returns>Raw output data for each command.</returns>
    public abstract Task<IReadOnlyList<ShellExecutorOutput>> ExecuteAsync(
        IReadOnlyList<string> commands,
        ShellToolOptions options,
        CancellationToken cancellationToken = default);
}
