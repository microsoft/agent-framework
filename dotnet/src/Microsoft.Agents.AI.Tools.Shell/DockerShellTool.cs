// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.Diagnostics;
using System.Linq;
using System.Security.Cryptography;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Tools.Shell;

/// <summary>
/// Sandboxed shell tool backed by a Docker (or compatible) container runtime.
/// </summary>
/// <remarks>
/// <para>
/// Mirrors the public surface of <see cref="LocalShellTool"/> but executes
/// commands inside an isolated container. The container is the security
/// boundary — when used with the default isolation flags
/// (<c>--network none</c>, non-root user, <c>--read-only</c> root,
/// <c>--cap-drop=ALL</c>, <c>--security-opt=no-new-privileges</c>, memory and
/// pids limits, <c>--tmpfs /tmp</c>) even running without approval gating
/// is reasonable for untrusted input, because a compromised guest cannot
/// reach the host filesystem, network, or processes.
/// </para>
/// <para>
/// Persistent mode reuses <see cref="ShellSession"/> by launching
/// <c>docker exec -i &lt;container&gt; bash --noprofile --norc</c> as the
/// long-lived shell — the sentinel protocol works unchanged because we're
/// still talking to a bash REPL over pipes. Stateless mode runs each call
/// in a fresh <c>docker run --rm</c>.
/// </para>
/// <para>
/// Mirrors the Python <c>DockerShellTool</c> in
/// <c>agent_framework_tools.shell._docker</c>.
/// </para>
/// </remarks>
public sealed class DockerShellTool : IDisposable, IAsyncDisposable, IShellExecutor
{
    /// <summary>Default container image. A small Microsoft-maintained Linux base.</summary>
    public const string DefaultImage = "mcr.microsoft.com/azurelinux/base/core:3.0";

    /// <summary>Default container user (nobody:nogroup on most distros).</summary>
    public const string DefaultContainerUser = "65534:65534";

    /// <summary>Default Docker network mode (no network).</summary>
    public const string DefaultNetwork = "none";

    /// <summary>Default container memory limit.</summary>
    public const string DefaultMemory = "512m";

    /// <summary>Default pids limit.</summary>
    public const int DefaultPidsLimit = 256;

    /// <summary>Default container working directory.</summary>
    public const string DefaultContainerWorkdir = "/workspace";

    private const int DefaultMaxOutputBytes = 64 * 1024;

    /// <summary>
    /// Recommended default per-command timeout (30 seconds). Pass this
    /// explicitly to the constructor to opt in to a bounded timeout. Note
    /// that <see langword="null"/> (the parameter default) means
    /// <em>no timeout</em>, matching the documented contract.
    /// </summary>
    public static readonly TimeSpan DefaultTimeout = TimeSpan.FromSeconds(30);

    private readonly string _image;
    private readonly ShellMode _mode;
    private readonly string? _hostWorkdir;
    private readonly string _containerWorkdir;
    private readonly bool _mountReadonly;
    private readonly string _network;
    private readonly string _memory;
    private readonly int _pidsLimit;
    private readonly string _user;
    private readonly bool _readOnlyRoot;
    private readonly IReadOnlyList<string> _extraRunArgs;
    private readonly IReadOnlyDictionary<string, string> _env;
    private readonly ShellPolicy _policy;
    private readonly TimeSpan? _timeout;
    private readonly int _maxOutputBytes;
    private readonly Action<string>? _onCommand;
    private ShellSession? _session;
    private bool _containerStarted;
    private readonly SemaphoreSlim _lifecycleLock = new(1, 1);

