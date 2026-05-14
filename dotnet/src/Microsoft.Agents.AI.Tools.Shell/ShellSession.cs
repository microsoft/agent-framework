// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Globalization;
using System.IO;
using System.Runtime.InteropServices;
using System.Text;
using System.Threading;
using System.Threading.Tasks;

namespace Microsoft.Agents.AI.Tools.Shell;

/// <summary>
/// A long-lived shell subprocess that executes commands one at a time using a
/// <b>sentinel protocol</b> to mark command boundaries. State (current
/// directory, exported variables, function definitions, etc.) is preserved
/// across calls.
/// </summary>
/// <remarks>
/// <para>
/// <b>Single-owner contract.</b> A <see cref="ShellSession"/> is owned by exactly one
/// conversation / agent session — i.e., one user. The backing shell process carries
/// mutable state (cwd, exported variables, history, background jobs) that every
/// subsequent command can observe, and <c>_runLock</c> serializes every call onto the
/// single stdin/stdout pipe. There is no per-caller isolation. The enclosing executor
/// must not share a single session across users, tenants, or concurrent conversations;
/// it must create one session per agent session and dispose it when the session ends.
/// </para>
/// <para>
/// Cross-OS implementation notes:
/// </para>
/// <list type="bullet">
/// <item>
/// PowerShell hosted with <c>-Command -</c> waits for a complete parse before
/// executing. Multi-line <c>try { ... }</c> blocks therefore stall with stdin
/// open, so the user command is base64-encoded and invoked with
/// <c>Invoke-Expression</c> on a single line.
/// </item>
/// <item>
/// <c>Write-Output</c> may drop trailing newlines when stdout is redirected.
/// The sentinel is therefore emitted via <c>[Console]::WriteLine</c> +
/// <c>[Console]::Out.Flush()</c>.
/// </item>
/// <item>
/// <c>$LASTEXITCODE</c> only tracks external-process exits, so the rc is
/// derived from <c>$?</c> and caught exceptions as well.
/// </item>
/// <item>
/// stdout/stderr are drained by long-running reader tasks; per-call buffer
/// offsets are snapshotted before the command is written and scanned forward,
/// which avoids late stderr being attributed to the next command.
/// </item>
/// </list>
/// </remarks>
internal sealed class ShellSession : IAsyncDisposable
{
    private const int ReadChunk = 64 * 1024;
    private static readonly TimeSpan s_shutdownGrace = TimeSpan.FromSeconds(2);
    // Brief quiescence to let late stderr drain after the sentinel is seen.
    private static readonly TimeSpan s_stderrQuiescence = TimeSpan.FromMilliseconds(50);
    // Time window to wait for the sentinel after we've sent SIGINT / Ctrl+C
    // to the shell. If the sentinel still doesn't land we fall back to a
    // hard close-and-respawn.
    private static readonly TimeSpan s_interruptGrace = TimeSpan.FromMilliseconds(500);

    private readonly ResolvedShell _shell;
    private readonly string? _workingDirectory;
    private readonly bool _confineWorkingDirectory;
    private readonly IReadOnlyDictionary<string, string?>? _environment;
    private readonly bool _cleanEnvironment;
    private readonly int _maxOutputBytes;
    // Serializes commands onto the single stdin/stdout pipe. This is an
    // ordering primitive within one owning session; it is NOT a multi-tenant
    // isolation mechanism. ShellSession is single-owner — see the type-level
    // remarks. The lock just guarantees that concurrent calls from the one
    // owner queue cleanly instead of interleaving on the pipe.
    private readonly SemaphoreSlim _runLock = new(1, 1);
    private readonly SemaphoreSlim _lifecycleLock = new(1, 1);
    private readonly string _sentinelTag;

    private Process? _proc;
    private bool _isSessionLeader;
    private Task? _stdoutReader;
    private Task? _stderrReader;
    private readonly List<byte> _stdoutBuf = new(capacity: 4096);
    private readonly List<byte> _stderrBuf = new(capacity: 1024);
    private readonly object _bufferGate = new();
    private TaskCompletionSource<bool> _stdoutSignal = NewSignal();
    private bool _stdoutClosed;

