# Prerequisites

WARNING: ONNX doesn't support function calling, so any function tools passed to the agent will be ignored.

Before you begin, ensure you have the following prerequisites:

- .NET 10 SDK or later
- An ONNX model downloaded to your machine

You can download an ONNX model from hugging face, using git clone:

```powershell
git clone https://huggingface.co/microsoft/Phi-4-mini-instruct-onnx
```

Set the following environment variables:

```powershell
$env:ONNX_MODEL_PATH="C:\repos\Phi-4-mini-instruct-onnx\cpu_and_mobile\cpu-int4-rtn-block-32-acc-level-4" # Replace with your model path
```
