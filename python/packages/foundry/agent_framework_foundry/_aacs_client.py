# Copyright (c) Microsoft. All rights reserved.

import os
from azure.ai.contentsafety import ContentSafetyClient
from azure.ai.contentsafety.models import TextCategory
from azure.core.credentials import AzureKeyCredential
from azure.core.exceptions import HttpResponseError
from azure.ai.contentsafety.models import AnalyzeTextOptions


_azure_ai_content_safety_client = None
def get_or_create_content_safety_client():
    global _azure_ai_content_safety_client

    if _azure_ai_content_safety_client is None:
        key = os.environ["AZURE_AI_CONTENT_SAFETY_API_KEY"]
        endpoint = os.environ["AZURE_AI_CONTENT_SAFETY_ENDPOINT"]

        # Create a Content Safety client
        _azure_ai_content_safety_client = ContentSafetyClient(endpoint, AzureKeyCredential(key))

    return _azure_ai_content_safety_client
