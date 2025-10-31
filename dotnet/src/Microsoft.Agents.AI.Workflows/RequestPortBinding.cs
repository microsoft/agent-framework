// Copyright (c) Microsoft. All rights reserved.

using System.Threading.Tasks;
using Microsoft.Agents.AI.Workflows.Specialized;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.Workflows;

/// <summary>
/// Represents the registration details for a request port, including configuration for allowing wrapped requests.
/// </summary>
/// <param name="Port">The request port.</param>
/// <param name="AllowWrapped">true to allow wrapped requests to be handled by the port; otherwise, false.
/// The default is true.</param>
public record RequestPortBinding(RequestPort Port, bool AllowWrapped = true)
    : ExecutorBinding(Throw.IfNull(Port).Id,
                           (_) => new ValueTask<Executor>(new RequestInfoExecutor(Port, AllowWrapped)),
                           typeof(RequestInfoExecutor),
                           Port)
{
    /// <inheritdoc/>
    public override bool IsSharedInstance => false;

    /// <inheritdoc/>
    public override bool SupportsConcurrentSharedExecution => true;

    /// <inheritdoc/>
    public override bool SupportsResetting => false;
}
