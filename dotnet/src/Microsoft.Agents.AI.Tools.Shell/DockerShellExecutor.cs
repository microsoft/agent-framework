// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Security.Cryptography;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.Tools.Shell;

/// <summary>
/// Sandboxed shell tool backed by a Docker (or compatible) container runtime.
/// </summary>
/// <remarks>
/// <para>
/// Exposes the same public surface as <see cref="LocalShellExecutor"/> but executes
/// commands inside a container. The container is intended to be the
/// security boundary, and the defaults bias toward a restrictive baseline
/// (<c>--network none</c>, non-root user, <c>--read-only</c> root filesystem,
/// <c>--cap-drop=ALL</c>, <c>--security-opt=no-new-privileges</c>, memory and
/// pids limits, <c>--tmpfs /tmp</c>). These are a best-effort starting point,
/// NOT a guarantee: the actual isolation you get depends on the host kernel,
/// the container runtime, the image, and any caller-supplied
/// <c>ExtraRunArgs</c>. Do not rely on this tool as your sole defense against
/// untrusted input. Approval gating via <see cref="AsAIFunction"/> is the
/// primary safety control; pair it with the precautions you would normally
/// apply when running adversarial code: review the model's output before
/// acting on it, run on a host you can afford to lose, monitor for resource
/// exhaustion, and consider stronger isolation (a dedicated VM, gVisor/Kata,
/// network segmentation) when stakes are high.
/// </para>
/// <para>
/// Persistent mode reuses <see cref="ShellSession"/> by launching
/// <c>docker exec -i &lt;container&gt; bash --noprofile --norc</c> as the
/// long-lived shell — the sentinel protocol works unchanged because the
/// host process is still a bash REPL connected over pipes. Stateless mode
/// runs each call in a fresh <c>docker run --rm</c>.
/// </para>
/// <para>
/// <b>Single-session ownership.</b> In persistent mode the executor owns a long-lived
/// container plus the bash REPL inside it. That container's filesystem, environment,
/// working directory, and any artifacts the agent has produced are visible to every
/// subsequent command, and a single stdin/stdout pipe serializes every call. A
/// persistent-mode <see cref="DockerShellExecutor"/> is therefore intended to be owned by
/// exactly one conversation / agent session — i.e., one user. Do not share one instance
/// across users, tenants, or concurrent conversations: their state leaks together inside
/// the container and commands queue behind each other. Create one executor per session,
/// dispose it when the session ends (disposal stops and removes the container), and in DI
/// scenarios register it with a per-session scope. If a shared instance is genuinely
/// required, use <see cref="ShellMode.Stateless"/>, which gives each call its own
/// throwaway <c>docker run --rm</c>.
/// </para>
/// </remarks>
public sealed class DockerShellExecutor : ShellExecutor
{
    /// <summary>Default container image. A small Microsoft-maintained Linux base.</summary>
    public const string DefaultImage = "mcr.microsoft.com/azurelinux/base/core:3.0";

    /// <summary>Default Docker network mode (no network).</summary>
    internal const string DefaultNetwork = DockerNetworkMode.None;

    /// <summary>Default container memory limit, in bytes (512 MiB).</summary>
    internal const long DefaultMemoryBytes = 512L * 1024 * 1024;

    /// <summary>Default pids limit.</summary>
    public const int DefaultPidsLimit = 256;

    /// <summary>Default container working directory.</summary>
    public const string DefaultContainerWorkdir = "/workspace";

    /// <summary>
    /// Recommended default per-command timeout (30 seconds). Pass this
    /// explicitly via <see cref="DockerShellExecutorOptions.Timeout"/> to
    /// opt in. Note that <see langword="null"/> (the property default) means
    /// <em>no timeout</em>.
    /// </summary>
    public static readonly TimeSpan DefaultTimeout = TimeSpan.FromSeconds(30);

