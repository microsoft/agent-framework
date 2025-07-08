# Copyright (c) Microsoft. All rights reserved.


from pydantic import BaseModel, ConfigDict


class AFBaseModel(BaseModel):
    """Base class for all pydantic models in the Agent Framework."""

    model_config = ConfigDict(populate_by_name=True, arbitrary_types_allowed=True, validate_assignment=True)
