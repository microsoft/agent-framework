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
/// <see cref="LocalShellExecutor"/> runs commands directly on the host (no
/// isolation; approval-in-the-loop is the security boundary).
/// <see cref="DockerShellExecutor"/> runs them inside a container with resource
/// limits, network isolation, and a non-root user.
/// </para>
/// <para>
/// This is an abstract class rather than an interface so the surface can be
/// extended in future versions (e.g., adding new lifecycle hooks) without
/// breaking existing third-party implementations. Mirrors the Python
/// <c>ShellExecutor</c> Protocol in
/// <c>agent_framework_tools.shell._executor_base</c>.
/// </para>
/// <para>
/// Lifetime: <see cref="InitializeAsync"/> is invoked at most once per
/// instance (idempotent); <see cref="DisposeAsync"/> tears the executor down
/// at the end of its life. There is no public Shutdown step — disposal is the
/// teardown.
/// </para>
/// <para>
/// <b>Concurrency and session ownership.</b> A single executor instance is
/// intended to serve a single conversation / agent session — i.e., a single
/// user. Stateless mode is safe to share across concurrent callers (each
/// <c>RunAsync</c> spawns a fresh process or container, so there is no
/// shared mutable state). Persistent mode is <em>not</em> shareable: a
/// single long-lived shell process backs every call, it carries mutable
/// state (working directory, exported variables, history, in-flight
/// background jobs) that is visible to every subsequent command, and
/// concurrent commands would interleave on its stdin/stdout. The framework
/// does not isolate one caller's state from another's. Build one executor
/// per session, treat it as owned by that session for its lifetime, and
/// dispose it when the session ends. If you register an executor with a DI
/// container, use a per-request / per-conversation scope, not a singleton.
/// </para>
/// </remarks>
public abstract class ShellExecutor : IAsyncDisposable
{
    /// <summary>
    /// Eagerly initialize the backend. Idempotent; subsequent calls are
    /// no-ops once the executor is started. For stateless executors this is
    /// typically a no-op (the default implementation returns
    /// <see cref="Task.CompletedTask"/>).
    /// </summary>
    /// <param name="cancellationToken">Cancellation token.</param>
    public virtual Task InitializeAsync(CancellationToken cancellationToken = default) => Task.CompletedTask;

    /// <summary>
    /// Run a single command and return its result. Implementations are
    /// expected to apply the configured per-command timeout and surface it
    /// via <see cref="ShellResult.TimedOut"/> + <c>ExitCode = 124</c>.
    /// </summary>
    /// <param name="command">The shell command to execute.</param>
    /// <param name="cancellationToken">Cancellation token.</param>
    public abstract Task<ShellResult> RunAsync(string command, CancellationToken cancellationToken = default);

    /// <inheritdoc />
    public abstract ValueTask DisposeAsync();
}
