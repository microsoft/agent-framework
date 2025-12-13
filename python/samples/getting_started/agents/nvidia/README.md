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
| [`nvidia_nim_agent_example.py`](nvidia_nim_agent_example.py) | Complete example demonstrating how to use NVIDIA NIM models with the Agent Framework. Shows both streaming and non-streaming responses with tool calling capabilities. |
| [`nvidia_nim_chat_client.py`](nvidia_nim_chat_client.py) | Custom chat client implementation that handles NVIDIA NIM's specific message format requirements. |

## Environment Variables

Set the following environment variables before running the examples:

- `OPENAI_BASE_URL`: Your Azure AI Foundry endpoint URL (e.g., `https://<endpoint>.<region>.inference.ml.azure.com/v1`)
- `OPENAI_API_KEY`: Your Azure AI Foundry API key
- `OPENAI_CHAT_MODEL_ID`: The NVIDIA NIM model to use (e.g., `nvidia/llama-3.1-8b-instruct`)

## Running the Example

After setting up your NVIDIA NIM deployment and environment variables, you can run the example:

```bash
# Navigate to the examples directory
cd python/samples/getting_started/agents/nvidia

# Activate the virtual environment (if using one)
source ../../../.venv/bin/activate

# Set your environment variables
export OPENAI_BASE_URL="https://your-endpoint.region.inference.ml.azure.com/v1"
export OPENAI_API_KEY="your-api-key"
export OPENAI_CHAT_MODEL_ID="nvidia/llama-3.1-8b-instruct"

# Run the example
python nvidia_nim_agent_example.py
```

The example will demonstrate:
- Chat completion with NVIDIA NIM models
- Function calling capabilities
- Tool integration

## API Compatibility

NVIDIA NIM models deployed on Azure AI Foundry expose an OpenAI-compatible API, making them easy to integrate with existing OpenAI-based applications and frameworks. The models support:

- Standard OpenAI Chat Completion API
- Streaming and non-streaming responses
- Tool calling capabilities
- System and user messages

### Message Format Differences

NVIDIA NIM models expect the `content` field in messages to be a simple string, not an array of content objects like the standard OpenAI API. The example uses a custom `NVIDIANIMChatClient` that handles this conversion automatically.

**Standard OpenAI format:**
```json
{
  "role": "user",
  "content": [{"type": "text", "text": "Hello"}]
}
```

**NVIDIA NIM format:**
```json
{
  "role": "user", 
  "content": "Hello"
}
```

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
