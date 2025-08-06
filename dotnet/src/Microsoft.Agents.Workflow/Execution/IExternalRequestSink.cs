// Copyright (c) Microsoft. All rights reserved.

using System.Threading.Tasks;
using Microsoft.Agents.Workflows.Core;

namespace Microsoft.Agents.Workflows.Execution;

internal interface IExternalRequestSink
{
    ValueTask PostAsync(ExternalRequest request);
}