    public ShellSession(
        ResolvedShell shell,
        string? workingDirectory,
        bool confineWorkingDirectory,
        IReadOnlyDictionary<string, string?>? environment,
        bool cleanEnvironment,
        int maxOutputBytes)
    {
        this._shell = shell;
        this._workingDirectory = workingDirectory;
        this._confineWorkingDirectory = confineWorkingDirectory;
        this._environment = environment;
        this._cleanEnvironment = cleanEnvironment;
        this._maxOutputBytes = maxOutputBytes;
        // Cryptographically-random tag prevents a rogue command from echoing
        // a matching earlier sentinel.
        var bytes = new byte[8];
#if NET6_0_OR_GREATER
        System.Security.Cryptography.RandomNumberGenerator.Fill(bytes);
#else
        using (var rng = System.Security.Cryptography.RandomNumberGenerator.Create())
        {
            rng.GetBytes(bytes);
        }
#endif
#pragma warning disable CA1308 // sentinel tag is matched against shell-emitted lowercase hex; not for security or display
        this._sentinelTag = Convert.ToHexString(bytes).ToLowerInvariant();
#pragma warning restore CA1308
    }

    public async ValueTask DisposeAsync()
    {
        await this.CloseAsync().ConfigureAwait(false);
        this._runLock.Dispose();
        this._lifecycleLock.Dispose();
    }

