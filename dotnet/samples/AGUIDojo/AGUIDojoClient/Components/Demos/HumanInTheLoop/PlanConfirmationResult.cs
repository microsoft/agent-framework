// Copyright (c) Microsoft. All rights reserved.

namespace AGUIDojoClient.Components.Demos.HumanInTheLoop;

/// <summary>
/// Result of user's plan confirmation decision.
/// </summary>
public class PlanConfirmationResult
{
    public bool Confirmed { get; set; }
    public List<int> SelectedStepIndices { get; set; } = [];
}