    private readonly string _image;
    private readonly ShellMode _mode;
    private readonly string? _hostWorkdir;
    private readonly string _containerWorkdir;
    private readonly bool _mountReadonly;
    private readonly string _network;
    private readonly long _memoryBytes;
    private readonly int _pidsLimit;
    private readonly ContainerUser _user;
    private readonly bool _readOnlyRoot;
    private readonly IReadOnlyList<string> _extraRunArgs;
    private readonly IReadOnlyDictionary<string, string> _env;
    private readonly ShellPolicy _policy;
    private readonly TimeSpan? _timeout;
    private readonly int _maxOutputBytes;
    private ShellSession? _session;
    private bool _containerStarted;
    private readonly SemaphoreSlim _lifecycleLock = new(1, 1);

    /// <summary>
    /// Initializes a new instance of the <see cref="DockerShellExecutor"/>
    /// class with default options.
    /// </summary>
    public DockerShellExecutor() : this(new DockerShellExecutorOptions())
    {
    }

    /// <summary>
    /// Initializes a new instance of the <see cref="DockerShellExecutor"/> class.
    /// </summary>
    /// <param name="options">Configuration. <see langword="null"/> selects defaults.</param>
    public DockerShellExecutor(DockerShellExecutorOptions options)
    {
        _ = Throw.IfNull(options);
        _ = Throw.IfNull(options.Image);
        if (options.MaxOutputBytes <= 0)
        {
            throw new ArgumentOutOfRangeException(nameof(options), $"{nameof(options.MaxOutputBytes)} must be positive.");
        }
        if (options.MemoryBytes is <= 0)
        {
            throw new ArgumentOutOfRangeException(nameof(options), $"{nameof(options.MemoryBytes)} must be positive.");
        }

        this._image = options.Image;
        this.ContainerName = options.ContainerName ?? GenerateContainerName();
        this._mode = options.Mode;
        this._hostWorkdir = options.HostWorkdir;
        this._containerWorkdir = options.ContainerWorkdir ?? DefaultContainerWorkdir;
        this._mountReadonly = options.MountReadonly;
        this._network = options.Network ?? DefaultNetwork;
        this._memoryBytes = options.MemoryBytes ?? DefaultMemoryBytes;
        this._pidsLimit = options.PidsLimit;
        this._user = options.User ?? ContainerUser.Default;
        this._readOnlyRoot = options.ReadOnlyRoot;
        this._extraRunArgs = options.ExtraRunArgs ?? Array.Empty<string>();
        this._env = options.Environment ?? new Dictionary<string, string>();
        this._policy = options.Policy ?? new ShellPolicy();
        this._timeout = options.Timeout;
        this._maxOutputBytes = options.MaxOutputBytes;
        this.DockerBinary = options.DockerBinary ?? "docker";
    }

    /// <summary>Gets the container name (auto-generated when not specified at construction).</summary>
    public string ContainerName { get; }

    /// <summary>Gets the docker binary path.</summary>
    public string DockerBinary { get; }

    /// <summary>Eagerly start the container (and inner shell session in persistent mode).</summary>
    public override async Task InitializeAsync(CancellationToken cancellationToken = default)
    {
        await this._lifecycleLock.WaitAsync(cancellationToken).ConfigureAwait(false);
        try
        {
            if (this._containerStarted)
            {
                return;
            }
            await this.StartContainerAsync(cancellationToken).ConfigureAwait(false);
            this._containerStarted = true;
            if (this._mode == ShellMode.Persistent)
            {
                var execArgv = BuildExecArgv(this.DockerBinary, this.ContainerName);
                // BuildExecArgv already includes the bash flags
                // (--noprofile --norc) at the end of the argv. We pass
                // ShellKind.Sh here (not Bash) because Sh's
                // PersistentArgv() returns an empty suffix and forwards
                // ExtraArgv unchanged; Bash would re-append
                // --noprofile/--norc and produce a duplicated argv.
                var inner = new ResolvedShell(execArgv[0], ShellKind.Sh, ExtraArgv: execArgv.Skip(1).ToArray());
                this._session = new ShellSession(
                    inner,
                    workingDirectory: null, // workdir is set on the container itself
                    confineWorkingDirectory: false,
                    environment: null,
                    cleanEnvironment: false,
                    maxOutputBytes: this._maxOutputBytes);
            }
        }
        finally
        {
            _ = this._lifecycleLock.Release();
        }
    }

