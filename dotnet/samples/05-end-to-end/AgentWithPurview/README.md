# Agent with Purview

This sample adds Microsoft Purview policy evaluation to an OpenAI-compatible chat client.

## What is required

The model endpoint and Purview authentication are separate:

- The model endpoint generates the response.
- Microsoft Graph Purview APIs evaluate the prompt and response against tenant policies.

Set the model configuration:

```powershell
# Azure OpenAI resource root (the sample appends /openai/v1 automatically):
$env:AZURE_OPENAI_ENDPOINT="https://your-resource.openai.azure.com/"
$env:AZURE_OPENAI_DEPLOYMENT_NAME="gpt-5.4-mini"

# A Foundry project OpenAI v1 endpoint also works:
# $env:AZURE_OPENAI_ENDPOINT="https://your-resource.services.ai.azure.com/api/projects/your-project/openai/v1/"
```

Create or reuse a Microsoft Entra public client application and set:

```powershell
$env:PURVIEW_CLIENT_APP_ID="<application-client-id>"
```

The app requires these delegated Microsoft Graph permissions with tenant administrator consent:

- `ProtectionScopes.Compute.All`
- `Content.Process.All`
- `ContentActivity.Write`

Configure a localhost redirect URI for the public client application so `InteractiveBrowserCredential`
can complete sign-in.

## Tenant configuration

A successful authentication only proves that the Graph permissions are configured. A real Purview block
also requires:

1. Microsoft Purview entitlement and consumptive billing.
2. The Entra app registered in **Purview > Settings > AI app and agent locations**.
3. A DLP or data collection policy targeting the app and signed-in user.
4. The policy enabled outside test-only mode.

## Run

```powershell
az login
dotnet run
```

The sample opens a browser for the delegated Purview sign-in, then prompts for text to send to the model.

For middleware options and policy behavior, see
[`Microsoft.Agents.AI.Purview`](../../../src/Microsoft.Agents.AI.Purview/README.md).
