// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Workflows;

/// <summary>
/// Review feedback for a proposed plan, including any revisions if the plan is not approved as-is. An
/// empty list of review messages indicates approval of the proposed plan without any revisions.
/// </summary>
/// <param name="Review">
/// Review feedback for a generated plan. Empty if the plan is approved as-is and changes are requested.
/// </param>
public record MagenticPlanReviewResponse(List<ChatMessage> Review)
{
    internal bool IsApproved => this.Review.Count == 0;
}
