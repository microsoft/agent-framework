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
/// <c>LocalShellTool</c> launches a real shell (bash/sh on POSIX, pwsh/powershell/cmd on Windows)
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
/// <b>Threat model.</b> The deny list is a guardrail, not a security boundary. Real isolation
/// requires either (a) approval-in-the-loop, where every command is reviewed by a human via the
/// harness <c>ToolApprovalAgent</c> (this is the default; see
/// <see cref="AsAIFunction(string, string?, bool)"/>), or (b) container isolation
/// (<c>DockerShellTool</c>). To produce an unapproved <see cref="AIFunction"/> you must pass
/// <c>acknowledgeUnsafe: true</c> at construction; otherwise <see cref="AsAIFunction"/> will
/// refuse to return a non-approval-gated function.
/// </para>
/// </remarks>
public sealed class LocalShellTool : IAsyncDisposable, IShellExecutor
{
    private const int DefaultMaxOutputBytes = 64 * 1024;

    /// <summary>
    /// Recommended default per-command timeout (30 seconds). Pass this
    /// explicitly to the constructor to opt in to a bounded timeout. Note
    /// that <see langword="null"/> (the parameter default) means
    /// <em>no timeout</em>, matching the documented contract.
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
    /// Initializes a new instance of the <see cref="LocalShellTool"/> class.
    /// </summary>
    /// <param name="mode">Execution mode. Defaults to <see cref="ShellMode.Persistent"/> so
    /// <c>cd</c>, exported variables, and function definitions persist across calls. Use
    /// <see cref="ShellMode.Stateless"/> if you specifically need every call to start fresh.</param>
    /// <param name="shell">Override path to the shell binary. Falls back to the <c>AGENT_FRAMEWORK_SHELL</c> environment variable, then OS defaults. Mutually exclusive with <paramref name="shellArgv"/>.</param>
    /// <param name="shellArgv">Override argv for the shell launch. The first element is the binary; subsequent elements are passed as a launch-time prefix (e.g. <c>["/bin/bash", "--rcfile", "/path/to/rc"]</c>). Mutually exclusive with <paramref name="shell"/>.</param>
    /// <param name="workingDirectory">Working directory for the spawned shell. Defaults to the current process directory. Required when <paramref name="confineWorkingDirectory"/> is <see langword="true"/>.</param>
    /// <param name="confineWorkingDirectory">When <see langword="true"/> (the default) and a <paramref name="workingDirectory"/> is set, every command in persistent mode is prefixed with a <c>cd</c> back into that directory so a wandering <c>cd</c> in one call doesn't leak to the next. This is a re-anchor, not a hard confinement — a command that does <c>cd /tmp; rm -rf .</c> can still touch <c>/tmp</c>. Use a sandboxed executor for true isolation.</param>
    /// <param name="environment">Extra environment variables. Pass a <see langword="null"/> value to remove an inherited variable.</param>
    /// <param name="cleanEnvironment">When <see langword="true"/>, the spawned shell does not inherit the parent process environment; only PATH/HOME/USER/USERNAME/USERPROFILE/SystemRoot/TEMP/TMP plus anything in <paramref name="environment"/> are visible.</param>
    /// <param name="policy">Optional <see cref="ShellPolicy"/>. Defaults to a policy seeded with <see cref="ShellPolicy.DefaultDenyList"/>.</param>
    /// <param name="timeout">Per-command timeout. <see langword="null"/> disables timeouts.</param>
    /// <param name="maxOutputBytes">Per-stream cap before head+tail truncation.</param>
    /// <param name="acknowledgeUnsafe">
    /// Set to <see langword="true"/> to allow <see cref="AsAIFunction"/> to produce an
    /// AIFunction without an <c>ApprovalRequiredAIFunction</c> wrapper. Required if you pass
    /// <c>requireApproval: false</c> to <see cref="AsAIFunction"/>. The default is
    /// <see langword="false"/>, which makes accidentally bypassing approval impossible.
    /// </param>
    public LocalShellTool(
        ShellMode mode = ShellMode.Persistent,
        string? shell = null,
        IReadOnlyList<string>? shellArgv = null,
        string? workingDirectory = null,
        bool confineWorkingDirectory = true,
        IReadOnlyDictionary<string, string?>? environment = null,
        bool cleanEnvironment = false,
        ShellPolicy? policy = null,
        TimeSpan? timeout = null,
        int maxOutputBytes = DefaultMaxOutputBytes,
        bool acknowledgeUnsafe = false)
    {
        if (maxOutputBytes <= 0)
        {
            throw new ArgumentOutOfRangeException(nameof(maxOutputBytes));
        }
        if (shell is not null && shellArgv is not null)
        {
            throw new ArgumentException("Pass either shell or shellArgv, not both.", nameof(shellArgv));
        }

        this._mode = mode;
        this._policy = policy ?? new ShellPolicy();
        this._shell = shellArgv is not null ? ShellResolver.ResolveArgv(shellArgv) : ShellResolver.Resolve(shell);
        this._timeout = timeout;
        this._maxOutputBytes = maxOutputBytes;
        this._workingDirectory = workingDirectory;
        this._confineWorkingDirectory = confineWorkingDirectory;
        this._environment = environment;
        this._cleanEnvironment = cleanEnvironment;
        this._acknowledgeUnsafe = acknowledgeUnsafe;

        if (mode == ShellMode.Persistent && this._shell.Kind == ShellKind.Cmd)
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
    public async Task<ShellResult> RunAsync(string command, CancellationToken cancellationToken = default)
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
    Task IShellExecutor.StartAsync(CancellationToken cancellationToken)
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

    /// <inheritdoc />
    Task IShellExecutor.CloseAsync(CancellationToken cancellationToken) => this.DisposeAsync().AsTask();

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
            var preserved = new[] { "PATH", "HOME", "USER", "USERNAME", "USERPROFILE", "SystemRoot", "TEMP", "TMP" };
            var keep = new Dictionary<string, string?>(StringComparer.OrdinalIgnoreCase);
            foreach (var name in preserved)
            {
                if (startInfo.Environment.TryGetValue(name, out var v) && v is not null)
                {
                    keep[name] = v;
                }
            }
            startInfo.Environment.Clear();
            foreach (var kv in keep)
            {
                startInfo.Environment[kv.Key] = kv.Value;
            }
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
            throw new ShellExecutionException(
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
                "Pass `acknowledgeUnsafe: true` to the LocalShellTool constructor to opt out, " +
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
    public async ValueTask DisposeAsync()
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

    /// <summary>
    /// Bounded accumulator that keeps the first <c>cap/2</c> chars of input and the
    /// most recent <c>cap/2</c> chars (rolling tail). When the input fits in <c>cap</c>,
    /// the result is the original concatenation. Otherwise the middle is dropped and
    /// the result includes a "[... truncated N chars ...]" marker.
    /// </summary>
    private sealed class HeadTailBuffer
    {
        private readonly int _cap;
        private readonly int _halfCap;
        private readonly StringBuilder _head = new();
        private readonly Queue<char> _tail = new();
        private long _totalChars;

        public HeadTailBuffer(int cap)
        {
            this._cap = cap;
            this._halfCap = cap / 2;
        }

        public void AppendLine(string line)
        {
            this.AppendInternal(line);
            this.AppendInternal("\n");
        }

        private void AppendInternal(string s)
        {
            for (var i = 0; i < s.Length; i++)
            {
                this._totalChars++;
                if (this._head.Length < this._halfCap)
                {
                    _ = this._head.Append(s[i]);
                }
                else
                {
                    this._tail.Enqueue(s[i]);
                    if (this._tail.Count > this._halfCap)
                    {
                        _ = this._tail.Dequeue();
                    }
                }
            }
        }

        public (string text, bool truncated) ToFinalString()
        {
            if (this._totalChars <= this._cap)
            {
                var combined = new StringBuilder(this._head.Length + this._tail.Count);
                _ = combined.Append(this._head);
                foreach (var c in this._tail)
                {
                    _ = combined.Append(c);
                }
                return (combined.ToString(), false);
            }

            var dropped = this._totalChars - this._head.Length - this._tail.Count;
            var sb = new StringBuilder();
            _ = sb.Append(this._head);
            _ = sb.Append('\n');
            _ = sb.Append("[... truncated ").Append(dropped).Append(" chars ...]");
            _ = sb.Append('\n');
            foreach (var c in this._tail)
            {
                _ = sb.Append(c);
            }
            return (sb.ToString(), true);
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
/// Thrown when <see cref="LocalShellTool"/> rejects a command via its policy.
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