    /// <summary>
    /// Initializes a new instance of the <see cref="DockerShellTool"/> class.
    /// </summary>
    /// <param name="image">OCI image to run. Must include <c>bash</c> and (for persistent mode) <c>sleep</c>.</param>
    /// <param name="containerName">Optional container name. When <see langword="null"/>, a unique name is generated.</param>
    /// <param name="mode">Execution mode. Defaults to <see cref="ShellMode.Persistent"/>.</param>
    /// <param name="hostWorkdir">Optional host directory mounted at <paramref name="containerWorkdir"/>. Mounted read-only by default.</param>
    /// <param name="containerWorkdir">Path inside the container. Defaults to <c>/workspace</c>.</param>
    /// <param name="mountReadonly">When <see langword="true"/> (default), the host workdir is mounted read-only.</param>
    /// <param name="network">Docker network mode. Defaults to <c>none</c>.</param>
    /// <param name="memory">Container memory limit (e.g. <c>512m</c>, <c>2g</c>).</param>
    /// <param name="pidsLimit">Max processes inside the container.</param>
    /// <param name="user">UID:GID. Defaults to <c>65534:65534</c> (nobody).</param>
    /// <param name="readOnlyRoot">When <see langword="true"/> (default), the container root filesystem is read-only.</param>
    /// <param name="extraRunArgs">Additional args appended to <c>docker run</c>.</param>
    /// <param name="environment">Environment variables passed via <c>-e</c> to every command.</param>
    /// <param name="policy">Optional <see cref="ShellPolicy"/>. Less critical than for <see cref="LocalShellTool"/> since the container provides isolation.</param>
    /// <param name="timeout">Per-command timeout. <see langword="null"/> disables timeouts.</param>
    /// <param name="maxOutputBytes">Per-stream cap before head+tail truncation.</param>
    /// <param name="onCommand">Audit callback invoked for every allowed command.</param>
    /// <param name="dockerBinary">Override (e.g. <c>podman</c>).</param>
    public DockerShellTool(
        string image = DefaultImage,
        string? containerName = null,
        ShellMode mode = ShellMode.Persistent,
        string? hostWorkdir = null,
        string containerWorkdir = DefaultContainerWorkdir,
        bool mountReadonly = true,
        string network = DefaultNetwork,
        string memory = DefaultMemory,
        int pidsLimit = DefaultPidsLimit,
        string user = DefaultContainerUser,
        bool readOnlyRoot = true,
        IReadOnlyList<string>? extraRunArgs = null,
        IReadOnlyDictionary<string, string>? environment = null,
        ShellPolicy? policy = null,
        TimeSpan? timeout = null,
        int maxOutputBytes = DefaultMaxOutputBytes,
        Action<string>? onCommand = null,
        string dockerBinary = "docker")
    {
        if (maxOutputBytes <= 0)
        {
            throw new ArgumentOutOfRangeException(nameof(maxOutputBytes));
        }

        this._image = image ?? throw new ArgumentNullException(nameof(image));
        this.ContainerName = containerName ?? GenerateContainerName();
        this._mode = mode;
        this._hostWorkdir = hostWorkdir;
        this._containerWorkdir = containerWorkdir ?? DefaultContainerWorkdir;
        this._mountReadonly = mountReadonly;
        this._network = network ?? DefaultNetwork;
        this._memory = memory ?? DefaultMemory;
        this._pidsLimit = pidsLimit;
        this._user = user ?? DefaultContainerUser;
        this._readOnlyRoot = readOnlyRoot;
        this._extraRunArgs = extraRunArgs ?? Array.Empty<string>();
        this._env = environment ?? new Dictionary<string, string>();
        this._policy = policy ?? new ShellPolicy();
        this._timeout = timeout;
        this._maxOutputBytes = maxOutputBytes;
        this._onCommand = onCommand;
        this.DockerBinary = dockerBinary ?? "docker";
    }

    /// <summary>Gets the container name (auto-generated when not specified at construction).</summary>
    public string ContainerName { get; }

    /// <summary>Gets the docker binary path.</summary>
    public string DockerBinary { get; }

    /// <summary>Eagerly start the container (and inner shell session in persistent mode).</summary>
    public async Task StartAsync(CancellationToken cancellationToken = default)
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
                var execArgv = BuildExecArgv(this.DockerBinary, this.ContainerName, interactive: true);
                // ShellSession needs a ResolvedShell. Stitch one together: the
                // 'binary' is `docker`, the 'kind' is bash (because the inner
                // shell is bash), and ExtraArgv carries the docker-exec prefix
                // so PersistentArgv prepends it before the bash flags.
                var inner = new ResolvedShell(execArgv[0], ShellKind.Bash, ExtraArgv: execArgv.Skip(1).ToArray());
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

    /// <summary>Stop the inner shell session and tear down the container.</summary>
    public async Task CloseAsync(CancellationToken cancellationToken = default)
    {
        await this._lifecycleLock.WaitAsync(cancellationToken).ConfigureAwait(false);
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
    }

    /// <summary>Run a single command inside the container.</summary>
    /// <exception cref="ShellCommandRejectedException">Thrown when the policy denies the command.</exception>
    public async Task<ShellResult> RunAsync(string command, CancellationToken cancellationToken = default)
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
        this._onCommand?.Invoke(command);

        if (this._mode == ShellMode.Persistent)
        {
            if (this._session is null)
            {
                await this.StartAsync(cancellationToken).ConfigureAwait(false);
            }
            return await this._session!.RunAsync(command, this._timeout, cancellationToken).ConfigureAwait(false);
        }

