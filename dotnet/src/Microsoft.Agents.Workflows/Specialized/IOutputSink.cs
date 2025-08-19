// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.Workflows.Specialized;

internal interface IOutputSink<TResult>
{
    TResult? Result { get; }
}
