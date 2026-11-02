// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Buffers;
using System.Collections.Generic;
using System.Linq;
using System.Security.Cryptography;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using HyperlightSandbox.Api;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Hyperlight.Internal;

/// <summary>
/// Captures a per-run snapshot of the provider state and owns the
/// lifecycle of the underlying <see cref="Sandbox"/>. A single
/// <see cref="SandboxExecutor"/> is shared across runs and serializes
/// execution via snapshot/restore.
/// </summary>
internal sealed class SandboxExecutor : IDisposable
{
    private readonly SemaphoreSlim _executionLock = new(1, 1);

    private Sandbox? _sandbox;
    private SandboxSnapshot? _warmSnapshot;
    private string? _lastConfigFingerprint;
    private bool _disposed;

    /// <summary>
    /// Immutable snapshot of provider state at the start of a run.
    /// Used to build a run-scoped <c>execute_code</c> function that is
    /// independent of subsequent CRUD mutations.
    /// </summary>
    internal sealed class RunSnapshot
    {
        public RunSnapshot(
            IReadOnlyList<AIFunction> tools,
            IReadOnlyList<FileMount> fileMounts,
            IReadOnlyList<AllowedDomain> allowedDomains,
            HyperlightCodeActProviderOptions options,
            Guid toolRegistryVersion = default)
        {
            this.Tools = tools.ToList();
            this.FileMounts = fileMounts.ToList();
            this.AllowedDomains = allowedDomains
                .Select(domain => new AllowedDomain(domain.Target, domain.Methods?.ToArray()))
                .ToList();
            this.Backend = options.Backend;
            this.ModulePath = options.ModulePath;
            this.HeapSize = options.HeapSize;
            this.StackSize = options.StackSize;
            this.HostInputDirectory = options.HostInputDirectory;
            this.ToolRegistryVersion = toolRegistryVersion;
            this.ConfigFingerprint = ComputeFingerprint(
                this.Tools,
                this.FileMounts,
                this.AllowedDomains,
                this.HostInputDirectory,
                toolRegistryVersion,
                this.Backend,
                this.ModulePath,
                this.HeapSize,
                this.StackSize);
        }

        public IReadOnlyList<AIFunction> Tools { get; }

        public IReadOnlyList<FileMount> FileMounts { get; }

        public IReadOnlyList<AllowedDomain> AllowedDomains { get; }

        public SandboxBackend Backend { get; }

        public string? ModulePath { get; }

        public string? HeapSize { get; }

        public string? StackSize { get; }

        public string? HostInputDirectory { get; }

        public Guid ToolRegistryVersion { get; }

        /// <summary>
        /// Stable fingerprint of the configuration that materially affects how
        /// the sandbox must be built. Used by <see cref="SandboxExecutor"/> to
        /// decide whether a previously-built sandbox can be reused or must be
        /// rebuilt because its capabilities or runtime options have changed.
        /// </summary>
        public string ConfigFingerprint { get; }

        internal static string ComputeFingerprint(
            IReadOnlyList<AIFunction> tools,
            IReadOnlyList<FileMount> fileMounts,
            IReadOnlyList<AllowedDomain> allowedDomains,
            string? hostInputDirectory,
            Guid toolRegistryVersion = default,
            SandboxBackend backend = SandboxBackend.JavaScript,
            string? modulePath = null,
            string? heapSize = null,
            string? stackSize = null)
        {
            var buffer = new ArrayBufferWriter<byte>();
            using (var writer = new Utf8JsonWriter(buffer))
            {
                writer.WriteStartObject();
                writer.WriteNumber("backend", (int)backend);
                writer.WriteString("modulePath", modulePath);
                writer.WriteString("heapSize", heapSize);
                writer.WriteString("stackSize", stackSize);
                writer.WriteString("hostInputDirectory", hostInputDirectory);
                writer.WriteString("toolRegistryVersion", toolRegistryVersion);

                writer.WritePropertyName("tools");
                writer.WriteStartArray();
                foreach (var name in tools.Select(tool => tool.Name).OrderBy(name => name, StringComparer.Ordinal))
                {
                    writer.WriteStringValue(name);
                }

                writer.WriteEndArray();

                writer.WritePropertyName("fileMounts");
                writer.WriteStartArray();
                foreach (var mount in fileMounts
                    .OrderBy(mount => mount.MountPath, StringComparer.Ordinal)
                    .ThenBy(mount => mount.HostPath, StringComparer.Ordinal))
                {
                    writer.WriteStartObject();
                    writer.WriteString("mountPath", mount.MountPath);
                    writer.WriteString("hostPath", mount.HostPath);
                    writer.WriteEndObject();
                }

                writer.WriteEndArray();

                var domains = allowedDomains
                    .Select(domain => (
                        domain.Target,
                        Methods: domain.Methods?.OrderBy(method => method, StringComparer.Ordinal).ToArray()))
                    .ToList();
                domains.Sort(static (left, right) =>
                {
                    var targetComparison = StringComparer.Ordinal.Compare(left.Target, right.Target);
                    return targetComparison != 0
                        ? targetComparison
                        : CompareStringArrays(left.Methods, right.Methods);
                });

                writer.WritePropertyName("allowedDomains");
                writer.WriteStartArray();
                foreach (var domain in domains)
                {
                    writer.WriteStartObject();
                    writer.WriteString("target", domain.Target);
                    writer.WritePropertyName("methods");
                    if (domain.Methods is null)
                    {
                        writer.WriteNullValue();
                    }
                    else
                    {
                        writer.WriteStartArray();
                        foreach (var method in domain.Methods)
                        {
                            writer.WriteStringValue(method);
                        }

                        writer.WriteEndArray();
                    }

                    writer.WriteEndObject();
                }

                writer.WriteEndArray();
                writer.WriteEndObject();
            }

            return Convert.ToHexString(SHA256.HashData(buffer.WrittenSpan));
        }