    /// <inheritdoc />
    public override async ValueTask DisposeAsync()
    {
        await this._lifecycleLock.WaitAsync().ConfigureAwait(false);
        try
        {
            if (this._session is not null)
            {
                try { await this._session.DisposeAsync().ConfigureAwait(false); }
                finally { this._session = null; }
            }
            if (this._containerStarted)
            {
                await this.StopContainerAsync().ConfigureAwait(false);
                this._containerStarted = false;
            }
        }
        finally
        {
            _ = this._lifecycleLock.Release();
        }
        this._lifecycleLock.Dispose();
    }

    /// <summary>Run a single command inside the container.</summary>
    /// <exception cref="ShellCommandRejectedException">Thrown when the policy denies the command.</exception>
    public override async Task<ShellResult> RunAsync(string command, CancellationToken cancellationToken = default)
    {
        if (command is null)
        {
            throw new ArgumentNullException(nameof(command));
        }

        var decision = this._policy.Evaluate(new ShellRequest(command, this._containerWorkdir));
        if (!decision.Allowed)
        {
            throw new ShellCommandRejectedException(
                $"Command rejected by policy: {decision.Reason ?? "(unspecified)"}");
        }

        if (this._mode == ShellMode.Persistent)
        {
            if (this._session is null)
            {
                await this.InitializeAsync(cancellationToken).ConfigureAwait(false);
            }
            return await this._session!.RunAsync(command, this._timeout, cancellationToken).ConfigureAwait(false);
        }

        return await this.RunStatelessAsync(command, cancellationToken).ConfigureAwait(false);
    }

    /// <summary>Format a byte count into the value passed to <c>docker --memory</c> (e.g. <c>536870912b</c>).</summary>
    internal static string FormatMemoryBytes(long memoryBytes) =>
        memoryBytes.ToString(System.Globalization.CultureInfo.InvariantCulture) + "b";

    /// <summary>
    /// Build the AIFunction for this tool.
    /// </summary>
    /// <remarks>
    /// When <paramref name="requireApproval"/> is <see langword="null"/>
    /// (the default), the returned function is wrapped in
    /// <see cref="ApprovalRequiredAIFunction"/>. The caller must
    /// explicitly pass <see langword="false"/> to opt out of approval
    /// gating. Container configuration alone is not a sufficient signal
    /// to safely auto-execute model-generated commands — the
    /// approval/policy decision belongs to the agent author.
    /// </remarks>
    /// <param name="name">Function name surfaced to the model.</param>
    /// <param name="description">Function description for the model.</param>
    /// <param name="requireApproval">
    /// <see langword="true"/> or <see langword="null"/> (the default)
    /// wraps the function in <see cref="ApprovalRequiredAIFunction"/>;
    /// <see langword="false"/> opts out and returns the raw function.
    /// </param>
    public AIFunction AsAIFunction(string name = "run_shell", string? description = null, bool? requireApproval = null)
    {
        var effectiveRequireApproval = requireApproval ?? true;

        description ??=
            "Execute a single shell command inside an isolated Docker container and return its " +
            "stdout, stderr, and exit code. The container has no network, no host filesystem access " +
            "(except an optional read-only workspace mount), and runs as a non-root user. " +
            (this._mode == ShellMode.Persistent
                ? "PERSISTENT MODE: a single long-lived container handles every call; cd and exported variables persist."
                : "STATELESS MODE: each call runs in a fresh container.");

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
            new AIFunctionFactoryOptions { Name = name, Description = description });

