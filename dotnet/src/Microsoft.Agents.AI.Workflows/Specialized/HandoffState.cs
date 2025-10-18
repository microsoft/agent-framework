// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Workflows.Specialized;

internal sealed record class HandoffState(
    TurnToken TurnToken,
    string? InvokedHandoff,
    List<ChatMessage> Messages);
