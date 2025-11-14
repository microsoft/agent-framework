# Hosted Agents with Hosted MCP Demo

This demo showcases an agent that has access to a MCP tool that can talk to the Microsoft Learn documentation platform, hosted as an agent endpoint running locally in a Docker container.

## What the Project Does

This project demonstrates how to:

- Create an agent with a hosted MCP tool using the Agent Framework
- Host the agent as an agent endpoint running in a Docker container

## Prerequisites

- OpenAI API access and credentials
- Required environment variables (see Configuration section)

## Configuration

Follow the `.env.example` file to set up the necessary environment variables for OpenAI.

## Docker Deployment

Build and run using Docker:

```bash
# Build the Docker image
docker build -t hosted-agent-mcp .

# Run the container
docker run -p 8088:8088 hosted-agent-mcp
```

> If you update the environment variables in the `.env` file or change the code or the dockerfile, make sure to rebuild the Docker image to apply the changes.

## Testing the Agent

Once the agent is running, you can test it by sending queries that contain the trigger keywords. For example:

```bash
curl -sS -H "Content-Type: application/json" -X POST http://localhost:8088/responses -d '{"input": "How to create an Azure storage account using az cli?","stream":false}'
```

Expected response:

```bash
{"object":"response","metadata":{},"agent":null,"conversation":{"id":"conv_6Y7osWAQ1ASyUZ7Ze0LL6dgPubmQv52jHb7G9QDqpV5yakc3ay"},"type":"message","role":"assistant","temperature":1.0,"top_p":1.0,"user":"","id":"resp_Vfd6mdmnmTZ2RNirwfldfqldWLhaxD6fO2UkXsVUg1jYJgftL9","created_at":1763075575,"output":[{"id":"msg_6Y7osWAQ1ASyUZ7Ze0PwiK2V4Bb7NOPaaEpQoBvFRZ5h6OfW4u","type":"message","status":"completed","role":"assistant","content":[{"type":"output_text","text":"To create an Azure Storage account using the Azure CLI, you'll need to follow these steps:\n\n1. **Install Azure CLI**: Make sure the Azure CLI is installed on your machine. You can download it from [here](https://docs.microsoft.com/en-us/cli/azure/install-azure-cli).\n\n2. **Log in to Azure**: Open your terminal or command prompt and use the following command to log in to your Azure account:\n\n    ```bash\n    az login\n    ```\n\n   This command will open a web browser where you can log in with your Azure account credentials. If you're using a service principal, you would use `az login --service-principal ...` with the appropriate parameters.\n\n3. **Select the Subscription**: If you have multiple Azure subscriptions, set the default subscription that you want to use:\n\n    ```bash\n    az account set --subscription \"Your Subscription Name\"\n    ```\n\n4. **Create a Resource Group**: If you don’t already have a resource group, create one using:\n\n    ```bash\n    az group create --name myResourceGroup --location eastus\n    ```\n\n   Replace `myResourceGroup` and `eastus` with your desired resource group name and location.\n\n5. **Create the Storage Account**: Use the following command to create the storage account:\n\n    ```bash\n    az storage account create --name mystorageaccount --resource-group myResourceGroup --location eastus --sku Standard_LRS\n    ```\n\n   Replace `mystorageaccount` with a unique name for your storage account. The storage account name must be between 3 and 24 characters in length, and may contain numbers and lowercase letters only. You can also choose other `--sku` options like `Standard_GRS`, `Standard_RAGRS`, `Standard_ZRS`, `Premium_LRS`, based on your redundancy and performance needs.\n\nBy following these steps, you'll create a new Azure Storage account in the specified resource group and location with the specified SKU.","annotations":[],"logprobs":[]}]}],"parallel_tool_calls":true,"status":"completed"}
```
