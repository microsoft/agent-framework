// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using HyperlightSandbox.Api;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Hyperlight;

/// <summary>
/// Configuration options for <see cref="HyperlightCodeActProvider"/> and
/// <see cref="HyperlightExecuteCodeFunction"/>.
/// </summary>
public sealed class HyperlightCodeActProviderOptions
{
    /// <summary>
    /// Gets or sets the Hyperlight sandbox backend to use.
    /// Defaults to <see cref="SandboxBackend.Wasm"/>.
    /// </summary>
    public SandboxBackend Backend { get; set; } = SandboxBackend.Wasm;

    /// <summary>
    /// Gets or sets the path to the guest module (<c>.wasm</c> or <c>.aot</c> file).
    /// Required for the <see cref="SandboxBackend.Wasm"/> backend; not needed for
    /// <see cref="SandboxBackend.JavaScript"/>.
    /// </summary>
    public string? ModulePath { get; set; }

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
    /// Gets or sets an optional workspace root directory on the host.
    /// When set, it is exposed as the sandbox's <c>/input</c> directory.
    /// </summary>
    public string? WorkspaceRoot { get; set; }

    /// <summary>
    /// Gets or sets the initial set of file mount configurations.
    /// </summary>
    public IEnumerable<FileMount>? FileMounts { get; set; }

    /// <summary>
    /// Gets or sets the initial outbound network allow-list entries.
    /// </summary>
    public IEnumerable<AllowedDomain>? AllowedDomains { get; set; }
}
