// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.AI;

/// <summary>
/// Configuration options for <see cref="AgentSkillsProvider"/>.
/// </summary>
public sealed class AgentSkillsProviderOptions
{
    /// <summary>
    /// Gets or sets a custom system prompt template for advertising skills.
    /// The template must contain <c>{skills}</c> as the placeholder for the generated skills list.
    /// When <see langword="null"/>, a default template is used.
    /// </summary>
    public string? SkillsInstructionPrompt { get; set; }

    /// <summary>
    /// Gets or sets a value indicating whether detailed exception information is included
    /// in the error message returned to the model when a script execution fails.
    /// </summary>
    /// <remarks>
    /// When <see langword="false"/> (the default), exceptions propagate to the caller, allowing
    /// <see cref="Extensions.AI.FunctionInvokingChatClient"/> to apply its own
    /// <c>IncludeDetailedErrors</c> policy — which achieves the same effect without requiring
    /// this property to be set. When <see langword="true"/>, the exception message is appended
    /// to the error string returned directly to the model, enabling it to retry with different
    /// arguments. However, this may disclose raw exception details to the model. Exercise
    /// particular caution when enabling this for skills whose scripts originate from untrusted
    /// or third-party sources: a maliciously crafted script could throw an exception whose
    /// message embeds a prompt-injection payload, which would then be fed back to the model.
    /// Only enable this when the skills and their scripts come from a trusted source.
    /// </remarks>
    public bool IncludeDetailedErrors { get; set; }

    /// <summary>
    /// Gets or sets a value indicating whether approval is disabled for the <see cref="AgentSkillsProvider.LoadSkillToolName"/> tool.
    /// </summary>
    /// <remarks>
    /// When <see langword="false"/> (the default), the tool requires approval before invocation.
    /// When <see langword="true"/>, the tool can be invoked without approval.
    /// If any other tool in the same response still requires approval, set
    /// <see cref="ChatClientAgentOptions.EnableNonApprovalRequiredFunctionBypassing"/> to <see langword="true"/>
    /// so this tool is not surfaced as an approval request.
    /// When approval is required, auto-approval rules (e.g. <see cref="AgentSkillsProvider.ReadOnlyToolsAutoApprovalRule"/>
    /// or <see cref="AgentSkillsProvider.AllToolsAutoApprovalRule"/>) can be used to automatically approve calls.
    /// </remarks>
    public bool DisableLoadSkillApproval { get; set; }

    /// <summary>
    /// Gets or sets a value indicating whether approval is disabled for the <see cref="AgentSkillsProvider.ReadSkillResourceToolName"/> tool.
    /// </summary>
    /// <remarks>
    /// When <see langword="false"/> (the default), the tool requires approval before invocation.
    /// When <see langword="true"/>, the tool can be invoked without approval.
    /// If any other tool in the same response still requires approval, set
    /// <see cref="ChatClientAgentOptions.EnableNonApprovalRequiredFunctionBypassing"/> to <see langword="true"/>
    /// so this tool is not surfaced as an approval request.
    /// When approval is required, auto-approval rules (e.g. <see cref="AgentSkillsProvider.ReadOnlyToolsAutoApprovalRule"/>
    /// or <see cref="AgentSkillsProvider.AllToolsAutoApprovalRule"/>) can be used to automatically approve calls.
    /// </remarks>
    public bool DisableReadSkillResourceApproval { get; set; }

    /// <summary>
    /// Gets or sets a value indicating whether approval is disabled for the <see cref="AgentSkillsProvider.RunSkillScriptToolName"/> tool.
    /// </summary>
    /// <remarks>
    /// When <see langword="false"/> (the default), the tool requires approval before invocation.
    /// When <see langword="true"/>, the tool can be invoked without approval.
    /// If any other tool in the same response still requires approval, set
    /// <see cref="ChatClientAgentOptions.EnableNonApprovalRequiredFunctionBypassing"/> to <see langword="true"/>
    /// so this tool is not surfaced as an approval request.
    /// When approval is required, auto-approval rules (e.g. <see cref="AgentSkillsProvider.ReadOnlyToolsAutoApprovalRule"/>
    /// or <see cref="AgentSkillsProvider.AllToolsAutoApprovalRule"/>) can be used to automatically approve calls.
    /// </remarks>
    public bool DisableRunSkillScriptApproval { get; set; }
}
