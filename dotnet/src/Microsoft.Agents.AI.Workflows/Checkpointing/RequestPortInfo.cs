// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.AI.Workflows.Checkpointing;

/// <summary>
/// Information about an input port, including its input and output types.
/// </summary>
/// <param name="RequestType"></param>
/// <param name="ResponseType"></param>
/// <param name="PortId"></param>
public record class RequestPortInfo(TypeId RequestType, TypeId ResponseType, string PortId);
