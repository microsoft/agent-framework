// Copyright (c) Microsoft. All rights reserved.

// Hosts the claw as a Foundry Hosted Agent (Responses API).
//
// Observability requires no extra wiring here: AddFoundryResponses automatically wraps the agent
// with OpenTelemetryAgent, and the Foundry hosting runtime (Azure.AI.AgentServer.Core's
// AddAgentHostTelemetry) registers the OTLP exporter pipeline. In the hosted environment Foundry
// injects APPLICATIONINSIGHTS_CONNECTION_STRING automatically, so traces, metrics and logs flow to
// Application Insights with no exporter configuration. To capture prompt/response content in traces,
// set OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT=true (off by default).
//
// File access and shell are DISABLED on the hosted agent. Granting the model arbitrary read/write
// access to the container filesystem, or letting it run shell commands, is a serious security risk in
// a shared hosted environment (data exfiltration, tampering, persistence) — and the local
// confirmations vault the shell operates on does not exist here. If you genuinely need file access
// when hosted, supply an external AgentFileStore (for example, one backed by Azure Blob Storage) via
// ClawAgentFactoryOptions.FileStore instead of using the container disk.
//
// CodeAct uses LocalCodeAct here, NOT the Hyperlight provider the local hosts use. Hyperlight runs
// guest code in a VM-isolated micro-sandbox that needs a hypervisor (KVM) and FUSE — neither of which
// an unprivileged Foundry hosted container exposes (attempting it fails at startup while configuring
// `fuse`, so the app never reports ready). LocalCodeAct instead runs the generated Python in a child
// process and relies on the hosted container itself as the isolation boundary, which is exactly the
// pattern the canonical Hosted-LocalCodeAct sample uses. SECURITY: LocalCodeAct is not itself a
// sandbox — only deploy it to an externally sandboxed environment such as a Foundry hosted-agent
// container.

using Azure.Core;
using Azure.Identity;
using ClawAgent;
using DotNetEnv;
using Hosted_Shared_Contributor_Setup;
using Microsoft.Agents.AI.Foundry.Hosting;
using Microsoft.Agents.AI.LocalCodeAct;

Env.TraversePath().Load();

var builder = WebApplication.CreateBuilder(args);
var httpContextAccessor = new HttpContextAccessor();
builder.Services.AddSingleton<IHttpContextAccessor>(httpContextAccessor);

var projectEndpoint = Environment.GetEnvironmentVariable("FOUNDRY_PROJECT_ENDPOINT")
    ?? throw new InvalidOperationException("FOUNDRY_PROJECT_ENDPOINT is not set.");
var deploymentName = Environment.GetEnvironmentVariable("AZURE_AI_MODEL_DEPLOYMENT_NAME") ?? "gpt-5.4";
var pythonExecutable = Environment.GetEnvironmentVariable("LOCAL_CODEACT_PYTHON") ?? "python3";
var purviewClientAppId = Environment.GetEnvironmentVariable("PURVIEW_CLIENT_APP_ID");

// WARNING: DefaultAzureCredential is convenient for development but requires careful consideration in
// production. Prefer a specific credential (e.g. ManagedIdentityCredential) when hosted. Here we chain
// a temporary dev token (for local Docker debugging) ahead of DefaultAzureCredential (for local
// dotnet run / managed identity when hosted).
TokenCredential credential = new ChainedTokenCredential(
    new DevTemporaryTokenCredential(),
    new DefaultAzureCredential());

await using ClawAgentBuild build = await ClawAgentFactory.CreateAsync(new ClawAgentFactoryOptions
{
    ProjectEndpoint = projectEndpoint,
    DeploymentName = deploymentName,
    Credential = credential,
    AgentDescription = "A production-ready personal finance claw with skills, CodeAct, background agents, telemetry, and optional Purview governance.",
    PurviewCredential = string.IsNullOrWhiteSpace(purviewClientAppId) ? null : credential,
    FoundryCallIdProvider = () =>
    {
        HttpContext? context = httpContextAccessor.HttpContext;
        return context is null ? null : context.Request.Headers["x-agent-foundry-call-id"].ToString();
    },

    // Disable filesystem and shell access on the hosted container (see risk note above).
    EnableFileAccess = false,
    EnableShell = false,

    // Use LocalCodeAct instead of the default Hyperlight provider: the hosted container has no
    // hypervisor/FUSE for Hyperlight, and acts as the sandbox for the child Python process itself.
    CodeActProvider = new LocalCodeActProvider(pythonExecutable),

    Log = Console.WriteLine,
});

// AddFoundryResponses wires up the Responses API host for the agent and auto-applies OpenTelemetry.
builder.Services.AddFoundryResponses(build.Agent);

var app = builder.Build();

// Map the hosted-agent endpoint that live Foundry calls.
app.MapFoundryResponses();

// Contributor-only: map the per-agent OpenAI route shape for local debugging. Not used in production.
app.MapDevTemporaryLocalAgentEndpoint();

app.Run();