    private async Task EnsureStartedAsync()
    {
        await this._lifecycleLock.WaitAsync().ConfigureAwait(false);
        try
        {
#pragma warning disable RCS1146 // HasExited can throw on disposed proc; null check intentional
            if (this._proc is not null && !this._proc.HasExited)
#pragma warning restore RCS1146
            {
                return;
            }

            var startInfo = new ProcessStartInfo
            {
                FileName = this._shell.Binary,
                RedirectStandardInput = true,
                RedirectStandardOutput = true,
                RedirectStandardError = true,
                UseShellExecute = false,
                CreateNoWindow = true,
                WorkingDirectory = this._workingDirectory ?? Directory.GetCurrentDirectory(),
            };

            foreach (var arg in this._shell.PersistentArgv())
            {
                startInfo.ArgumentList.Add(arg);
            }

            // On POSIX, wrap the shell in `setsid` so the spawned process
            // becomes a session leader (PID == PGID). This is what makes
            // `killpg(proc.Id, SIGINT)` in InterruptCurrentCommandAsync
            // correctly target the shell + its in-flight command instead
            // of inheriting the agent host's process group. If setsid is
            // not available we fall back to a direct launch and the
            // interrupt path becomes a best-effort no-op (the caller's
            // hard close-and-respawn handles the timeout case).
            this._isSessionLeader = false;
            if (!RuntimeInformation.IsOSPlatform(OSPlatform.Windows)
                && TryFindSetsid(out var setsidPath))
            {
                var originalArgs = new List<string>(startInfo.ArgumentList);
                startInfo.FileName = setsidPath;
                startInfo.ArgumentList.Clear();
                startInfo.ArgumentList.Add(this._shell.Binary);
                foreach (var arg in originalArgs)
                {
                    startInfo.ArgumentList.Add(arg);
                }
                this._isSessionLeader = true;
            }

            if (this._cleanEnvironment)
            {
                // Strip everything inherited except the allowlist in
                // EnvironmentSanitizer.PreservedVariables, so the shell can
                // still locate itself and basic tools.
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

            this._stdoutBuf.Clear();
            this._stderrBuf.Clear();
            this._stdoutSignal = NewSignal();
            this._stdoutClosed = false;

            var proc = new Process { StartInfo = startInfo, EnableRaisingEvents = true };
            _ = proc.Start();
            this._proc = proc;

            this._stdoutReader = Task.Run(() => this.ReadLoopAsync(proc.StandardOutput.BaseStream, this._stdoutBuf, isStdout: true));
            this._stderrReader = Task.Run(() => this.ReadLoopAsync(proc.StandardError.BaseStream, this._stderrBuf, isStdout: false));

            // Best-effort: make PowerShell emit UTF-8 so the sentinel is byte-clean.
            if (this._shell.Kind == ShellKind.PowerShell)
            {
                await this.WriteRawAsync(
                    "$OutputEncoding = [Console]::OutputEncoding = " +
                    "[System.Text.UTF8Encoding]::new($false);" +
                    "$ErrorActionPreference = 'Stop'\n").ConfigureAwait(false);
            }
        }
        finally
        {
            _ = this._lifecycleLock.Release();
        }
    }

    public async Task CloseAsync()
    {
        await this._lifecycleLock.WaitAsync().ConfigureAwait(false);
        try
        {
            var proc = this._proc;
            this._proc = null;
#pragma warning disable RCS1146
            if (proc is null || proc.HasExited)
#pragma warning restore RCS1146
            {
                await this.CancelReadersAsync().ConfigureAwait(false);
                proc?.Dispose();
                return;
            }

            try
            {
                try
                {
                    await proc.StandardInput.WriteLineAsync("exit").ConfigureAwait(false);
                    await proc.StandardInput.FlushAsync().ConfigureAwait(false);
                    proc.StandardInput.Close();
                }
                catch (IOException) { /* pipe may already be closed */ }
                catch (ObjectDisposedException) { }

                using var cts = new CancellationTokenSource(s_shutdownGrace);
                try
                {
                    await proc.WaitForExitAsync(cts.Token).ConfigureAwait(false);
                }
                catch (OperationCanceledException)
                {
                    KillProcessTree(proc);
                }
            }
            finally
            {
                await this.CancelReadersAsync().ConfigureAwait(false);
                proc.Dispose();
            }
        }
        finally
        {
            _ = this._lifecycleLock.Release();
        }
    }

    private async Task CancelReadersAsync()
    {
        // Reader loops exit when their stream closes; just wait for them.
        if (this._stdoutReader is not null)
        {
            try { await this._stdoutReader.ConfigureAwait(false); }
            catch { /* best-effort */ }
        }
        if (this._stderrReader is not null)
        {
            try { await this._stderrReader.ConfigureAwait(false); }
            catch { /* best-effort */ }
        }
        this._stdoutReader = null;
        this._stderrReader = null;
    }

    /// <summary>Run a single command in the live session and return the result.</summary>
    public async Task<ShellResult> RunAsync(string command, TimeSpan? timeout, CancellationToken cancellationToken)
    {
        await this.EnsureStartedAsync().ConfigureAwait(false);
        await this._runLock.WaitAsync(cancellationToken).ConfigureAwait(false);
        try
        {
            return await this.RunLockedAsync(command, timeout, cancellationToken).ConfigureAwait(false);
        }
        finally
        {
            _ = this._runLock.Release();
        }
    }

    private async Task<ShellResult> RunLockedAsync(string command, TimeSpan? timeout, CancellationToken cancellationToken)
    {
        var proc = this._proc ?? throw new InvalidOperationException("Session not started.");

        // Per-command random suffix on top of the session tag.
        var suffix = new byte[4];
#if NET6_0_OR_GREATER
        System.Security.Cryptography.RandomNumberGenerator.Fill(suffix);
#else
        using (var rng = System.Security.Cryptography.RandomNumberGenerator.Create())
        {
            rng.GetBytes(suffix);
        }
#endif
#pragma warning disable CA1308
        var sentinel = $"__AF_END_{this._sentinelTag}_{Convert.ToHexString(suffix).ToLowerInvariant()}__";
#pragma warning restore CA1308
        var script = this.BuildScript(command, sentinel);

        int stdoutOffset, stderrOffset;
        lock (this._bufferGate)
        {
            stdoutOffset = this._stdoutBuf.Count;
            stderrOffset = this._stderrBuf.Count;
            // Reset stdout signal so the wait loop blocks on fresh data.
            this._stdoutSignal = NewSignal();
        }

        var stopwatch = Stopwatch.StartNew();
        try
        {
            await proc.StandardInput.WriteAsync(script.AsMemory(), cancellationToken).ConfigureAwait(false);
            await proc.StandardInput.FlushAsync(cancellationToken).ConfigureAwait(false);
        }
        catch (IOException ex)
        {
            throw new IOException("Persistent shell session is no longer alive.", ex);
        }

        var needle = Encoding.UTF8.GetBytes(sentinel);
        var hardCap = this._maxOutputBytes * 4;
        var (sentinelIdx, exitCode, timedOut, overflow) = await this.WaitForSentinelAsync(
            needle, stdoutOffset, hardCap, timeout, cancellationToken).ConfigureAwait(false);

        if (timedOut)
        {
            // Graceful path: interrupt the current command (SIGINT / Ctrl+C)
            // and give the shell a moment to print its own sentinel. If that
            // works the session survives — `cd` and exported variables from
            // earlier calls are preserved across the timeout.
            await this.InterruptCurrentCommandAsync().ConfigureAwait(false);
            using var graceCts = new CancellationTokenSource(s_interruptGrace);
            try
            {
                using var graceLink = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken, graceCts.Token);
                var (postIdx, _, postTimedOut, postOverflow) = await this.WaitForSentinelAsync(
                    needle, stdoutOffset, hardCap, s_interruptGrace, graceLink.Token).ConfigureAwait(false);
                if (!postTimedOut && !postOverflow && postIdx >= 0)
                {
                    sentinelIdx = postIdx;
                    // Treat a successfully-interrupted command as a timeout
                    // for the result envelope but keep the session alive.
                    await Task.Delay(s_stderrQuiescence, cancellationToken).ConfigureAwait(false);
                    stopwatch.Stop();
                    byte[] stdoutRawI;
                    byte[] stderrRawI;
                    lock (this._bufferGate)
                    {
                        stdoutRawI = SnapshotRange(this._stdoutBuf, stdoutOffset, sentinelIdx - stdoutOffset);
                        stderrRawI = SnapshotRange(this._stderrBuf, stderrOffset, this._stderrBuf.Count - stderrOffset);
                    }
                    var stdoutI = Encoding.UTF8.GetString(stdoutRawI).TrimEnd('\r', '\n');
                    var stderrI = Encoding.UTF8.GetString(stderrRawI);
                    var (soutI, soTI) = TruncateHeadTail(stdoutI, this._maxOutputBytes);
                    var (serrI, seTI) = TruncateHeadTail(stderrI, this._maxOutputBytes);
                    return new ShellResult(
                        Stdout: soutI,
                        Stderr: serrI,
                        ExitCode: 124,
                        Duration: stopwatch.Elapsed,
                        Truncated: soTI || seTI,
                        TimedOut: true);
                }
            }
            catch (OperationCanceledException) { /* fall through to hard close */ }
        }

        if (timedOut || overflow)
        {
            // Best-effort recovery: tear the session down. Next call respawns.
            await this.CloseAsync().ConfigureAwait(false);
            stopwatch.Stop();
            byte[] stdoutBytes;
            byte[] stderrBytes;
            lock (this._bufferGate)
            {
                stdoutBytes = SnapshotRange(this._stdoutBuf, stdoutOffset, this._stdoutBuf.Count - stdoutOffset);
                stderrBytes = SnapshotRange(this._stderrBuf, stderrOffset, this._stderrBuf.Count - stderrOffset);
            }
            var (so, soT) = TruncateHeadTail(Encoding.UTF8.GetString(stdoutBytes), this._maxOutputBytes);
            var (se, seT) = TruncateHeadTail(Encoding.UTF8.GetString(stderrBytes), this._maxOutputBytes);
            return new ShellResult(
                Stdout: so,
                Stderr: se,
                ExitCode: timedOut ? 124 : -1,
                Duration: stopwatch.Elapsed,
                Truncated: soT || seT,
                TimedOut: timedOut);
        }

        // Let stderr quiesce briefly — late writes from the completing command
        // otherwise leak into the next run().
        await Task.Delay(s_stderrQuiescence, cancellationToken).ConfigureAwait(false);

        stopwatch.Stop();
        byte[] stdoutRaw;
        byte[] stderrRaw;
        lock (this._bufferGate)
        {
            stdoutRaw = SnapshotRange(this._stdoutBuf, stdoutOffset, sentinelIdx - stdoutOffset);
            stderrRaw = SnapshotRange(this._stderrBuf, stderrOffset, this._stderrBuf.Count - stderrOffset);
        }

        var stdout = Encoding.UTF8.GetString(stdoutRaw).TrimEnd('\r', '\n');
        var stderr = Encoding.UTF8.GetString(stderrRaw);
        var (sout, soutTrunc) = TruncateHeadTail(stdout, this._maxOutputBytes);
        var (serr, serrTrunc) = TruncateHeadTail(stderr, this._maxOutputBytes);

        return new ShellResult(
            Stdout: sout,
            Stderr: serr,
            ExitCode: exitCode,
            Duration: stopwatch.Elapsed,
            Truncated: soutTrunc || serrTrunc,
            TimedOut: false);
    }

