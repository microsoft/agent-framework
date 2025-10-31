# Get Started with Microsoft Agent Framework and LiteLLM

Please install this package via pip:

```bash
pip install agent-framework-litellm --pre
```

and see the [README](https://github.com/microsoft/agent-framework/tree/main/python/README.md) for more information.



# Configuration
- LiteLLM AF clients can be configured similarly to the pure LiteLLM clients (see https://docs.litellm.ai/docs/ for more information).

 As with other clients, configuration can be provided either on class instantiation or via environment variables:
- Set `api_key` and `api_base` for your provider, or per LiteLLM env var instructions (varied settings per provider). See https://docs.litellm.ai/docs/ for more information.
- `model_id` (param) or `LITE_LLM_MODEL_ID` (env var): The provider+model used for chat and responses clients (e.g. `azure_ai/gpt-4o-mini`)

# Development Notes

* LiteLLM doesn't have a generic way of setting config for model id (see https://docs.litellm.ai/docs/set_keys for more information on available environment vairiables). For this reason, we've added the "LITE_LLM_MODEL" env param which may be set. The integration still supports LiteLLM's list of provider-specific environment variables.
