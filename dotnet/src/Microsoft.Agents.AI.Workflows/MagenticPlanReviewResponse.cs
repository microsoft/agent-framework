// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Workflows;

/// <summary>
/// .
/// </summary>
/// <param name="Review"></param>
public record MagenticPlanReviewResponse(List<ChatMessage> Review)
{
    internal bool IsApproved => this.Review.Count == 0;
}