        return await this.RunStatelessAsync(command, cancellationToken).ConfigureAwait(false);
    }

    /// <summary>
    /// Build the AIFunction for this tool. Unlike <see cref="LocalShellTool"/>,
    /// approval is NOT required by default since the container is the boundary.
    /// </summary>
    /// <param name="name">Function name surfaced to the model.</param>
    /// <param name="description">Function description for the model.</param>
    /// <param name="requireApproval">When <see langword="true"/>, wraps in <see cref="ApprovalRequiredAIFunction"/>. Defaults to <see langword="false"/>.</param>
    public AIFunction AsAIFunction(string name = "run_shell", string? description = null, bool requireApproval = false)
    {
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

        return requireApproval ? new ApprovalRequiredAIFunction(fn) : fn;
    }

    /// <inheritdoc />
    public void Dispose()
    {
#pragma warning disable VSTHRD002
        this.DisposeAsync().AsTask().GetAwaiter().GetResult();
#pragma warning restore VSTHRD002
    }

    /// <inheritdoc />
    public async ValueTask DisposeAsync()
    {
        await this.CloseAsync().ConfigureAwait(false);
        this._lifecycleLock.Dispose();
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
        string user,
        string network,
        string memory,
        int pidsLimit,
        string workdir,
        string? hostWorkdir,
        bool mountReadonly,
        bool readOnlyRoot,
        IReadOnlyDictionary<string, string>? extraEnv,
        IReadOnlyList<string>? extraArgs)
    {
        var argv = new List<string>
        {
            binary,
            "run",
            "-d",
            "--rm",
            "--name", containerName,
            "--user", user,
            "--network", network,
            "--memory", memory,
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

    /// <summary>Build the <c>docker exec -i &lt;container&gt; bash</c> argv.</summary>
    public static IReadOnlyList<string> BuildExecArgv(string binary, string containerName, bool interactive)
    {
        var argv = new List<string> { binary, "exec", "-i", containerName, "bash" };
        if (interactive)
        {
            argv.Add("--noprofile");
            argv.Add("--norc");
        }
        else
        {
            argv.Add("-c");
        }
        return argv;
    }

    private async Task StartContainerAsync(CancellationToken cancellationToken)
    {
        var argv = BuildRunArgv(
            this.DockerBinary, this._image, this.ContainerName, this._user, this._network,
            this._memory, this._pidsLimit, this._containerWorkdir, this._hostWorkdir,
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
        var stdoutBuf = new StringBuilder();
        var stderrBuf = new StringBuilder();

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
        proc.OutputDataReceived += (_, e) => { if (e.Data is not null) { _ = stdoutBuf.AppendLine(e.Data); } };
        proc.ErrorDataReceived += (_, e) => { if (e.Data is not null) { _ = stderrBuf.AppendLine(e.Data); } };

        try { _ = proc.Start(); }
        catch (Win32Exception ex)
        {
            throw new ShellExecutionException($"Failed to launch '{this.DockerBinary}': {ex.Message}", ex);
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
            try
            {
                using var killCts = new CancellationTokenSource(TimeSpan.FromSeconds(5));
                _ = await RunDockerCommandAsync(
                    new[] { this.DockerBinary, "kill", "--signal", "KILL", perCallName }, killCts.Token).ConfigureAwait(false);
            }
            catch (Exception ex) when (ex is OperationCanceledException || ex is Win32Exception || ex is InvalidOperationException)
            {
                // best-effort
            }
            try { await proc.WaitForExitAsync(CancellationToken.None).ConfigureAwait(false); }
            catch (Exception ex) when (ex is InvalidOperationException || ex is Win32Exception) { }
        }
        proc.WaitForExit();
        stopwatch.Stop();

        var (sout, soutT) = ShellSession.TruncateHeadTail(stdoutBuf.ToString(), this._maxOutputBytes);
        var (serr, serrT) = ShellSession.TruncateHeadTail(stderrBuf.ToString(), this._maxOutputBytes);
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
            "--user", this._user,
            "--network", this._network,
            "--memory", this._memory,
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
        var stdoutBuf = new StringBuilder();
        var stderrBuf = new StringBuilder();
        using var proc = new Process { StartInfo = psi, EnableRaisingEvents = true };
        proc.OutputDataReceived += (_, e) => { if (e.Data is not null) { _ = stdoutBuf.AppendLine(e.Data); } };
        proc.ErrorDataReceived += (_, e) => { if (e.Data is not null) { _ = stderrBuf.AppendLine(e.Data); } };
        _ = proc.Start();
        proc.BeginOutputReadLine();
        proc.BeginErrorReadLine();
        await proc.WaitForExitAsync(cancellationToken).ConfigureAwait(false);
        proc.WaitForExit();
        return (proc.ExitCode, stdoutBuf.ToString(), stderrBuf.ToString());
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
