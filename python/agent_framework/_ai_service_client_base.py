# Copyright (c) Microsoft. All rights reserved.

from abc import ABC
from typing import Annotated, Any

from pydantic.types import StringConstraints

from agent_framework import AFBaseModel


class AIServiceClientBase(AFBaseModel, ABC):
    """Base class for all AI Services.

    Has an ai_model_id and service_id, any other fields have to be defined by the subclasses.

    The ai_model_id can refer to a specific model, like 'gpt-35-turbo' for OpenAI,
    or can just be a string that is used to identify the model in the service.

    The service_id is used in Semantic Kernel to identify the service, if empty the ai_model_id is used.
    """

    ai_model_id: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
    service_id: str = ""

    def model_post_init(self, _: Any) -> None:
        """Update the service_id if it is not set."""
        if not self.service_id:
            self.service_id = self.ai_model_id

    def service_url(self) -> str | None:
        """Get the URL of the service.

        Override this in the subclass to return the proper URL.
        If the service does not have a URL, return None.
        """
        return None