    private async Task<(int sentinelIdx, int exitCode, bool timedOut, bool overflow)> WaitForSentinelAsync(
        byte[] needle, int searchFrom, int hardCap, TimeSpan? timeout, CancellationToken cancellationToken)
    {
        using var timeoutCts = timeout is null
            ? new CancellationTokenSource()
            : new CancellationTokenSource(timeout.Value);
        using var linkedCts = CancellationTokenSource.CreateLinkedTokenSource(
            cancellationToken, timeoutCts.Token);

        while (true)
        {
            int idx;
            int bufLen;
            bool closed;
            TaskCompletionSource<bool> signal;
            lock (this._bufferGate)
            {
                bufLen = this._stdoutBuf.Count;
                closed = this._stdoutClosed;
                signal = this._stdoutSignal;
                idx = IndexOf(this._stdoutBuf, needle, searchFrom);
            }

            if (idx >= 0)
            {
                var rc = await this.ReadExitCodeAsync(idx + needle.Length, linkedCts.Token).ConfigureAwait(false);
                return (idx, rc, false, false);
            }
            if (bufLen - searchFrom > hardCap)
            {
                return (-1, -1, false, true);
            }
            if (closed)
            {
                return (-1, -1, false, true);
            }

            try
            {
                await signal.Task.WaitAsync(TimeSpan.FromMilliseconds(100), linkedCts.Token).ConfigureAwait(false);
            }
            catch (TimeoutException)
            {
                // Spin and re-check.
            }
            catch (OperationCanceledException) when (timeoutCts.IsCancellationRequested && !cancellationToken.IsCancellationRequested)
            {
                return (-1, -1, true, false);
            }
        }
    }