        return effectiveRequireApproval ? new ApprovalRequiredAIFunction(fn) : fn;
    }

    /// <summary>
    /// Probe whether the configured docker binary can be reached. Returns
    /// <see langword="true"/> only if the binary exists on PATH and
    /// <c>docker version</c> succeeds within ~5 seconds.
    /// </summary>
    public static async Task<bool> IsAvailableAsync(string binary = "docker", CancellationToken cancellationToken = default)
    {
        try
        {
            var psi = new ProcessStartInfo
            {
                FileName = binary,
                RedirectStandardOutput = true,
                RedirectStandardError = true,
                UseShellExecute = false,
                CreateNoWindow = true,
            };
            psi.ArgumentList.Add("version");
            psi.ArgumentList.Add("--format");
            psi.ArgumentList.Add("{{.Server.Version}}");
            using var proc = new Process { StartInfo = psi };
            if (!proc.Start())
            {
                return false;
            }
            using var cts = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
            cts.CancelAfter(TimeSpan.FromSeconds(5));
            try
            {
                await proc.WaitForExitAsync(cts.Token).ConfigureAwait(false);
            }
            catch (OperationCanceledException)
            {
                try { proc.Kill(entireProcessTree: true); } catch { }
                return false;
            }
            return proc.ExitCode == 0;
        }
        catch (Win32Exception)
        {
            return false;
        }
        catch (InvalidOperationException)
        {
            return false;
        }
    }

    // ------------------------------------------------------------------
    // Pure argv builders — kept side-effect-free so tests don't need Docker.
    // ------------------------------------------------------------------

    /// <summary>Build the <c>docker run -d</c> argv that starts the long-lived container.</summary>
    public static IReadOnlyList<string> BuildRunArgv(
        string binary,
        string image,
        string containerName,
        ContainerUser user,
        string network,
        long memoryBytes,
        int pidsLimit,
        string workdir,
        string? hostWorkdir,
        bool mountReadonly,
        bool readOnlyRoot,
        IReadOnlyDictionary<string, string>? extraEnv,
        IReadOnlyList<string>? extraArgs)
    {
        _ = Throw.IfNull(user);
        var argv = new List<string>
        {
            binary,
            "run",
            "-d",
            "--rm",
            "--name", containerName,
            "--user", user.ToString(),
            "--network", network,
            "--memory", FormatMemoryBytes(memoryBytes),
            "--pids-limit", pidsLimit.ToString(System.Globalization.CultureInfo.InvariantCulture),
            "--cap-drop", "ALL",
            "--security-opt", "no-new-privileges",
            "--tmpfs", "/tmp:rw,nosuid,nodev,size=64m",
            "--workdir", workdir,
        };
        if (readOnlyRoot)
        {
            argv.Add("--read-only");
        }
        if (hostWorkdir is not null)
        {
            var ro = mountReadonly ? "ro" : "rw";
            argv.Add("-v");
            argv.Add($"{hostWorkdir}:{workdir}:{ro}");
        }
        if (extraEnv is not null)
        {
            foreach (var kv in extraEnv)
            {
                argv.Add("-e");
                argv.Add($"{kv.Key}={kv.Value}");
            }
        }
        if (extraArgs is not null)
        {
            foreach (var a in extraArgs) { argv.Add(a); }
        }
        argv.Add(image);
        argv.Add("sleep");
        argv.Add("infinity");
        return argv;
    }

    /// <summary>
    /// Build the <c>docker exec -i &lt;container&gt; bash --noprofile --norc</c> argv for
    /// the persistent inner shell. Stateless callers should use
    /// <see cref="BuildRunArgvStateless"/>; this method intentionally does
    /// not produce a stand-alone command argv.
    /// </summary>
    public static IReadOnlyList<string> BuildExecArgv(string binary, string containerName)
    {
        return new List<string> { binary, "exec", "-i", containerName, "bash", "--noprofile", "--norc" };
    }

    private async Task StartContainerAsync(CancellationToken cancellationToken)
    {
        var argv = BuildRunArgv(
            this.DockerBinary, this._image, this.ContainerName, this._user, this._network,
            this._memoryBytes, this._pidsLimit, this._containerWorkdir, this._hostWorkdir,
            this._mountReadonly, this._readOnlyRoot, this._env, this._extraRunArgs);

        var (exit, _, stderr) = await RunDockerCommandAsync(argv, cancellationToken).ConfigureAwait(false);
        if (exit != 0)
        {
            throw new DockerNotAvailableException(
                $"Failed to start container ({exit}): {stderr.Trim()}");
        }
    }

    private async Task StopContainerAsync()
    {
        var argv = new[] { this.DockerBinary, "rm", "-f", this.ContainerName };
        try
        {
            using var cts = new CancellationTokenSource(TimeSpan.FromSeconds(10));
            _ = await RunDockerCommandAsync(argv, cts.Token).ConfigureAwait(false);
        }
        catch (Exception ex) when (ex is OperationCanceledException || ex is Win32Exception || ex is InvalidOperationException)
        {
            // Best-effort teardown.
        }
    }

    private async Task<ShellResult> RunStatelessAsync(string command, CancellationToken cancellationToken)
    {
        var perCallName = GenerateContainerName();
        var argv = new List<string>(this.BuildRunArgvStateless(perCallName));
        argv.Add(this._image);
        argv.Add("bash");
        argv.Add("-c");
        argv.Add(command);

        var stopwatch = Stopwatch.StartNew();
        var stdoutBuf = new HeadTailBuffer(this._maxOutputBytes);
        var stderrBuf = new HeadTailBuffer(this._maxOutputBytes);

        var psi = new ProcessStartInfo
        {
            FileName = argv[0],
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            UseShellExecute = false,
            CreateNoWindow = true,
        };
        for (var i = 1; i < argv.Count; i++) { psi.ArgumentList.Add(argv[i]); }

        using var proc = new Process { StartInfo = psi, EnableRaisingEvents = true };
        proc.OutputDataReceived += (_, e) => { if (e.Data is not null) { stdoutBuf.AppendLine(e.Data); } };
        proc.ErrorDataReceived += (_, e) => { if (e.Data is not null) { stderrBuf.AppendLine(e.Data); } };

        try { _ = proc.Start(); }
        catch (Win32Exception ex)
        {
            throw new IOException($"Failed to launch '{this.DockerBinary}': {ex.Message}", ex);
        }
        proc.BeginOutputReadLine();
        proc.BeginErrorReadLine();

        var timedOut = false;
        using var timeoutCts = this._timeout is null
            ? new CancellationTokenSource()
            : new CancellationTokenSource(this._timeout.Value);
        using var linkedCts = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken, timeoutCts.Token);
        try
        {
            await proc.WaitForExitAsync(linkedCts.Token).ConfigureAwait(false);
        }
        catch (OperationCanceledException) when (timeoutCts.IsCancellationRequested && !cancellationToken.IsCancellationRequested)
        {
            timedOut = true;
            // Kill the running container by name; --rm reaps it.
            await this.BestEffortKillContainerAsync(perCallName).ConfigureAwait(false);
            try { await proc.WaitForExitAsync(CancellationToken.None).ConfigureAwait(false); }
            catch (Exception ex) when (ex is InvalidOperationException || ex is Win32Exception) { }
        }
        catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested)
        {
            // Caller-driven cancellation: --rm only fires when PID 1 exits, so
            // if we just propagate, the container keeps running indefinitely.
            // Kill it explicitly before rethrowing so we don't leak containers.
            await this.BestEffortKillContainerAsync(perCallName).ConfigureAwait(false);
            try { await proc.WaitForExitAsync(CancellationToken.None).ConfigureAwait(false); }
            catch (Exception ex) when (ex is InvalidOperationException || ex is Win32Exception) { }
            throw;
        }
        proc.WaitForExit();
        stopwatch.Stop();

        var (sout, soutT) = stdoutBuf.ToFinalString();
        var (serr, serrT) = stderrBuf.ToFinalString();
        return new ShellResult(
            Stdout: sout,
            Stderr: serr,
            ExitCode: timedOut ? 124 : proc.ExitCode,
            Duration: stopwatch.Elapsed,
            Truncated: soutT || serrT,
            TimedOut: timedOut);
    }

    private List<string> BuildRunArgvStateless(string perCallName)
    {
        var argv = new List<string>
        {
            this.DockerBinary,
            "run", "--rm", "-i",
            "--name", perCallName,
            "--user", this._user.ToString(),
            "--network", this._network,
            "--memory", FormatMemoryBytes(this._memoryBytes),
            "--pids-limit", this._pidsLimit.ToString(System.Globalization.CultureInfo.InvariantCulture),
            "--cap-drop", "ALL",
            "--security-opt", "no-new-privileges",
            "--tmpfs", "/tmp:rw,nosuid,nodev,size=64m",
            "--workdir", this._containerWorkdir,
        };
        if (this._readOnlyRoot) { argv.Add("--read-only"); }
        if (this._hostWorkdir is not null)
        {
            var ro = this._mountReadonly ? "ro" : "rw";
            argv.Add("-v");
            argv.Add($"{this._hostWorkdir}:{this._containerWorkdir}:{ro}");
        }
        foreach (var kv in this._env)
        {
            argv.Add("-e");
            argv.Add($"{kv.Key}={kv.Value}");
        }
        foreach (var a in this._extraRunArgs) { argv.Add(a); }
        return argv;
    }

    private async Task BestEffortKillContainerAsync(string containerName)
    {
        try
        {
            using var killCts = new CancellationTokenSource(TimeSpan.FromSeconds(5));
            _ = await RunDockerCommandAsync(
                new[] { this.DockerBinary, "kill", "--signal", "KILL", containerName }, killCts.Token).ConfigureAwait(false);
        }
        catch (Exception ex) when (ex is OperationCanceledException || ex is Win32Exception || ex is InvalidOperationException)
        {
            // best-effort: container may already be gone
        }
    }

    private static async Task<(int ExitCode, string Stdout, string Stderr)> RunDockerCommandAsync(
        IReadOnlyList<string> argv, CancellationToken cancellationToken)
    {
        var psi = new ProcessStartInfo
        {
            FileName = argv[0],
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            UseShellExecute = false,
            CreateNoWindow = true,
        };
        for (var i = 1; i < argv.Count; i++) { psi.ArgumentList.Add(argv[i]); }
        // Cap helper-command output at 1 MiB. These commands (`docker version`,
        // `docker kill`, `docker pull`) shouldn't produce more than that, but a
        // chatty `docker pull` progress stream can easily run into hundreds of
        // KiB; bound the buffer so we never exhaust memory on misbehaviour.
        const int HelperOutputCap = 1 * 1024 * 1024;
        var stdoutBuf = new HeadTailBuffer(HelperOutputCap);
        var stderrBuf = new HeadTailBuffer(HelperOutputCap);
        using var proc = new Process { StartInfo = psi, EnableRaisingEvents = true };
        proc.OutputDataReceived += (_, e) => { if (e.Data is not null) { stdoutBuf.AppendLine(e.Data); } };
        proc.ErrorDataReceived += (_, e) => { if (e.Data is not null) { stderrBuf.AppendLine(e.Data); } };
        _ = proc.Start();
        proc.BeginOutputReadLine();
        proc.BeginErrorReadLine();
        await proc.WaitForExitAsync(cancellationToken).ConfigureAwait(false);
        proc.WaitForExit();
        return (proc.ExitCode, stdoutBuf.ToFinalString().text, stderrBuf.ToFinalString().text);
    }

    private static string GenerateContainerName()
    {
        var bytes = new byte[6];
#if NET6_0_OR_GREATER
        RandomNumberGenerator.Fill(bytes);
#else
        using var rng = RandomNumberGenerator.Create();
        rng.GetBytes(bytes);
#endif
#pragma warning disable CA1308
        return "af-shell-" + Convert.ToHexString(bytes).ToLowerInvariant();
#pragma warning restore CA1308
    }
}

/// <summary>
/// Thrown when the configured docker (or compatible) binary cannot start a
/// container — typically because the daemon isn't running, the image
/// can't be pulled, or the binary isn't on PATH.
/// </summary>
public sealed class DockerNotAvailableException : Exception
{
    /// <summary>Initializes a new instance of the <see cref="DockerNotAvailableException"/> class.</summary>
    public DockerNotAvailableException() { }

    /// <summary>Initializes a new instance of the <see cref="DockerNotAvailableException"/> class.</summary>
    /// <param name="message">The exception message.</param>
    public DockerNotAvailableException(string message) : base(message) { }

    /// <summary>Initializes a new instance of the <see cref="DockerNotAvailableException"/> class.</summary>
    /// <param name="message">The exception message.</param>
    /// <param name="inner">The inner exception.</param>
    public DockerNotAvailableException(string message, Exception inner) : base(message, inner) { }
}
