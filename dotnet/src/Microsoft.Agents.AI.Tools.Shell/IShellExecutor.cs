// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Threading;
using System.Threading.Tasks;

namespace Microsoft.Agents.AI.Tools.Shell;

/// <summary>
/// Pluggable backend that runs shell commands on behalf of a tool.
/// </summary>
/// <remarks>
/// <para>
/// <see cref="LocalShellTool"/> runs commands directly on the host (no
/// isolation; approval-in-the-loop is the security boundary).
/// <see cref="DockerShellTool"/> runs them inside a container with resource
/// limits, network isolation, and a non-root user — the container itself
/// is the security boundary, which is why it can be used without approval
/// gating for untrusted-input scenarios.
/// </para>
/// <para>
/// The interface is intentionally minimal so callers can plug in their own
/// executor (Firecracker microVM, remote SSH, WASI runtime, etc.) without
/// forking the framework. Mirrors the Python <c>ShellExecutor</c> Protocol
/// in <c>agent_framework_tools.shell._executor_base</c>.
/// </para>
/// </remarks>
public interface IShellExecutor : IAsyncDisposable
{
    /// <summary>
    /// Eagerly initialize the backend. Idempotent; subsequent calls are
    /// no-ops once the executor is started. For stateless executors this
    /// is typically a no-op.
    /// </summary>
    /// <param name="cancellationToken">Cancellation token.</param>
    Task StartAsync(CancellationToken cancellationToken = default);

    /// <summary>
    /// Tear down all backend resources. Idempotent; safe to call multiple
    /// times.
    /// </summary>
    /// <param name="cancellationToken">Cancellation token.</param>
    Task CloseAsync(CancellationToken cancellationToken = default);

    /// <summary>
    /// Run a single command and return its result. Implementations are
    /// expected to apply the configured per-command timeout and surface
    /// it via <see cref="ShellResult.TimedOut"/> + <c>ExitCode = 124</c>.
    /// </summary>
    /// <param name="command">The shell command to execute.</param>
    /// <param name="cancellationToken">Cancellation token.</param>
    Task<ShellResult> RunAsync(string command, CancellationToken cancellationToken = default);
}