    private async Task<int> ReadExitCodeAsync(int afterIdx, CancellationToken cancellationToken)
    {
        // The trailer is "_<digits>\n". Wait briefly for the newline to land.
        var deadline = DateTime.UtcNow + TimeSpan.FromSeconds(1);
        while (DateTime.UtcNow < deadline)
        {
            int len;
            byte[] tail;
            TaskCompletionSource<bool> signal;
            lock (this._bufferGate)
            {
                len = this._stdoutBuf.Count - afterIdx;
                tail = len > 0 ? SnapshotRange(this._stdoutBuf, afterIdx, len) : Array.Empty<byte>();
                signal = this._stdoutSignal = NewSignal();
            }

            var nl = Array.IndexOf(tail, (byte)'\n');
            if (nl >= 0)
            {
                return ParseRc(tail, nl);
            }

            try
            {
                await signal.Task.WaitAsync(TimeSpan.FromMilliseconds(100), cancellationToken).ConfigureAwait(false);
            }
            catch (TimeoutException) { }
        }
        return -1;
    }

    private static int ParseRc(byte[] tail, int newlineIdx)
    {
        if (newlineIdx == 0 || tail[0] != (byte)'_')
        {
            return -1;
        }
        var digits = new StringBuilder();
        for (var i = 1; i < newlineIdx; i++)
        {
            var b = tail[i];
            if (b == '\r')
            {
                break;
            }
            if ((b >= '0' && b <= '9') || b == '-')
            {
                _ = digits.Append((char)b);
            }
            else
            {
                return -1;
            }
        }
        return int.TryParse(digits.ToString(), NumberStyles.Integer, CultureInfo.InvariantCulture, out var rc)
            ? rc
            : -1;
    }

