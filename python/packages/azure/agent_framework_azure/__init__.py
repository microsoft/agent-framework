# Copyright (c) Microsoft. All rights reserved.

import importlib.metadata

from ._assistants_client import AzureAssistantsClient
from ._chat_client import AzureChatClient
from ._entra_id_authentication import get_entra_auth_token
from ._responses_client import AzureResponsesClient
from ._shared import AzureOpenAISettings

try:
    __version__ = importlib.metadata.version(__name__)
except importlib.metadata.PackageNotFoundError:
    __version__ = "0.0.0"  # Fallback for development mode

__all__ = [
    "AzureAssistantsClient",
    "AzureChatClient",
    "AzureOpenAISettings",
    "AzureResponsesClient",
    "__version__",
    "get_entra_auth_token",
]