        private static int CompareStringArrays(string[]? left, string[]? right)
        {
            if (left is null)
            {
                return right is null ? 0 : -1;
            }

            if (right is null)
            {
                return 1;
            }

            var sharedLength = Math.Min(left.Length, right.Length);
            for (var index = 0; index < sharedLength; index++)
            {
                var comparison = StringComparer.Ordinal.Compare(left[index], right[index]);
                if (comparison != 0)
                {
                    return comparison;
                }
            }

            return left.Length.CompareTo(right.Length);
        }
    }

    /// <summary>
    /// Executes <paramref name="code"/> inside the sandbox using the
    /// captured <paramref name="snapshot"/>. Builds (or rebuilds) the
    /// sandbox lazily when the snapshot's configuration fingerprint
    /// differs from the previously-used one.
    /// </summary>
    public async Task<string> ExecuteAsync(RunSnapshot snapshot, string code, CancellationToken cancellationToken)
    {
        await this._executionLock.WaitAsync(cancellationToken).ConfigureAwait(false);
        try
        {
            this.EnsureInitialized(snapshot);

            if (this._warmSnapshot is not null)
            {
                this._sandbox!.Restore(this._warmSnapshot);
            }

            ExecutionResult result;
            try
            {
                result = this._sandbox!.Run(code);
            }
#pragma warning disable CA1031 // Surface sandbox execution failures as structured JSON rather than propagating.
            catch (Exception ex)
#pragma warning restore CA1031
            {
                return BuildErrorResult(ex.Message);
            }

            return BuildResult(result);
        }
        finally
        {
            this._executionLock.Release();
        }
    }

    private void EnsureInitialized(RunSnapshot snapshot)
    {
        if (this._sandbox is not null && string.Equals(this._lastConfigFingerprint, snapshot.ConfigFingerprint, StringComparison.Ordinal))
        {
            return;
        }

        // Configuration changed (or first run) — dispose the previous sandbox
        // so the new one picks up the current capabilities and runtime options.
        this._warmSnapshot?.Dispose();
        this._sandbox?.Dispose();
        this._warmSnapshot = null;
        this._sandbox = null;

        this.BuildAndWarmUp(snapshot);
    }

    private void BuildAndWarmUp(RunSnapshot snapshot)
    {
        var builder = new SandboxBuilder()
            .WithBackend(snapshot.Backend);

        if (!string.IsNullOrEmpty(snapshot.ModulePath))
        {
            builder = builder.WithModulePath(snapshot.ModulePath!);
        }

        if (!string.IsNullOrEmpty(snapshot.HeapSize))
        {
            builder = builder.WithHeapSize(snapshot.HeapSize!);
        }

        if (!string.IsNullOrEmpty(snapshot.StackSize))
        {
            builder = builder.WithStackSize(snapshot.StackSize!);
        }

        var hostInput = snapshot.HostInputDirectory;
        if (!string.IsNullOrEmpty(hostInput))
        {
            builder = builder.WithInputDir(hostInput!);
        }

        // The Hyperlight .NET SDK currently exposes only a single input + output + temp-output
        // surface; per-mount configuration (`FileMount`) is captured in the execute_code
        // description so the model is aware of the layout, and will be wired to a richer
        // mount API once the SDK exposes one.
        if (snapshot.FileMounts.Count > 0 || !string.IsNullOrEmpty(hostInput))
        {
            builder = builder.WithTempOutput();
        }

        var sandbox = builder.Build();

        // Tools must be registered before the first Run() call.
        ToolBridge.RegisterAll(sandbox, snapshot.Tools);

        foreach (var allowedDomain in snapshot.AllowedDomains)
        {
            sandbox.AllowDomain(allowedDomain.Target, allowedDomain.Methods);
        }

        // Warm-up run to trigger lazy initialization, then capture a clean snapshot
        // that is restored before every subsequent user invocation.
        // Backend-specific no-op used to trigger lazy guest runtime initialization
        // before the warm snapshot is captured. Matches the values used by the
        // upstream HyperlightSandbox.Extensions.AI CodeExecutionTool reference.
        _ = sandbox.Run(snapshot.Backend == SandboxBackend.JavaScript ? "void 0;" : "None");
        this._warmSnapshot = sandbox.Snapshot();
        this._sandbox = sandbox;
        this._lastConfigFingerprint = snapshot.ConfigFingerprint;
    }

    private static string BuildResult(ExecutionResult result) =>
        JsonSerializer.Serialize(
            new HyperlightExecutionResult(
                result.Stdout ?? string.Empty,
                result.Stderr ?? string.Empty,
                result.ExitCode,
                result.ExitCode == 0),
            HyperlightJsonContext.Default.HyperlightExecutionResult);

    private static string BuildErrorResult(string message) =>
        JsonSerializer.Serialize(
            new HyperlightExecutionResult(string.Empty, message, -1, false),
            HyperlightJsonContext.Default.HyperlightExecutionResult);

    public void Dispose()
    {
        if (this._disposed)
        {
            return;
        }

        this._disposed = true;
        this._warmSnapshot?.Dispose();
        this._sandbox?.Dispose();
        this._executionLock.Dispose();
    }
}