    private string BuildScript(string command, string sentinel)
    {
        // Idempotent re-anchor: in confined mode every command is prefixed
        // with a `cd` back to the configured workdir so a `cd` inside one
        // command doesn't leak to the next.
        var effective = this.MaybeReanchor(command);

        if (this._shell.Kind == ShellKind.PowerShell)
        {
            // Base64-encode the command so multi-line constructs don't stall
            // the pwsh parser. Sentinel is emitted via [Console]::WriteLine
            // so the pipeline formatter can't drop the newline.
            var encoded = Convert.ToBase64String(Encoding.UTF8.GetBytes(effective));
            return
                "& {" +
                " $__af_rc = 0;" +
                " try {" +
                $"   $__af_cmd = [System.Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('{encoded}'));" +
                // Force the user command's success output through the same
                // [Console]::Out pipe as the sentinel, *inside the try* so
                // every byte of output is flushed before the finally fires.
                // Without this, pwsh defers Out-Default formatting until the
                // script block returns and the sentinel races ahead of the
                // user's output in the byte stream.
                "   Invoke-Expression $__af_cmd 2>&1 | ForEach-Object {" +
                "     if ($_ -is [System.Management.Automation.ErrorRecord]) {" +
                "       [Console]::Error.WriteLine(($_ | Out-String).TrimEnd());" +
                "     } else {" +
                "       [Console]::WriteLine(($_ | Out-String).TrimEnd());" +
                "     }" +
                "   };" +
                "   [Console]::Out.Flush();" +
                "   if ($LASTEXITCODE -ne $null) { $__af_rc = $LASTEXITCODE }" +
                "   elseif (-not $?) { $__af_rc = 1 }" +
                " } catch {" +
                "   [Console]::Error.WriteLine($_.ToString());" +
                "   $__af_rc = 1" +
                " } finally {" +
                $"   [Console]::WriteLine('{sentinel}_' + $__af_rc);" +
                "   [Console]::Out.Flush()" +
                " }" +
                " }\n";
        }

        // POSIX shell. Run the user command in a brace group so we capture
        // its exit status, then print the sentinel on a line of its own.
        // ``set +e`` around the trailer prevents a prior ``set -e`` from
        // skipping the sentinel print.
        return "{ " + effective + "\n" +
               "}; __af_rc=$?; set +e; " +
               $"printf '\\n{sentinel}_%s\\n' \"$__af_rc\"\n";
    }

    private string MaybeReanchor(string command)
    {
        if (!this._confineWorkingDirectory || string.IsNullOrEmpty(this._workingDirectory))
        {
            return command;
        }
        return this._shell.Kind == ShellKind.PowerShell
            ? $"Set-Location -LiteralPath {QuotePowerShell(this._workingDirectory!)}\n{command}"
            : $"cd -- {QuotePosix(this._workingDirectory!)}\n{command}";
    }

    /// <summary>
    /// Wrap <paramref name="value"/> in a PowerShell single-quoted string literal,
    /// escaping embedded single quotes by doubling. Single-quoted PowerShell
    /// strings perform no expansion, so this is safe against <c>$(...)</c>,
    /// <c>$var</c>, and backtick interpolation.
    /// </summary>
    internal static string QuotePowerShell(string value) =>
        "'" + value.Replace("'", "''", StringComparison.Ordinal) + "'";

    /// <summary>
    /// Wrap <paramref name="value"/> in POSIX single quotes, terminating and
    /// re-opening the literal around any embedded single quote
    /// (<c>'\u0027\\\u0027'</c>). POSIX single-quoted strings perform no
    /// expansion, so this is safe against <c>$VAR</c>, <c>$(...)</c>, and
    /// backtick interpolation.
    /// </summary>
    internal static string QuotePosix(string value) =>
        "'" + value.Replace("'", "'\\''", StringComparison.Ordinal) + "'";

    /// <summary>
    /// Send SIGINT (POSIX) or Ctrl+Break (Windows) to the live shell so the
    /// currently-running command is cancelled but the shell itself survives.
    /// Used to honor a per-command timeout without losing session state.
    /// </summary>
    internal async Task InterruptCurrentCommandAsync()
    {
        var proc = this._proc;
#pragma warning disable RCS1146
        if (proc is null || proc.HasExited)
#pragma warning restore RCS1146
        {
            return;
        }
        try
        {
            if (RuntimeInformation.IsOSPlatform(OSPlatform.Windows))
            {
                // pwsh hosted in -NoInteractive mode doesn't have a console
                // group attached to it, so GenerateConsoleCtrlEvent typically
                // can't reach it. Best we can do without ripping the session
                // is to write Ctrl+C to stdin, which the pwsh REPL picks up
                // for the in-flight pipeline. If that doesn't work the caller
                // falls back to a hard close-and-respawn.
                try
                {
                    await proc.StandardInput.WriteAsync("\u0003").ConfigureAwait(false);
                    await proc.StandardInput.FlushAsync().ConfigureAwait(false);
                }
                catch (IOException) { }
                catch (ObjectDisposedException) { }
            }
            else
            {
                // Send SIGINT to the process group so the shell + any direct
                // child receive it. p/invoke killpg via libc. We only do
                // this when EnsureStartedAsync succeeded in wrapping the
                // shell in `setsid` — otherwise `proc.Id` is NOT a process
                // group id (the child inherited the agent's PGID) and
                // calling killpg on it would signal the agent.
                if (!this._isSessionLeader)
                {
                    return;
                }
                _ = NativeMethods.killpg(proc.Id, NativeMethods.SIGINT);
            }
        }
        catch (Exception ex) when (ex is InvalidOperationException || ex is System.ComponentModel.Win32Exception)
        {
            // Best-effort interrupt — fall through to caller's hard-close path.
        }
        await Task.CompletedTask.ConfigureAwait(false);
    }

