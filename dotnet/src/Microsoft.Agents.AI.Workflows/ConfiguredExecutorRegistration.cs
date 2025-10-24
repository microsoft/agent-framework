// Copyright (c) Microsoft. All rights reserved.

using System;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.Workflows;

// TODO: Unwrap the Configured object, just like for WorkflowRegistration
internal record ConfiguredExecutorRegistration(Configured<Executor> ConfiguredExecutor, Type ExecutorType)
    : ExecutorRegistration(Throw.IfNull(ConfiguredExecutor).Id,
                           ConfiguredExecutor.BoundFactoryAsync,
                           ExecutorType,
                           ConfiguredExecutor.Raw)
{
    /// <inheritdoc/>
    public override bool SupportsConcurrentSharedExecution => true;

    /// <inheritdoc/>
    public override bool SupportsResetting => false;
}
