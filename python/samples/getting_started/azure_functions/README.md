These are common starting instructions for how to set up your environment for all the samples in this directory. 
These  samples are for illustrating the use of the Durable extensibility to Agent Framework running in Azure Functions. 

All of these samples are set up to run in Azure Functions. Azure Functions has a local called [CoreTools](https://learn.microsoft.com/azure/azure-functions/functions-run-local?tabs=windows%2Cpython%2Cv2&pivots=programming-language-python#install-the-azure-functions-core-tools) which we will set up to run these samples locally.

## Environment Setup

### 1. Install dependencies and create appropriate services

-Install [Azure Functions Core Tools 4.x](https://learn.microsoft.com/azure/azure-functions/functions-run-local?tabs=windows%2Cpython%2Cv2&pivots=programming-language-python#install-the-azure-functions-core-tools)
  
-Install [Azurite storage emulator](https://learn.microsoft.com/en-us/azure/storage/common/storage-install-azurite?toc=%2Fazure%2Fstorage%2Fblobs%2Ftoc.json&bc=%2Fazure%2Fstorage%2Fblobs%2Fbreadcrumb%2Ftoc.json&tabs=visual-studio%2Cblob-storage)

- Create an [Azure OpenAI](https://azure.microsoft.com/en-us/products/ai-foundry/models/openai)  resource. Note the Azure OpenAI endpoint, deployment name and the Key.

- Install a tool to execute HTTP calls for [example](https://marketplace.visualstudio.com/items?itemName=humao.rest-client)

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

## 3. Running the samples 

- [Start the Azurite emulator](https://learn.microsoft.com/en-us/azure/storage/common/storage-install-azurite?tabs=npm%2Cblob-storage#run-azurite)

- Inside each sample: 

    - Install Python dependencies – from this folder, run `pip install -r requirements.txt` (or the equivalent in your active virtual environment).
  
    - Copy `local.settings.json.template` to `local.settings.json`, then update `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_CHAT_DEPLOYMENT_NAME`, and `AZURE_OPENAI_API_KEY` so the Azure OpenAI SDK can authenticate; keep `TASKHUB_NAME` set to `default` unless you plan to change the durable task hub name.

    - [Start Azurite](https://learn.microsoft.com/en-us/azure/storage/common/storage-install-azurite?tabs=npm%2Cblob-storage#run-azurite) before launching the app (the sample uses `AzureWebJobsStorage=UseDevelopmentStorage=true`)


- Run the command: *func start* from the root of the sample

- Follow the specific instructions/requests for each sample
