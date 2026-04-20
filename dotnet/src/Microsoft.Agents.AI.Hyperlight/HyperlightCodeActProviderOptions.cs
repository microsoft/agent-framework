// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using HyperlightSandbox.Api;
using Microsoft.Extensions.AI;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.Hyperlight;

/// <summary>
/// Configuration options for <see cref="HyperlightCodeActProvider"/> and
/// <see cref="HyperlightExecuteCodeFunction"/>.
/// </summary>
/// <remarks>
/// Use the <see cref="CreateForWasm(string)"/> and <see cref="CreateForJavaScript()"/>
/// factory methods to construct an instance with the desired sandbox backend.
/// The parameterless constructor is equivalent to <see cref="CreateForJavaScript()"/>.
/// </remarks>
public sealed class HyperlightCodeActProviderOptions
{
    /// <summary>
    /// Initializes a new instance configured for the JavaScript backend.
    /// Equivalent to <see cref="CreateForJavaScript()"/>.
    /// </summary>
    public HyperlightCodeActProviderOptions()
        : this(SandboxBackend.JavaScript, modulePath: null)
    {
    }

    private HyperlightCodeActProviderOptions(SandboxBackend backend, string? modulePath)
    {
        this.Backend = backend;
        this.ModulePath = modulePath;
    }

    /// <summary>
    /// Creates options targeting the <see cref="SandboxBackend.Wasm"/> backend.
    /// </summary>
    /// <param name="modulePath">Path to the guest module (<c>.wasm</c> or <c>.aot</c> file).</param>
    public static HyperlightCodeActProviderOptions CreateForWasm(string modulePath)
        => new(SandboxBackend.Wasm, Throw.IfNullOrWhitespace(modulePath));

    /// <summary>
    /// Creates options targeting the <see cref="SandboxBackend.JavaScript"/> backend.
    /// </summary>
    public static HyperlightCodeActProviderOptions CreateForJavaScript()
        => new(SandboxBackend.JavaScript, modulePath: null);

    /// <summary>
    /// Gets the Hyperlight sandbox backend this options instance is configured for.
    /// </summary>
    public SandboxBackend Backend { get; }

    /// <summary>
    /// Gets the path to the guest module. Set when the options were created via
    /// <see cref="CreateForWasm(string)"/>; <see langword="null"/> otherwise.
    /// </summary>
    public string? ModulePath { get; }

    /// <summary>
    /// Gets or sets the guest heap size. Accepts human-readable strings such as
    /// <c>"50Mi"</c> or <c>"2Gi"</c>. When <see langword="null"/> the backend default is used.
    /// </summary>
    public string? HeapSize { get; set; }

    /// <summary>
    /// Gets or sets the guest stack size. Accepts human-readable strings such as
    /// <c>"35Mi"</c>. When <see langword="null"/> the backend default is used.
    /// </summary>
    public string? StackSize { get; set; }

    /// <summary>
    /// Gets or sets the initial set of provider-owned CodeAct tools made available
    /// inside the sandbox via <c>call_tool(...)</c>.
    /// </summary>
    public IEnumerable<AIFunction>? Tools { get; set; }

    /// <summary>
    /// Gets or sets the default approval mode for <c>execute_code</c>.
    /// Defaults to <see cref="CodeActApprovalMode.NeverRequire"/>.
    /// </summary>
    public CodeActApprovalMode ApprovalMode { get; set; } = CodeActApprovalMode.NeverRequire;

    /// <summary>
    /// Gets or sets an optional host directory exposed to the sandbox as its
    /// <c>/input</c> directory.
    /// </summary>
    public string? HostInputDirectory { get; set; }

    /// <summary>
    /// Gets or sets the initial set of file mount configurations.
    /// </summary>
    public IEnumerable<FileMount>? FileMounts { get; set; }

    /// <summary>
    /// Gets or sets the initial outbound network allow-list entries.
    /// </summary>
    public IEnumerable<AllowedDomain>? AllowedDomains { get; set; }
}
