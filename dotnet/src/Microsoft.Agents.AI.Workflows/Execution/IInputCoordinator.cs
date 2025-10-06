// Copyright (c) Microsoft. All rights reserved.

using System.Threading;
using System.Threading.Tasks;

namespace Microsoft.Agents.AI.Workflows.Execution;

internal interface IInputCoordinator
{
    ValueTask<bool> WaitForNextInputAsync(CancellationToken cancellation = default);
}
