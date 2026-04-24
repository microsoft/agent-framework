These are common instructions for setting up your environment for every sample in this directory.
These samples illustrate the Durable extensibility for Agent Framework running in Azure Functions.

All of these samples are set up to run in Azure Functions. Azure Functions has a local development tool called [CoreTools](https://learn.microsoft.com/azure/azure-functions/functions-run-local?tabs=windows%2Cpython%2Cv2&pivots=programming-language-python#install-the-azure-functions-core-tools) which we will set up to run these samples locally.

## Environment Setup

### 1. Install dependencies and create appropriate services

- Install [Azure Functions Core Tools 4.x](https://learn.microsoft.com/azure/azure-functions/functions-run-local?tabs=windows%2Cpython%2Cv2&pivots=programming-language-python#install-the-azure-functions-core-tools)

- Install [Azurite storage emulator](https://learn.microsoft.com/en-us/azure/storage/common/storage-install-azurite?toc=%2Fazure%2Fstorage%2Fblobs%2Ftoc.json&bc=%2Fazure%2Fstorage%2Fblobs%2Fbreadcrumb%2Ftoc.json&tabs=visual-studio%2Cblob-storage)

- Create an [Azure AI Foundry project](https://learn.microsoft.com/azure/ai-foundry/) with an OpenAI model deployment. Note the Foundry project endpoint and deployment name, and ensure you can authenticate with `AzureCliCredential`.

- Install a tool to execute HTTP calls, for example the [REST Client extension](https://marketplace.visualstudio.com/items?itemName=humao.rest-client)

- [Optionally] Create an [Azure Function Python app](https://learn.microsoft.com/en-us/azure/azure-functions/functions-create-function-app-portal?tabs=core-tools&pivots=flex-consumption-plan) to later deploy your app to Azure if you so desire.

### 2. Create and activate a virtual environment

**Windows (PowerShell):**
```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

**Linux/macOS:**
```bash
python -m venv .venv
source .venv/bin/activate
```

### 3. Running the samples

- [Start the Azurite emulator](https://learn.microsoft.com/en-us/azure/storage/common/storage-install-azurite?tabs=npm%2Cblob-storage#run-azurite)

- Inside each sample:

    - Install Python dependencies – from the sample directory, run `pip install -r requirements.txt` (or the equivalent in your active virtual environment).

    - Copy `local.settings.json.template` to `local.settings.json`, then update `FOUNDRY_PROJECT_ENDPOINT` and `FOUNDRY_MODEL`. The samples use `AzureCliCredential`, so ensure you're logged in via `az login`.
        - Keep `TASKHUB_NAME` set to `default` unless you plan to change the durable task hub name.

    - Run the command `func start` from the root of the sample

    - Follow each sample's README for scenario-specific steps, and use its `demo.http` file (or provided curl examples) to trigger the hosted HTTP endpoints.
