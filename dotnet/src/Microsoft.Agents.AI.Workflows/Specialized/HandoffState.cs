// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Workflows.Specialized;

internal sealed record class HandOffState(
    TurnToken TurnToken,
    string? InvokedHandOff,
    List<ChatMessage> Messages);
