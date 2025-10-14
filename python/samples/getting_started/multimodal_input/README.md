# Multimodal Input Examples

This folder contains examples demonstrating how to send multimodal content (images, audio, PDF files) to AI agents using the Agent Framework.

## Examples

### OpenAI Chat Client

- **File**: `openai_chat_multimodal.py`
- **Description**: Shows how to send images, audio, and PDF files to OpenAI's Chat Completions API
- **Supported formats**: PNG/JPEG images, WAV/MP3 audio, PDF documents

### Azure OpenAI Chat Client

- **File**: `azure_chat_multimodal.py`
- **Description**: Shows how to send images to Azure OpenAI Chat Completions API
- **Supported formats**: PNG/JPEG images (PDF files are NOT supported by Chat Completions API)

### Azure OpenAI Responses Client

- **File**: `azure_responses_multimodal.py`
- **Description**: Shows how to send images and PDF files to Azure OpenAI Responses API
- **Supported formats**: PNG/JPEG images, PDF documents (full multimodal support)

## Environment Variables

Set the following environment variables before running the examples:

**For OpenAI:**
- `OPENAI_API_KEY`: Your OpenAI API key

**For Azure OpenAI:**

- `AZURE_OPENAI_ENDPOINT`: Your Azure OpenAI endpoint
- `AZURE_OPENAI_CHAT_DEPLOYMENT_NAME`: The name of your Azure OpenAI chat model deployment
- `AZURE_OPENAI_RESPONSES_DEPLOYMENT_NAME`: The name of your Azure OpenAI responses model deployment

Optionally for Azure OpenAI:
- `AZURE_OPENAI_API_VERSION`: The API version to use (default is `2024-10-21`)
- `AZURE_OPENAI_API_KEY`: Your Azure OpenAI API key (if not using `AzureCliCredential`)

**Note:** You can also provide configuration directly in code instead of using environment variables:
```python
# Example: Pass deployment_name directly
client = AzureOpenAIChatClient(
    credential=AzureCliCredential(),
    deployment_name="your-deployment-name",
    endpoint="https://your-resource.openai.azure.com"
)
```

## Authentication

The Azure example uses `AzureCliCredential` for authentication. Run `az login` in your terminal before running the example, or replace `AzureCliCredential` with your preferred authentication method (e.g., provide `api_key` parameter).

## Running the Examples

```bash
# Run OpenAI example
python openai_chat_multimodal.py

# Run Azure Chat example (requires az login or API key)
python azure_chat_multimodal.py

# Run Azure Responses example (requires az login or API key)
python azure_responses_multimodal.py
```

## Using Your Own Files

The examples include small embedded test files for demonstration. To use your own files:

### Method 1: Data URIs (recommended)

```python
import base64

# Load and encode your file
with open("path/to/your/image.jpg", "rb") as f:
    image_data = f.read()
    image_base64 = base64.b64encode(image_data).decode('utf-8')
    image_uri = f"data:image/jpeg;base64,{image_base64}"

# Use in DataContent
DataContent(
    uri=image_uri,
    media_type="image/jpeg"
)
```

### Method 2: Raw bytes

```python
# Load raw bytes
with open("path/to/your/image.jpg", "rb") as f:
    image_bytes = f.read()

# Use in DataContent
DataContent(
    data=image_bytes,
    media_type="image/jpeg"
)
```

## Supported File Types

| Type      | Formats              | Notes                          |
| --------- | -------------------- | ------------------------------ |
| Images    | PNG, JPEG, GIF, WebP | Most common image formats      |
| Audio     | WAV, MP3             | For transcription and analysis |
| Documents | PDF                  | Text extraction and analysis   |

## API Differences

- **OpenAI Chat Completions API**: Supports images, audio, and PDF files
- **Azure OpenAI Chat Completions API**: Supports images only (no PDF/audio file types)
- **Azure OpenAI Responses API**: Supports images and PDF files (full multimodal support)

Choose the appropriate client based on your multimodal needs and available APIs.
