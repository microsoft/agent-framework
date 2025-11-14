# Summary

This demo showcases the ability to parse a declarative Foundry Workflow file (YAML) to build a `Workflow<>`
be executed using the same pattern as any code-based workflow.

## Configuration

This demo requires configuration to access agents an [Azure Foundry Project](https://learn.microsoft.com/azure/ai-foundry).

#### Settings

We suggest using .NET [Secret Manager](https://learn.microsoft.com/en-us/aspnet/core/security/app-secrets) 
to avoid the risk of leaking secrets into the repository, branches and pull requests. 
You can also use environment variables if you prefer.

To set your secrets as an environment variable (PowerShell):

```pwsh
$env:FOUNDRY_PROJECT_ENDPOINT="https://..."
```

etc...


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
    dotnet user-secrets set "FOUNDRY_MODEL_DEPLOYMENT_NAME" "gpt-4.1"
    ```

6. Define setting that identifies your Bing Grounding connection:

    ```
    dotnet user-secrets set "FOUNDRY_CONNECTION_GROUNDING_TOOL" "mybinggrounding"
    ```

#### Authorization

Use [_Azure CLI_](https://learn.microsoft.com/cli/azure/authenticate-azure-cli) to authorize access to your Azure Foundry Project:

```
az login
az account get-access-token
```

#### Agents

The sample workflows rely on agents defined in your Azure Foundry Project.

To create agents, run the [`Create.ps1`](../../../../../workflow-samples/setup/) script.
This will create the agents used in the sample workflows in your Azure Foundry Project and format a script you can copy and use to configure your environment.

> Note: `Create.ps1` relies upon the `FOUNDRY_PROJECT_ENDPOINT`, `FOUNDRY_MODEL_DEPLOYMENT_NAME`, and `FOUNDRY_CONNECTION_GROUNDING_TOOL` settings.

## Execution

Run the demo from the console by specifying a path to a declarative (YAML) workflow file.  
The repository has example workflows available in the root [`/workflow-samples`](../../../../../workflow-samples) folder.

1. From the root of the repository, navigate the console to the project folder:

    ```sh
    cd dotnet/samples/GettingStarted/Workflows/Declarative/DeclarativeWorkflow
    ```

2. Run the demo referencing a sample workflow by name:

    ```sh
    dotnet run Marketing
    ```

3. Run the demo with a path to any workflow file:

    ```sh
    dotnet run c:/myworkflows/Marketing.yaml
    ```
