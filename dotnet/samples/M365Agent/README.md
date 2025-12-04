# Microsoft Agent Framework agents with the M365 Agents SDK Weather Agent sample

This is a sample of a simple Weather Forecast Agent that is hosted on an Asp.Net core web service and is exposed via the M365 Agent SDK. This Agent is configured to accept a request asking for information about a weather forecast and respond to the caller with an Adaptive Card. This agent will handle multiple "turns" to get the required information from the user.

This Agent Sample is intended to introduce you the basics of integrating Agent Framework with the Microsoft 365 Agents SDK in order to use Agent Framework agents in various M365 services and applications. It can also be used as the base for a custom Agent that you choose to develop.

***Note:*** This sample requires JSON structured output from the model which works best from newer versions of the model such as gpt-4o-mini.

## Prerequisites

- [.NET 10.0 SDK or later](https://dotnet.microsoft.com/download)
- [devtunnel](https://learn.microsoft.com/azure/developer/dev-tunnels/get-started?tabs=windows)
- [Microsoft 365 Agents Toolkit](https://github.com/OfficeDev/microsoft-365-agents-toolkit)

- You will need an Azure OpenAI or OpenAI resource using `gpt-4o-mini`
 
- Configure OpenAI in appsettings

  ```json
  "AIServices": {
    "AzureOpenAI": {
      "DeploymentName": "", // This is the Deployment (as opposed to model) Name of the Azure OpenAI model
      "Endpoint": "", // This is the Endpoint of the Azure OpenAI resource
      "ApiKey": "" // This is the API Key of the Azure OpenAI resource. Optional, uses AzureCliCredential if not provided
    },
    "OpenAI": {
      "ModelId": "", // This is the Model ID of the OpenAI model
      "ApiKey": "" // This is your API Key for the OpenAI service
    },
    "UseAzureOpenAI": false // This is a flag to determine whether to use the Azure OpenAI or the OpenAI service
  }
  ```

## QuickStart using Agent Toolkit
1. If you haven't done so already, install the Agents Playground
 
   ```
   winget install agentsplayground
   ```
1. Start the sample application.
1. Start Agents Playground.  At a command prompt: `agentsplayground`
   - The tool will open a web browser showing the Microsoft 365 Agents Playground, ready to send messages to your agent. 
1. Interact with the Agent via the browser

## QuickStart using WebChat or Teams

- Overview of running and testing an Agent
  - Provision an Azure Bot in your Azure Subscription
  - Configure your Agent settings to use to desired authentication type
  - Running an instance of the Agent app (either locally or deployed to Azure)
  - Test in a client

1. Create an Azure Bot with one of these authentication types
   - [SingleTenant, Client Secret](https://learn.microsoft.com/en-us/microsoft-365/agents-sdk/azure-bot-create-single-secret)
   - [SingleTenant, Federated Credentials](https://learn.microsoft.com/en-us/microsoft-365/agents-sdk/azure-bot-create-federated-credentials) 
   - [User Assigned Managed Identity](https://learn.microsoft.com/en-us/microsoft-365/agents-sdk/azure-bot-create-managed-identity)
    
   > Be sure to follow the **Next Steps** at the end of these docs to configure your agent settings.

   > **IMPORTANT:** If you want to run your agent locally via devtunnels, the only support auth type is ClientSecret and Certificates

1. Running the Agent
   1. Running the Agent locally
      - Requires a tunneling tool to allow for local development and debugging should you wish to do local development whilst connected to a external client such as Microsoft Teams.
      - **For ClientSecret or Certificate authentication types only.**  Federated Credentials and Managed Identity will not work via a tunnel to a local agent and must be deployed to an App Service or container.
      
      1. Run `devtunnel`. Please follow [Create and host a dev tunnel](https://learn.microsoft.com/azure/developer/dev-tunnels/get-started?tabs=windows) and host the tunnel with anonymous user access command as shown below:

         ```bash
         devtunnel host -p 3978 --allow-anonymous
         ```

      1. On the Azure Bot, select **Settings**, then **Configuration**, and update the **Messaging endpoint** to `{tunnel-url}/api/messages`

      1. Start the Agent in Visual Studio

   1. Deploy Agent code to Azure
      1. VS Publish works well for this.  But any tools used to deploy a web application will also work.
      1. On the Azure Bot, select **Settings**, then **Configuration**, and update the **Messaging endpoint** to `https://{{appServiceDomain}}/api/messages`

## Testing this agent with WebChat

   1. Select **Test in WebChat** under **Settings** on the Azure Bot in the Azure Portal

## Testing this Agent in Teams or M365

1. Update the manifest.json
   - Edit the `manifest.json` contained in the `/appManifest` folder
     - Replace with your AppId (that was created above) *everywhere* you see the place holder string `<<AAD_APP_CLIENT_ID>>`
     - Replace `<<BOT_DOMAIN>>` with your Agent url.  For example, the tunnel host name.
   - Zip up the contents of the `/appManifest` folder to create a `manifest.zip`
     - `manifest.json`
     - `outline.png`
     - `color.png`

1. Your Azure Bot should have the **Microsoft Teams** channel added under **Channels**.

1. Navigate to the Microsoft Admin Portal (MAC). Under **Settings** and **Integrated Apps,** select **Upload Custom App**.

1. Select the `manifest.zip` created in the previous step. 

1. After a short period of time, the agent shows up in Microsoft Teams and Microsoft 365 Copilot.

## Enabling JWT token validation
1. By default, the AspNet token validation is disabled in order to support local debugging.
1. Enable by updating appsettings
   ```json
   "TokenValidation": {
     "Enabled": true,
     "Audiences": [
       "{{ClientId}}" // this is the Client ID used for the Azure Bot
     ],
     "TenantId": "{{TenantId}}"
   },
   ```

## Further reading

To learn more about using the M365 Agent SDK, see [Microsoft 365 Agents SDK](https://learn.microsoft.com/en-us/microsoft-365/agents-sdk/).
