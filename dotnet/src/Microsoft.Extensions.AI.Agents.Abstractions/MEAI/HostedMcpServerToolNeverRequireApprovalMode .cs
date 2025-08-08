// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics;

namespace Microsoft.Extensions.AI;

/// <summary>
/// Indicates that approval is never required for tool calls to a hosted MCP server.
/// </summary>
/// <remarks>
/// Use <see cref="HostedMcpServerToolApprovalMode.NeverRequire"/> to get an instance of <see cref="HostedMcpServerToolNeverRequireApprovalMode"/>.
/// </remarks>
[DebuggerDisplay(nameof(NeverRequire))]
public sealed class HostedMcpServerToolNeverRequireApprovalMode : HostedMcpServerToolApprovalMode;
