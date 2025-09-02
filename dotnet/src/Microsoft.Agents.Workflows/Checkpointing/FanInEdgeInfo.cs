// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.Workflows.Checkpointing;

internal class FanInEdgeInfo(FanInEdgeData data) : EdgeInfo(Edge.Type.FanIn, data.Connection);
