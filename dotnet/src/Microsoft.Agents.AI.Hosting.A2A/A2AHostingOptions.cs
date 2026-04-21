// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics.CodeAnalysis;
using A2A;
using Microsoft.Shared.DiagnosticIds;

namespace Microsoft.Agents.AI.Hosting.A2A;

/// <summary>
/// Options for configuring A2A endpoint hosting behavior.
/// </summary>
[Experimental(DiagnosticIds.Experiments.AIResponseContinuations)]
public sealed class A2AHostingOptions
{
    /// <summary>
    /// Gets or sets the A2A protocol binding(s) to expose.
    /// </summary>
    /// <remarks>
    /// When <see langword="null"/>, defaults to <see cref="A2AProtocolBinding.HttpJson"/>.
    /// Use the bitwise OR operator to enable multiple bindings
    /// (e.g., <c>A2AProtocolBinding.HttpJson | A2AProtocolBinding.JsonRpc</c>).
    /// </remarks>
    public A2AProtocolBinding? ProtocolBindings { get; set; }

    /// <summary>
    /// Gets or sets the agent run mode that controls how the agent responds to A2A requests.
    /// </summary>
    /// <remarks>
    /// When <see langword="null"/>, defaults to <see cref="AgentRunMode.DisallowBackground"/>.
    /// </remarks>
    public AgentRunMode? AgentRunMode { get; set; }

    /// <summary>
    /// Gets or sets the A2A server options used to configure the underlying <see cref="A2AServer"/>.
    /// </summary>
    /// <remarks>
    /// When <see langword="null"/>, no custom server options are applied.
    /// </remarks>
    public A2AServerOptions? ServerOptions { get; set; }
}
