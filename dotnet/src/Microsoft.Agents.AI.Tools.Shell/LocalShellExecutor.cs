// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.Diagnostics;
using System.IO;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Tools.Shell;

/// <summary>
/// Cross-platform shell tool. <b>Approval-in-the-loop is the security boundary.</b>
/// </summary>
/// <remarks>
/// <para>
/// <c>LocalShellExecutor</c> launches a real shell (bash/sh on POSIX, pwsh/powershell/cmd on Windows)
/// to execute commands emitted by an agent. Output is captured, optionally truncated, and a
/// timeout terminates the process tree.
/// </para>
/// <para>
/// Both <see cref="ShellMode.Stateless"/> (every call spawns a fresh shell) and
/// <see cref="ShellMode.Persistent"/> (a long-lived shell that preserves <c>cd</c>, exported
/// variables, etc. across calls via a sentinel protocol) are supported. Persistent mode is the
/// recommended default for coding agents because it eliminates a class of "agent runs cd and
/// then runs the wrong path" failures.
/// </para>
/// <para>
/// <b>Single-session ownership.</b> A persistent-mode executor is owned by a single
/// conversation / agent session — i.e., a single user. The backing shell process carries
/// mutable state (working directory, exported variables, shell history, background jobs)
/// that is visible to every command run through it, and a single stdin/stdout pipe
/// serializes every call. Do not share one instance across users, tenants, or concurrent
/// conversations: state leaks between them and commands queue behind each other. Create
/// one <see cref="LocalShellExecutor"/> per session, dispose it when the session ends, and
/// in DI scenarios register it with a per-session scope (not as a singleton). If a shared
/// instance is genuinely required, use <see cref="ShellMode.Stateless"/>.
/// </para>
/// <para>
/// <b>Threat model.</b> The deny list is a guardrail, not a security boundary. Real isolation
/// requires either (a) approval-in-the-loop, where every command is reviewed by a human via the
/// harness <c>ToolApprovalAgent</c> (this is the default; see
/// <see cref="AsAIFunction(string, string?, bool)"/>), or (b) container isolation
/// (<c>DockerShellExecutor</c>). To produce an unapproved <see cref="AIFunction"/> you must pass
/// <c>acknowledgeUnsafe: true</c> at construction; otherwise <see cref="AsAIFunction"/> will
/// refuse to return a non-approval-gated function.
/// </para>
/// </remarks>
public sealed class LocalShellExecutor : ShellExecutor
{
    /// <summary>
    /// Recommended default per-command timeout (30 seconds). Pass this
    /// explicitly via <see cref="LocalShellExecutorOptions.Timeout"/> to opt
    /// in. Note that <see langword="null"/> (the property default) means
    /// <em>no timeout</em>.
    /// </summary>
    public static readonly TimeSpan DefaultTimeout = TimeSpan.FromSeconds(30);

    private readonly ShellMode _mode;
    private readonly ShellPolicy _policy;
    private readonly ResolvedShell _shell;
    private readonly TimeSpan? _timeout;
    private readonly int _maxOutputBytes;
    private readonly string? _workingDirectory;
    private readonly bool _confineWorkingDirectory;
    private readonly IReadOnlyDictionary<string, string?>? _environment;
    private readonly bool _cleanEnvironment;
    private readonly bool _acknowledgeUnsafe;
    private ShellSession? _session;
    private readonly object _sessionGate = new();

    /// <summary>
    /// Initializes a new instance of the <see cref="LocalShellExecutor"/>
    /// class with default options.
    /// </summary>
    public LocalShellExecutor() : this(new LocalShellExecutorOptions())
    {
    }

    /// <summary>
    /// Initializes a new instance of the <see cref="LocalShellExecutor"/> class.
    /// </summary>
    /// <param name="options">Configuration. <see langword="null"/> selects defaults.</param>
    public LocalShellExecutor(LocalShellExecutorOptions options)
    {
        options ??= new LocalShellExecutorOptions();

        if (options.MaxOutputBytes <= 0)
        {
            throw new ArgumentOutOfRangeException(nameof(options), $"{nameof(options.MaxOutputBytes)} must be positive.");
        }
        if (options.Shell is not null && options.ShellArgv is not null)
        {
            throw new ArgumentException($"Pass either {nameof(options.Shell)} or {nameof(options.ShellArgv)}, not both.", nameof(options));
        }

        this._mode = options.Mode;
        this._policy = options.Policy ?? new ShellPolicy();
        this._shell = options.ShellArgv is not null ? ShellResolver.ResolveArgv(options.ShellArgv) : ShellResolver.Resolve(options.Shell);
        this._timeout = options.Timeout;
        this._maxOutputBytes = options.MaxOutputBytes;
        this._workingDirectory = options.WorkingDirectory;
        this._confineWorkingDirectory = options.ConfineWorkingDirectory;
        this._environment = options.Environment;
        this._cleanEnvironment = options.CleanEnvironment;
        this._acknowledgeUnsafe = options.AcknowledgeUnsafe;

        if (this._mode == ShellMode.Persistent && this._shell.Kind == ShellKind.Cmd)
        {
            throw new NotSupportedException(
                "Persistent mode is not supported for cmd.exe — use pwsh/powershell or override the shell with AGENT_FRAMEWORK_SHELL.");
        }
    }

