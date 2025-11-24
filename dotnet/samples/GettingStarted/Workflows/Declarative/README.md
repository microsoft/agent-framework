# Summary

These samples showcases the ability to parse a declarative Foundry Workflow file (YAML) 
to build a `Workflow` that may be executed using the same pattern as any code-based workflow.

## Configuration

These samples must be configured to create and use agents your 
[Azure Foundry Project](https://learn.microsoft.com/azure/ai-foundry).

### Settings

We suggest using .NET [Secret Manager](https://learn.microsoft.com/en-us/aspnet/core/security/app-secrets) 
to avoid the risk of leaking secrets into the repository, branches and pull requests. 
You can also use environment variables if you prefer.

The configuraton required by the samples is:

|Setting Name| Description|
|:--|:--|
|FOUNDRY_PROJECT_ENDPOINT| The endpoint URL of your Azure Foundry Project.|
|FOUNDRY_MODEL_DEPLOYMENT_NAME| The name of the model deployment to use
|FOUNDRY_CONNECTION_GROUNDING_TOOL| The name of the Bing Grounding connection configured in your Azure Foundry Project.|

To set your secrets with .NET Secret Manager:

1. From the root of the repository, navigate the console to the project folder:

    ```
    cd dotnet/samples/GettingStarted/Workflows/Declarative/ExecuteWorkflow
    ```

2. Examine existing secret definitions:

    ```
    dotnet user-secrets list
    ```

3. If needed, perform first time initialization:

    ```
    dotnet user-secrets init
    ```

4. Define setting that identifies your Azure Foundry Project (endpoint):

    ```
    dotnet user-secrets set "FOUNDRY_PROJECT_ENDPOINT" "https://..."
    ```

5. Define setting that identifies your Azure Foundry Model Deployment (endpoint):

    ```
    dotnet user-secrets set "FOUNDRY_MODEL_DEPLOYMENT_NAME" "gpt-5"
    ```

6. Define setting that identifies your Bing Grounding connection:

    ```
    dotnet user-secrets set "FOUNDRY_CONNECTION_GROUNDING_TOOL" "mybinggrounding"
    ```

You may alternatively set your secrets as an environment variable (PowerShell):

```pwsh
$env:FOUNDRY_PROJECT_ENDPOINT="https://..."
$env:FOUNDRY_MODEL_DEPLOYMENT_NAME="gpt-5"
$env:FOUNDRY_CONNECTION_GROUNDING_TOOL="mybinggrounding"
```

### Authorization

Use [_Azure CLI_](https://learn.microsoft.com/cli/azure/authenticate-azure-cli) to authorize access to your Azure Foundry Project:

```
az login
az account get-access-token
```

## Execution

The samples may be executed within _Visual Studio_ or _VS Code_.

To run the sampes from the command line:

1. From the root of the repository, navigate the console to the project folder:

    ```sh
    cd dotnet/samples/GettingStarted/Workflows/Declarative/Marketing
    dotnet run Marketing
    ```

2. Run the demo and optionally provided input:

    ```sh
    dotnet run "An eco-friendly stainless steel water bottle that keeps drinks cold for 24 hours."
    dotnet run c:/myworkflows/Marketing.yaml
    ```
   >  The sample will allow for interactive input in the absence of an input argument.