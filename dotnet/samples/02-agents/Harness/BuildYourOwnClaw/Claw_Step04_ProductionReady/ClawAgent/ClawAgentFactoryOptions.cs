// Copyright (c) Microsoft. All rights reserved.

using Azure.Core;
using Microsoft.Agents.AI;

namespace ClawAgent;

/// <summary>
/// Options for building the production-ready claw agent.
/// </summary>
public sealed class ClawAgentFactoryOptions
{
    /// <summary>
    /// Gets or sets the Foundry project endpoint. Defaults to <c>FOUNDRY_PROJECT_ENDPOINT</c>.
    /// </summary>
    public string? ProjectEndpoint { get; set; }

    /// <summary>
    /// Gets or sets the Foundry model deployment name. Defaults to <c>AZURE_AI_MODEL_DEPLOYMENT_NAME</c> or <c>gpt-5.4</c>.
    /// </summary>
    public string? DeploymentName { get; set; }

    /// <summary>
    /// Gets or sets the token credential used for Foundry. Defaults to <see cref="Azure.Identity.DefaultAzureCredential" />.
    /// </summary>
    public TokenCredential? Credential { get; set; }

    /// <summary>
    /// Gets or sets the token credential used for Purview. When provided, Purview is enabled with
    /// this credential. Otherwise, <c>PURVIEW_CLIENT_APP_ID</c> enables local browser authentication.
    /// </summary>
    public TokenCredential? PurviewCredential { get; set; }

    /// <summary>
    /// Gets or sets an optional provider for the current Foundry hosted call ID. When supplied, the
    /// call ID is forwarded to the Toolbox MCP endpoint as <c>x-agent-foundry-call-id</c>.
    /// </summary>
    public Func<string?>? FoundryCallIdProvider { get; set; }

    /// <summary>
    /// Gets or sets the agent name exposed to hosting and telemetry.
    /// </summary>
    public string AgentName { get; set; } = "personal-finance-claw";

    /// <summary>
    /// Gets or sets the agent description exposed to hosting and telemetry.
    /// </summary>
    public string AgentDescription { get; set; } = "A production-ready personal finance claw with skills, shell, CodeAct, background agents, telemetry, and optional Purview governance.";

    /// <summary>
    /// Gets or sets the working directory containing portfolio data and trade confirmations.
    /// </summary>
    public string? WorkingDirectory { get; set; }

    /// <summary>
    /// Gets or sets the directory containing file-based skills.
    /// </summary>
    public string? SkillsDirectory { get; set; }

    /// <summary>
    /// Gets or sets a value indicating whether the agent can read and write files on the host.
    /// </summary>
    /// <remarks>
    /// Enabled by default for local hosts. Disable it on shared/hosted deployments where giving the
    /// model arbitrary read/write access to the container filesystem is a data-exfiltration and
    /// tampering risk. When you still need file access in a hosted environment, prefer supplying an
    /// external <see cref="FileStore"/> (for example, a blob-storage-backed store) rather than the
    /// container disk.
    /// </remarks>
    public bool EnableFileAccess { get; set; } = true;

    /// <summary>
    /// Gets or sets an optional custom <see cref="AgentFileStore"/> used for file access.
    /// </summary>
    /// <remarks>
    /// When <see langword="null"/> (and <see cref="EnableFileAccess"/> is <see langword="true"/>), a
    /// <see cref="FileSystemAgentFileStore"/> rooted at <see cref="WorkingDirectory"/> is used. Supply
    /// your own store to keep files off the local disk — for example, a store backed by Azure Blob
    /// Storage — which is the recommended approach for hosted deployments. Ignored when
    /// <see cref="EnableFileAccess"/> is <see langword="false"/>.
    /// </remarks>
    public AgentFileStore? FileStore { get; set; }

    /// <summary>
    /// Gets or sets a value indicating whether the agent can run shell commands on the host.
    /// </summary>
    /// <remarks>
    /// Enabled by default for local hosts. Disable it on shared/hosted deployments: arbitrary command
    /// execution inside the hosted container is a serious security risk (data exfiltration, persistence,
    /// tampering) even with a deny-list, and the local vault it operates on does not exist in the
    /// hosted environment.
    /// </remarks>
    public bool EnableShell { get; set; } = true;

    /// <summary>
    /// Gets or sets a value indicating whether the agent exposes a CodeAct code interpreter.
    /// </summary>
    /// <remarks>
    /// Enabled by default. When <see langword="true"/> and <see cref="CodeActProvider"/> is
    /// <see langword="null"/>, a Hyperlight-backed, VM-isolated provider is used — suitable for local
    /// hosts with a hypervisor (KVM) and FUSE. Foundry hosted containers do not expose those, so a
    /// hosted host should either supply a <see cref="CodeActProvider"/> that relies on the container as
    /// the sandbox (for example a <c>LocalCodeActProvider</c>) or set this to <see langword="false"/>.
    /// </remarks>
    public bool EnableCodeAct { get; set; } = true;

    /// <summary>
    /// Gets or sets an optional CodeAct context provider used when <see cref="EnableCodeAct"/> is
    /// <see langword="true"/>.
    /// </summary>
    /// <remarks>
    /// When <see langword="null"/> the factory creates a Hyperlight-backed provider. Supply your own
    /// (for example a <c>LocalCodeActProvider</c>) to run in an environment without a hypervisor, such
    /// as a Foundry hosted container. Ignored when <see cref="EnableCodeAct"/> is
    /// <see langword="false"/>. If the provider implements <see cref="IDisposable"/> it is
    /// disposed by the returned <see cref="ClawAgentBuild"/>.
    /// </remarks>
    public AIContextProvider? CodeActProvider { get; set; }

    /// <summary>
    /// Gets or sets additional tool auto-approval rules for this host.
    /// </summary>
    /// <remarks>
    /// The factory always includes the read-only file-access rule. Use additional rules only in
    /// trusted hosts, such as an evaluation runner that executes bundled skill scripts.
    /// </remarks>
    public IEnumerable<Func<ToolAutoApprovalRuleContext, ValueTask<bool>>>? AdditionalToolAutoApprovalRules { get; set; }

    /// <summary>
    /// Gets or sets the optional log callback used for setup notes.
    /// </summary>
    public Action<string>? Log { get; set; }
}