    /// <summary>Gets the resolved shell binary that will host commands.</summary>
    public string ResolvedShellBinary => this._shell.Binary;

    /// <summary>
    /// Run a single command and return its result.
    /// </summary>
    /// <param name="command">The command to execute.</param>
    /// <param name="cancellationToken">Cancellation token.</param>
    /// <returns>The captured <see cref="ShellResult"/>.</returns>
    /// <exception cref="ShellCommandRejectedException">Thrown when the policy denies the command.</exception>
    public override async Task<ShellResult> RunAsync(string command, CancellationToken cancellationToken = default)
    {
        if (command is null)
        {
            throw new ArgumentNullException(nameof(command));
        }

        var decision = this._policy.Evaluate(new ShellRequest(command, this._workingDirectory));
        if (!decision.Allowed)
        {
            throw new ShellCommandRejectedException(
                $"Command rejected by policy: {decision.Reason ?? "(unspecified)"}");
        }

        return this._mode == ShellMode.Persistent
            ? await this.RunPersistentAsync(command, cancellationToken).ConfigureAwait(false)
            : await this.RunStatelessAsync(command, cancellationToken).ConfigureAwait(false);
    }

    private async Task<ShellResult> RunPersistentAsync(string command, CancellationToken cancellationToken)
    {
        ShellSession session;
        lock (this._sessionGate)
        {
            this._session ??= new ShellSession(
                this._shell,
                this._workingDirectory,
                this._confineWorkingDirectory,
                this._environment,
                this._cleanEnvironment,
                this._maxOutputBytes);
            session = this._session;
        }
        return await session.RunAsync(command, this._timeout, cancellationToken).ConfigureAwait(false);
    }

    /// <inheritdoc />
    public override Task InitializeAsync(CancellationToken cancellationToken = default)
    {
        if (this._mode != ShellMode.Persistent)
        {
            return Task.CompletedTask;
        }
        ShellSession session;
        lock (this._sessionGate)
        {
            this._session ??= new ShellSession(
                this._shell,
                this._workingDirectory,
                this._confineWorkingDirectory,
                this._environment,
                this._cleanEnvironment,
                this._maxOutputBytes);
            session = this._session;
        }
        // Force a tiny no-op so the session spawns now rather than lazily.
        return session.RunAsync(this._shell.Kind == ShellKind.PowerShell ? "$null" : ":", this._timeout, cancellationToken);
    }

