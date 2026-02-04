These are common instructions for setting up your environment for every sample in this directory.
These samples illustrate the Durable extensibility for Agent Framework running in Azure Functions.

All of these samples are set up to run in Azure Functions. Azure Functions has a local development tool called [CoreTools](https://learn.microsoft.com/azure/azure-functions/functions-run-local?tabs=windows%2Cpython%2Cv2&pivots=programming-language-python#install-the-azure-functions-core-tools) which we will set up to run these samples locally.

## Environment Setup

### 1. Install dependencies and create appropriate services

- Install [Azure Functions Core Tools 4.x](https://learn.microsoft.com/azure/azure-functions/functions-run-local?tabs=windows%2Cpython%2Cv2&pivots=programming-language-python#install-the-azure-functions-core-tools)
  
- Install [Azurite storage emulator](https://learn.microsoft.com/en-us/azure/storage/common/storage-install-azurite?toc=%2Fazure%2Fstorage%2Fblobs%2Ftoc.json&bc=%2Fazure%2Fstorage%2Fblobs%2Fbreadcrumb%2Ftoc.json&tabs=visual-studio%2Cblob-storage)

- Create an [Azure OpenAI](https://azure.microsoft.com/en-us/products/ai-foundry/models/openai) resource. Note the Azure OpenAI endpoint, deployment name, and the key (or ensure you can authenticate with `AzureCliCredential`).

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
  
    - Copy `local.settings.json.template` to `local.settings.json`, then update `AZURE_OPENAI_ENDPOINT` and `AZURE_OPENAI_CHAT_DEPLOYMENT_NAME` for Azure OpenAI authentication. The samples use `AzureCliCredential` by default, so ensure you're logged in via `az login`. 
        - Alternatively, you can use API key authentication by setting `AZURE_OPENAI_API_KEY` and updating the code to use `AzureOpenAIChatClient()` without the credential parameter.
        - Keep `TASKHUB_NAME` set to `default` unless you plan to change the durable task hub name.

    - Run the command `func start` from the root of the sample

    - Follow each sample's README for scenario-specific steps, and use its `demo.http` file (or provided curl examples) to trigger the hosted HTTP endpoints.
