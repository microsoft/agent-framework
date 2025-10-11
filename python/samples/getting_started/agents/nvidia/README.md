# NVIDIA NIM Examples

This folder contains examples demonstrating how to use NVIDIA NIM (NVIDIA Inference Microservices) models with the Agent Framework through Azure AI Foundry.

## Prerequisites

Before running these examples, you need to set up NVIDIA NIM models on Azure AI Foundry. Follow the detailed instructions in the [NVIDIA Developer Blog](https://developer.nvidia.com/blog/accelerated-ai-inference-with-nvidia-nim-on-azure-ai-foundry/#deploy_a_nim_on_azure_ai_foundry).

### Quick Setup Steps

1. **Access Azure AI Foundry Portal**
   - Navigate to [ai.azure.com](https://ai.azure.com)
   - Ensure you have a Hub and Project available

2. **Deploy NVIDIA NIM Model**
   - Select **Model Catalog** from the left sidebar
   - In the **Collections** filter, select **NVIDIA**
   - Choose a NIM microservice (e.g., Llama 3.1 8B Instruct NIM)
   - Click **Deploy**
   - Choose deployment name and VM type
   - Review pricing and terms of use
   - Click **Deploy** to launch the deployment

3. **Get API Credentials**
   - Once deployed, note your endpoint URL and API key
   - The endpoint URL should include `/v1` (e.g., `https://<endpoint>.<region>.inference.ml.azure.com/v1`)

## Examples

| File | Description |
|------|-------------|
| [`nvidia_nim_with_openai_chat_client.py`](nvidia_nim_with_openai_chat_client.py) | Demonstrates how to configure OpenAI Chat Client to use NVIDIA NIM models deployed on Azure AI Foundry. Shows both streaming and non-streaming responses with tool calling capabilities. |

## Environment Variables

Set the following environment variables before running the examples:

- `AZURE_AI_ENDPOINT`: Your Azure AI Foundry endpoint URL (e.g., `https://<endpoint>.<region>.inference.ml.azure.com/v1`)
- `AZURE_AI_API_KEY`: Your Azure AI Foundry API key
- `NVIDIA_NIM_MODEL`: The NVIDIA NIM model to use (e.g., `meta/llama-3.1-8b-instruct`)

## API Compatibility

NVIDIA NIM models deployed on Azure AI Foundry expose an OpenAI-compatible API, making them easy to integrate with existing OpenAI-based applications and frameworks. The models support:

- Standard OpenAI Chat Completion API
- Streaming and non-streaming responses
- Tool calling capabilities
- System and user messages

## Available Models

NVIDIA NIM microservices support a wide range of models including:

- **Meta Llama 3.1 8B Instruct NIM**
- **Meta Llama 3.3 70B NIM**
- **NVIDIA Nemotron models**
- **Community models**
- **Custom AI models**

For the complete list of available models, check the Model Catalog in Azure AI Foundry.

## Additional Resources

- [NVIDIA NIM on Azure AI Foundry Documentation](https://developer.nvidia.com/blog/accelerated-ai-inference-with-nvidia-nim-on-azure-ai-foundry/)
- [NVIDIA NIM Microservices](https://developer.nvidia.com/nim)
- [Azure AI Foundry Portal](https://ai.azure.com)
- [OpenAI SDK with NIM on Azure AI Foundry](https://developer.nvidia.com/blog/accelerated-ai-inference-with-nvidia-nim-on-azure-ai-foundry/#openai_sdk_with_nim_on_azure_ai_foundry)