    private async Task<ShellResult> RunStatelessAsync(string command, CancellationToken cancellationToken)
    {
        var startInfo = new ProcessStartInfo
        {
            FileName = this._shell.Binary,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            RedirectStandardInput = false,
            UseShellExecute = false,
            CreateNoWindow = true,
            WorkingDirectory = this._workingDirectory ?? Directory.GetCurrentDirectory(),
        };

        foreach (var arg in this._shell.StatelessArgvForCommand(command))
        {
            startInfo.ArgumentList.Add(arg);
        }

        if (this._cleanEnvironment)
        {
            EnvironmentSanitizer.RemoveNonPreserved(startInfo.Environment);
        }

        if (this._environment is not null)
        {
            foreach (var kv in this._environment)
            {
                if (kv.Value is null)
                {
                    _ = startInfo.Environment.Remove(kv.Key);
                }
                else
                {
                    startInfo.Environment[kv.Key] = kv.Value;
                }
            }
        }

        // PowerShell defaults to non-UTF8 output redirection; force UTF-8 to avoid mojibake.
        if (this._shell.Kind == ShellKind.PowerShell)
        {
            startInfo.Environment["PSDefaultParameterValues"] = "Out-File:Encoding=utf8";
        }

        using var process = new Process { StartInfo = startInfo, EnableRaisingEvents = true };
        var stdoutBuf = new HeadTailBuffer(this._maxOutputBytes);
        var stderrBuf = new HeadTailBuffer(this._maxOutputBytes);

        process.OutputDataReceived += (_, e) =>
        {
            if (e.Data is null) { return; }
            stdoutBuf.AppendLine(e.Data);
        };
        process.ErrorDataReceived += (_, e) =>
        {
            if (e.Data is null) { return; }
            stderrBuf.AppendLine(e.Data);
        };

        var stopwatch = Stopwatch.StartNew();
        try
        {
            _ = process.Start();
        }
        catch (Win32Exception ex)
        {
            throw new IOException(
                $"Failed to launch shell '{this._shell.Binary}': {ex.Message}", ex);
        }

        process.BeginOutputReadLine();
        process.BeginErrorReadLine();

        var timedOut = false;
        using var timeoutCts = this._timeout is null
            ? new CancellationTokenSource()
            : new CancellationTokenSource(this._timeout.Value);
        using var linkedCts = CancellationTokenSource.CreateLinkedTokenSource(
            cancellationToken, timeoutCts.Token);

        try
        {
            await process.WaitForExitAsync(linkedCts.Token).ConfigureAwait(false);
        }
        catch (OperationCanceledException) when (timeoutCts.IsCancellationRequested && !cancellationToken.IsCancellationRequested)
        {
            timedOut = true;
        }
        catch (OperationCanceledException)
        {
            KillProcessTree(process);
            throw;
        }

        if (timedOut)
        {
            KillProcessTree(process);
            try
            {
                await process.WaitForExitAsync(CancellationToken.None).ConfigureAwait(false);
            }
            catch (Exception ex) when (ex is InvalidOperationException || ex is Win32Exception)
            {
                // Best-effort shutdown after timeout — process may already be reaped.
            }
        }

        stopwatch.Stop();

        // Drain the async readers — WaitForExit doesn't guarantee the
        // OutputDataReceived/ErrorDataReceived events have all fired.
        process.WaitForExit();

        var (stdout, soutTrunc) = stdoutBuf.ToFinalString();
        var (stderr, serrTrunc) = stderrBuf.ToFinalString();

        return new ShellResult(
            Stdout: stdout,
            Stderr: stderr,
            ExitCode: timedOut ? 124 : process.ExitCode,
            Duration: stopwatch.Elapsed,
            Truncated: soutTrunc || serrTrunc,
            TimedOut: timedOut);
    }

    /// <summary>
    /// Build an <see cref="AIFunction"/> bound to this tool, suitable for
    /// adding to <see cref="ChatOptions.Tools"/>.
    /// </summary>
    /// <param name="name">Function name surfaced to the model. Defaults to <c>run_shell</c>.</param>
    /// <param name="description">Function description for the model.</param>
    /// <param name="requireApproval">
    /// When <see langword="true"/> (the default) the returned function is wrapped in
    /// <see cref="ApprovalRequiredAIFunction"/>, so any agent built with
    /// <c>UseFunctionInvocation()</c> + <c>UseToolApproval()</c> will surface a
    /// <see cref="ToolApprovalRequestContent"/> that the harness can present to the user
    /// before the command runs. This is the security boundary for the local shell tool —
    /// disable only if you are intentionally running unattended (e.g. in a sandboxed
    /// container where the tool itself is the boundary).
    /// </param>
    /// <returns>An <see cref="AIFunction"/> wrapping <see cref="RunAsync"/>.</returns>
    public AIFunction AsAIFunction(string name = "run_shell", string? description = null, bool requireApproval = true)
    {
        if (!requireApproval && !this._acknowledgeUnsafe)
        {
            throw new InvalidOperationException(
                "Refusing to produce an AIFunction without approval gating. " +
                "Pass `acknowledgeUnsafe: true` to the LocalShellExecutor constructor to opt out, " +
                "or leave `requireApproval: true` (the default).");
        }

        description ??= this.BuildDefaultDescription();

        var fn = AIFunctionFactory.Create(
            async ([Description("The shell command to execute.")] string command,
                CancellationToken cancellationToken) =>
            {
                try
                {
                    var result = await this.RunAsync(command, cancellationToken).ConfigureAwait(false);
                    return result.FormatForModel();
                }
                catch (ShellCommandRejectedException ex)
                {
                    // ex.Message already starts with "Command rejected by policy: ...".
                    return ex.Message;
                }
            },
            new AIFunctionFactoryOptions
            {
                Name = name,
                Description = description,
            });

        return requireApproval ? new ApprovalRequiredAIFunction(fn) : fn;
    }

    /// <inheritdoc />
    public override async ValueTask DisposeAsync()
    {
        ShellSession? session;
        lock (this._sessionGate)
        {
            session = this._session;
            this._session = null;
        }
        if (session is not null)
        {
            await session.DisposeAsync().ConfigureAwait(false);
        }
    }

