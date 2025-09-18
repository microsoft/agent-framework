# Multimodal Input Examples

This folder contains examples demonstrating how to send multimodal content (images, audio, PDF files) to AI agents using the Agent Framework.

## Examples

### OpenAI Chat Client

- **File**: `openai_chat_multimodal.py`
- **Description**: Shows how to send images, audio, and PDF files to OpenAI's Chat Completions API
- **Supported formats**: PNG/JPEG images, WAV/MP3 audio, PDF documents

### Azure Chat Client

- **File**: `azure_chat_multimodal.py`
- **Description**: Shows how to send multimodal content to Azure OpenAI service
- **Supported formats**: PNG/JPEG images, WAV/MP3 audio, PDF documents

## Running the Examples

1. Set your API keys:

   ```bash
   export OPENAI_API_KEY="your-openai-key"
   export AZURE_OPENAI_API_KEY="your-azure-key"
   export AZURE_OPENAI_ENDPOINT="your-azure-endpoint"
   ```

2. Run an example:
   ```bash
   python openai_chat_client_multimodal.py
   python azure_chat_client_multimodal.py
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

- **Chat Completions API**: Supports images, audio, and PDF files
- **Assistants API**: Only supports text and images (no audio/PDF)
- **Responses API**: Similar to Chat Completions

Choose the appropriate client based on your multimodal needs.