    private static bool TryFindSetsid(out string fullPath)
    {
        // Check well-known locations first to avoid PATH-based lookups when possible.
        foreach (var c in new[] { "/usr/bin/setsid", "/bin/setsid", "/usr/local/bin/setsid" })
        {
            if (File.Exists(c))
            {
                fullPath = c;
                return true;
            }
        }
        // Fall back to PATH.
        var pathEnv = Environment.GetEnvironmentVariable("PATH");
        if (!string.IsNullOrEmpty(pathEnv))
        {
            foreach (var dir in pathEnv!.Split(Path.PathSeparator))
            {
                if (string.IsNullOrEmpty(dir))
                {
                    continue;
                }
                var candidate = Path.Combine(dir, "setsid");
                if (File.Exists(candidate))
                {
                    fullPath = candidate;
                    return true;
                }
            }
        }
        fullPath = string.Empty;
        return false;
    }

    private static class NativeMethods
    {
        internal const int SIGINT = 2;

        // killpg lives in libc on Linux/macOS. The previous annotation used
        // DllImportSearchPath.System32 — that's a Windows-only loader hint and
        // does nothing for libc.so on POSIX. SafeDirectories satisfies
        // CA5392/CA5393 without falling back to the unsafe AssemblyDirectory
        // probe path. The call site is also gated to non-Windows, so the
        // import is never resolved on Windows.
        [DllImport("libc", SetLastError = true)]
        [DefaultDllImportSearchPaths(DllImportSearchPath.SafeDirectories)]
        internal static extern int killpg(int pgrp, int sig);
    }

    private async Task WriteRawAsync(string text)
    {
        if (this._proc is null)
        {
            return;
        }
        await this._proc.StandardInput.WriteAsync(text).ConfigureAwait(false);
        await this._proc.StandardInput.FlushAsync().ConfigureAwait(false);
    }

    private async Task ReadLoopAsync(Stream stream, List<byte> buf, bool isStdout)
    {
        var chunk = new byte[ReadChunk];
        try
        {
            while (true)
            {
                int n;
                try
                {
                    n = await stream.ReadAsync(chunk.AsMemory(), CancellationToken.None).ConfigureAwait(false);
                }
                catch (IOException) { break; }
                catch (ObjectDisposedException) { break; }

                if (n == 0)
                {
                    break;
                }

                lock (this._bufferGate)
                {
                    // Bulk-copy the chunk into the backing list. ArraySegment<byte>
                    // implements ICollection<byte>, so AddRange takes the fast path
                    // and avoids per-byte resize/branching on the hot path.
                    buf.AddRange(new ArraySegment<byte>(chunk, 0, n));
                    if (isStdout)
                    {
                        // Swap the signal BEFORE completing the old one so any
                        // consumer that next reads `_stdoutSignal` sees a fresh
                        // (uncompleted) TCS. Without this, a consumer looping in
                        // WaitForSentinelAsync would re-read the same completed
                        // TCS, causing WaitAsync to return synchronously every
                        // iteration — a tight busy-spin until the sentinel
                        // arrives or the timeout fires.
                        var prev = this._stdoutSignal;
                        this._stdoutSignal = NewSignal();
                        _ = prev.TrySetResult(true);
                    }
                }
            }
        }
        finally
        {
            if (isStdout)
            {
                lock (this._bufferGate)
                {
                    this._stdoutClosed = true;
                    _ = this._stdoutSignal.TrySetResult(true);
                }
            }
        }
    }

