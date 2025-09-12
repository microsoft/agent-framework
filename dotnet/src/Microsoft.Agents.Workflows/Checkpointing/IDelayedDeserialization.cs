// Copyright (c) Microsoft. All rights reserved.

using System;

namespace Microsoft.Agents.Workflows.Checkpointing;

internal interface IDelayedDeserialization
{
    TValue Deserialize<TValue>();

    object? Deserialize(Type targetType);
}
