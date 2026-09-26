# Hosted Harness Scaling Capabilities

This sample hosts the finance harness from `dotnet/samples/02-agents/Harness/BuildYourOwnClaw/Claw_Step03_ScalingCapabilities`. Its existing stock tools, simulated trade approval, file skills and scripts, optional toolbox skills, confined shell, background research agent, and demo files are linked from that console example. The `HostedHarnessScalingCapabilities` project uses local framework source and does not set `AllowStoredOutputEnabled`; the hosted platform records the turn while the model service receives `store=false`.

It shares the research sample's `StatelessWebSearchChatClient`: hosted search stays available to the main harness and its background agent, but the raw search result is not replayed into later stateless model requests. The original result remains in the session history.

## Run locally

1. Set `FOUNDRY_PROJECT_ENDPOINT` and `AZURE_AI_MODEL_DEPLOYMENT_NAME` for an existing Foundry model deployment, then sign in with `az login`. Copy `.env.example` to `.env` if preferred.
2. From this directory, run `dotnet run --tl:off`. Call `POST http://localhost:8088/responses` with model `hosted-harness-scaling-capabilities`. Ask about `portfolio.csv` or a stock price, then send another turn with the same conversation ID.
3. Ask for a simulated trade or to reorganize the confirmations. The shell, trade and skill-script functions require explicit approval. Read-only files and skill loading are auto-approved. To resume, send the returned `mcp_approval_request.id` in an `mcp_approval_response` with the same conversation and hosted session. `azd ai agent invoke -f` sends a text message rather than a structured Responses body; use authenticated `az rest --resource https://ai.azure.com` for approvals.

Foundry's application directory is read-only. The sample seeds only missing files into the per-session writable home, keeping previously edited portfolio files, reports and confirmations. The shell is confined to the confirmations folder; its deny-list is **not** a security boundary. Run the image only in the externally isolated hosted container.

The working folder and file memory rely on Foundry's session sandbox: by default each caller gets their own session with a private `$HOME` (see [Isolate hosted agent sessions per user](https://learn.microsoft.com/azure/foundry/agents/how-to/isolate-sessions-per-user)). If you [place several users in one session](https://learn.microsoft.com/azure/foundry/agents/how-to/multiplex-session-users), partition both stores per user yourself.

`ENABLE_HYPERLIGHT_CODEACT=true` adds CodeAct where hardware virtualization is available. It is off by default because hosted containers typically do not provide nested virtualization; requesting it on an unsupported host fails explicitly. Optional toolbox skills use `TOOLBOX_MCP_SERVER_URL`. File skill scripts require Python 3 (included in the container image).

## Container build from this checkout

The source, skills and demonstration data link to other MAF sample directories. Publish from the complete checkout and build the runtime image, not from an isolated upload of this directory:

```powershell
dotnet publish HostedHarnessScalingCapabilities.csproj -c Release -f net10.0 -r linux-musl-x64 --self-contained false -o out --tl:off
docker build -t hosted-harness-scaling .
```

The image includes the local framework fix. Rebuild after changing the framework; an older published package will still reject the local history marker.

For deployment to an existing Foundry project, follow the [persistent `azd` container workflow](../Hosted-Harness-Research/README.md#deploy-with-an-existing-foundry-project) with this project's publish output, bundle directory `src\hosted-harness-scaling`, and agent name `maf-harness-scaling`. A hosted validation on the updated agent version confirmed the stock tool, multi-turn history, skill loading, a Python risk-scoring script **only after explicit approval**, and a confined read-only shell command **only after explicit approval**. Hyperlight CodeAct was not enabled on the hosted container because nested virtualization was unavailable.