    private static byte[] SnapshotRange(List<byte> buf, int start, int length)
    {
        if (length <= 0)
        {
            return Array.Empty<byte>();
        }
        var result = new byte[length];
        for (var i = 0; i < length; i++)
        {
            result[i] = buf[start + i];
        }
        return result;
    }

    private static int IndexOf(List<byte> buf, byte[] needle, int from)
    {
        // Caller holds the buffer gate. Linear search; needle is ~30 bytes
        // so this is fine for our buffer sizes (< few MB even in worst-case
        // overflow).
        var end = buf.Count - needle.Length;
        for (var i = from; i <= end; i++)
        {
            var match = true;
            for (var j = 0; j < needle.Length; j++)
            {
                if (buf[i + j] != needle[j])
                {
                    match = false;
                    break;
                }
            }
            if (match)
            {
                return i;
            }
        }
        return -1;
    }

    /// <summary>
    /// Truncate <paramref name="data"/> to at most <paramref name="cap"/> UTF-8 bytes
    /// using a head/tail strategy. Splits between runes (never inside a multi-byte
    /// UTF-8 sequence) so the result is always valid UTF-8 / .NET text.
    /// </summary>
    /// <param name="data">The text to truncate.</param>
    /// <param name="cap">Maximum number of UTF-8 bytes to retain (excluding the marker line).</param>
    /// <returns>The (possibly truncated) text and a flag indicating whether truncation occurred.</returns>
    internal static (string text, bool truncated) TruncateHeadTail(string data, int cap)
    {
        if (cap <= 0 || string.IsNullOrEmpty(data))
        {
            return (data, false);
        }

        var totalBytes = Encoding.UTF8.GetByteCount(data);
        if (totalBytes <= cap)
        {
            return (data, false);
        }

        var headCap = cap / 2;
        var tailCap = cap - headCap;
        var head = TakePrefixByBytes(data, headCap);
        var tail = TakeSuffixByBytes(data, tailCap);
        var droppedBytes = totalBytes - Encoding.UTF8.GetByteCount(head) - Encoding.UTF8.GetByteCount(tail);
        if (droppedBytes < 0)
        {
            droppedBytes = 0;
        }
        return ($"{head}\n[... truncated {droppedBytes} bytes ...]\n{tail}", true);
    }

    private static string TakePrefixByBytes(string data, int maxBytes)
    {
        if (maxBytes <= 0)
        {
            return string.Empty;
        }

        // Iterate by rune so we never split a surrogate pair and never have to
        // reason about Encoder state. Rune.Utf8SequenceLength is the byte width
        // of the rune in UTF-8; for unpaired surrogates EnumerateRunes yields
        // Rune.ReplacementChar (3 bytes), which matches what UTF-8 encoding
        // would have produced anyway.
        var byteCount = 0;
        var charsTaken = 0;
        foreach (var rune in data.EnumerateRunes())
        {
            var n = rune.Utf8SequenceLength;
            if (byteCount + n > maxBytes)
            {
                break;
            }
            byteCount += n;
            charsTaken += rune.Utf16SequenceLength;
        }
        return data.Substring(0, charsTaken);
    }

    private static string TakeSuffixByBytes(string data, int maxBytes)
    {
        if (maxBytes <= 0)
        {
            return string.Empty;
        }

        // Same approach as the prefix walker, but we need to skip an unknown
        // prefix and keep the suffix. Walk the runes forward to learn the total
        // UTF-8 byte count, then walk again skipping while the remaining tail
        // would exceed `maxBytes`.
        var totalBytes = 0;
        foreach (var rune in data.EnumerateRunes())
        {
            totalBytes += rune.Utf8SequenceLength;
        }
        if (totalBytes <= maxBytes)
        {
            return data;
        }

        var bytesToSkip = totalBytes - maxBytes;
        var skipped = 0;
        var startCharIndex = 0;
        foreach (var rune in data.EnumerateRunes())
        {
            var n = rune.Utf8SequenceLength;
            if (skipped + n > bytesToSkip)
            {
                break;
            }
            skipped += n;
            startCharIndex += rune.Utf16SequenceLength;
        }
        return data.Substring(startCharIndex);
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
        catch (InvalidOperationException) { }
        catch (System.ComponentModel.Win32Exception) { }
    }

    private static TaskCompletionSource<bool> NewSignal()
        => new(TaskCreationOptions.RunContinuationsAsynchronously);
}
