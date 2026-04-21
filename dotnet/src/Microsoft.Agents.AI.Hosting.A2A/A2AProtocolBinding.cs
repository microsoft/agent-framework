// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Diagnostics.CodeAnalysis;
using Microsoft.Shared.DiagnosticIds;

namespace Microsoft.Agents.AI.Hosting.A2A;

/// <summary>
/// Specifies which A2A protocol binding(s) to expose when mapping A2A endpoints.
/// </summary>
/// <remarks>
/// This is a flags enum. Combine values using the bitwise OR operator to enable multiple bindings
/// (e.g., <c>A2AProtocolBinding.HttpJson | A2AProtocolBinding.JsonRpc</c>).
/// </remarks>
[Flags]
[Experimental(DiagnosticIds.Experiments.AIResponseContinuations)]
public enum A2AProtocolBinding
{
    /// <summary>
    /// Expose the agent via the HTTP+JSON/REST protocol binding.
    /// </summary>
    HttpJson = 1,

    /// <summary>
    /// Expose the agent via the JSON-RPC protocol binding.
    /// </summary>
    JsonRpc = 2,
}
