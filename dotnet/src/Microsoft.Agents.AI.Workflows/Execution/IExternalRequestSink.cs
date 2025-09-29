// Copyright (c) Microsoft. All rights reserved.

using System.Threading.Tasks;

namespace Microsoft.Agents.AI.Workflows.Execution;

internal interface IExternalRequestSink
{
    ValueTask PostAsync(ExternalRequest request);
}