    private string BuildDefaultDescription()
    {
        var sb = new StringBuilder();
        _ = sb.Append("Execute a single shell command on the local machine and return its stdout, stderr, and exit code.");
        _ = sb.Append(' ');

        var os = System.Runtime.InteropServices.RuntimeInformation.IsOSPlatform(System.Runtime.InteropServices.OSPlatform.Windows) ? "Windows"
            : System.Runtime.InteropServices.RuntimeInformation.IsOSPlatform(System.Runtime.InteropServices.OSPlatform.OSX) ? "macOS"
            : System.Runtime.InteropServices.RuntimeInformation.IsOSPlatform(System.Runtime.InteropServices.OSPlatform.Linux) ? "Linux"
            : "POSIX";
        _ = sb.Append("Operating system: ").Append(os).Append(". ");

        var shellName = this._shell.Kind switch
        {
            ShellKind.PowerShell => "PowerShell (pwsh)",
            ShellKind.Cmd => "cmd.exe",
            ShellKind.Bash => "bash",
            ShellKind.Sh => "POSIX sh (dash/ash)",
            _ => "POSIX shell",
        };
        _ = sb.Append("Shell: ").Append(shellName).Append(" (binary: '").Append(this._shell.Binary).Append("'). ");

        if (this._shell.Kind == ShellKind.PowerShell)
        {
            _ = sb.Append(
                "Use PowerShell syntax — NOT bash/sh. Equivalents: ");
            _ = sb.Append("`cd $env:TEMP` (NOT `cd /tmp`); ");
            _ = sb.Append("`$env:VAR = 'x'` (NOT `VAR=x` or `export VAR=x`); ");
            _ = sb.Append("`$env:VAR` (NOT `$VAR`); ");
            _ = sb.Append("`Get-ChildItem` or `dir` (NOT `ls -la`); ");
            _ = sb.Append("`Get-Content` or `cat` (built-in alias works); ");
            _ = sb.Append("`Where-Object` / `Select-String` (NOT `grep`). ");
        }
        else if (this._shell.Kind is ShellKind.Bash or ShellKind.Sh)
        {
            _ = sb.Append("Use POSIX shell syntax. ");
            if (this._shell.Kind == ShellKind.Sh)
            {
                _ = sb.Append("This is a minimal POSIX sh (likely dash/ash) — avoid bash-only features like `[[ ... ]]`, arrays, `<<<` here-strings, or `set -o pipefail`. ");
            }
        }

        if (this._mode == ShellMode.Persistent)
        {
            _ = sb.Append(
                "PERSISTENT MODE: a single long-lived shell handles every call. " +
                "`cd`, exported / `$env:` variables, and function definitions DO persist across calls. " +
                "Use this to your advantage: change directory once, then run subsequent commands without re-cd'ing.");
        }
        else
        {
            _ = sb.Append(
                "STATELESS MODE: each call runs in a fresh shell. " +
                "Working directory and environment variables DO NOT carry across calls — combine related steps into one command if state matters.");
        }

        _ = sb.Append(' ');
        if (this._timeout is { } t)
        {
            _ = sb.Append("Per-call timeout: ").Append((int)t.TotalSeconds).Append("s. ");
        }
        _ = sb.Append("Output is truncated to ").Append(this._maxOutputBytes).Append(" bytes (head + tail). ");
        _ = sb.Append("The user reviews and approves every call.");

        return sb.ToString();
    }

    private static void KillProcessTree(Process process)
    {
        try
        {
#if NET5_0_OR_GREATER
            process.Kill(entireProcessTree: true);
#else
            process.Kill();
#endif
        }
        catch (InvalidOperationException)
        {
            // Process already exited.
        }
        catch (Win32Exception)
        {
            // Best-effort tree-kill — child has likely already exited.
        }
    }
}

/// <summary>
/// Thrown when <see cref="LocalShellExecutor"/> rejects a command via its policy.
/// </summary>
public sealed class ShellCommandRejectedException : Exception
{
    /// <summary>Initializes a new instance of the <see cref="ShellCommandRejectedException"/> class.</summary>
    /// <param name="message">The exception message.</param>
    public ShellCommandRejectedException(string message) : base(message)
    {
    }

    /// <summary>Initializes a new instance of the <see cref="ShellCommandRejectedException"/> class.</summary>
    /// <param name="message">The exception message.</param>
    /// <param name="inner">The inner exception.</param>
    public ShellCommandRejectedException(string message, Exception inner) : base(message, inner)
    {
    }

    /// <summary>Initializes a new instance of the <see cref="ShellCommandRejectedException"/> class.</summary>
    public ShellCommandRejectedException()
    {
    }
}
