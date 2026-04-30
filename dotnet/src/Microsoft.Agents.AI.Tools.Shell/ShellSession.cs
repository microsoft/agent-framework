// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Globalization;
using System.IO;
using System.Linq;
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
/// Cross-OS implementation notes (hard-won, mirrors the Python sibling):
/// </para>
/// <list type="bullet">
/// <item>
/// PowerShell hosted with <c>-Command -</c> waits for a complete parse before
/// executing. Multi-line <c>try { ... }</c> blocks therefore stall with stdin
/// open. We sidestep this by base64-encoding the user command and invoking it
/// with <c>Invoke-Expression</c> on a single line.
/// </item>
/// <item>
/// <c>Write-Output</c> may drop trailing newlines when stdout is redirected.
/// The sentinel is therefore emitted via <c>[Console]::WriteLine</c> +
/// <c>[Console]::Out.Flush()</c>.
/// </item>
/// <item>
/// <c>$LASTEXITCODE</c> only tracks external-process exits. We derive the rc
/// from <c>$?</c> and caught exceptions as well.
/// </item>
/// <item>
/// stdout/stderr are drained by long-running reader tasks; per-call we
/// snapshot buffer offsets before writing the command and scan forward, which
/// avoids late stderr being attributed to the next command.
/// </item>
/// </list>
/// </remarks>
internal sealed class ShellSession : IAsyncDisposable
{
    private const int ReadChunk = 64 * 1024;
    private static readonly TimeSpan ShutdownGrace = TimeSpan.FromSeconds(2);
    // Brief quiescence to let late stderr drain after the sentinel is seen.
    private static readonly TimeSpan StderrQuiescence = TimeSpan.FromMilliseconds(50);

    private readonly ResolvedShell _shell;
    private readonly string? _workingDirectory;
    private readonly IReadOnlyDictionary<string, string?>? _environment;
    private readonly int _maxOutputBytes;
    private readonly SemaphoreSlim _runLock = new(1, 1);
    private readonly SemaphoreSlim _lifecycleLock = new(1, 1);
    private readonly string _sentinelTag;

    private Process? _proc;
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
        IReadOnlyDictionary<string, string?>? environment,
        int maxOutputBytes)
    {
        this._shell = shell;
        this._workingDirectory = workingDirectory;
        this._environment = environment;
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

                using var cts = new CancellationTokenSource(ShutdownGrace);
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
            throw new InvalidOperationException("Persistent shell session is no longer alive.", ex);
        }

        var needle = Encoding.UTF8.GetBytes(sentinel);
        var hardCap = this._maxOutputBytes * 4;
        var (sentinelIdx, exitCode, timedOut, overflow) = await this.WaitForSentinelAsync(
            needle, stdoutOffset, hardCap, timeout, cancellationToken).ConfigureAwait(false);

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
        await Task.Delay(StderrQuiescence, cancellationToken).ConfigureAwait(false);

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
        if (this._shell.Kind == ShellKind.PowerShell)
        {
            // Base64-encode the command so multi-line constructs don't stall
            // the pwsh parser. Sentinel is emitted via [Console]::WriteLine
            // so the pipeline formatter can't drop the newline.
            var encoded = Convert.ToBase64String(Encoding.UTF8.GetBytes(command));
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
        return "{ " + command + "\n" +
               "}; __af_rc=$?; set +e; " +
               $"printf '\\n{sentinel}_%s\\n' \"$__af_rc\"\n";
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
                    for (var i = 0; i < n; i++)
                    {
                        buf.Add(chunk[i]);
                    }
                    if (isStdout)
                    {
                        var prev = this._stdoutSignal;
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

    internal static (string text, bool truncated) TruncateHeadTail(string data, int cap)
    {
        if (data.Length <= cap)
        {
            return (data, false);
        }
        var head = data.Substring(0, cap / 2);
        var tail = data.Substring(data.Length - (cap / 2));
        return ($"{head}\n[... truncated {data.Length - cap} chars ...]\n{tail}", true);
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
