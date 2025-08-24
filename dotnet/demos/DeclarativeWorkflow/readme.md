# Summary

This demo showcases the ability to parse a declarative Foundry Workflow file (YAML) to build a `Workflow<>`
be executed using the same pattern as any code-based workflow.

## Configuration

This demo requires configuration to access agents an [Azure Foundry Project](https://learn.microsoft.com/azure/ai-foundry).

We suggest using .NET [Secret Manager](https://learn.microsoft.com/en-us/aspnet/core/security/app-secrets) 
to avoid the risk of leaking secrets into the repository, branches and pull requests. 
You can also use environment variables if you prefer.

To set your secrets with .NET Secret Manager:

1. From the root of the respository, navigate the console to the project folder:

    ```
    cd dotnet/demos/DeclarativeWorkflow
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
    dotnet user-secrets set "AzureAI:Endpoint" "https://..."
    ```

5. Use [_Azure CLI_](https://learn.microsoft.com/cli/azure/authenticate-azure-cli) to authorize access to your Azure Foundry Project:

    ```
    az login
    az account get-access-token
    ```

## Execution

Run the demo from the console by specifying a path to a declarative (YAML) workflow file.  
The repository has example workflows available in the root [`/workflows`](../../../workflows) folder.

1. From the root of the respository, navigate the console to the project folder:

    ```
    cd dotnet/demos/DeclarativeWorkflow
    ```

2. Run the demo with a path to a workflow file:

    ```
    dotnet run ../../../workflows/HelloWorld.yaml
    ```
