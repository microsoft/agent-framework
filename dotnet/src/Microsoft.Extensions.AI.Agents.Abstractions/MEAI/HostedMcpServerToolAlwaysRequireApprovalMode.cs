// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics;

namespace Microsoft.Extensions.AI;

/// <summary>
/// Indicates that approval is always required for tool calls to a hosted MCP server.
/// </summary>
/// <remarks>
/// Use <see cref="HostedMcpServerToolApprovalMode.AlwaysRequire"/> to get an instance of <see cref="HostedMcpServerToolAlwaysRequireApprovalMode"/>.
/// </remarks>
[DebuggerDisplay(nameof(AlwaysRequire))]
public sealed class HostedMcpServerToolAlwaysRequireApprovalMode : HostedMcpServerToolApprovalMode;
