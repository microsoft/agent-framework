// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.Workflows.Checkpointing;

internal record class InputPortInfo(TypeId InputType, TypeId OutputType, string PortId);
