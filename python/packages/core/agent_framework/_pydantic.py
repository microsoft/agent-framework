# Copyright (c) Microsoft. All rights reserved.


from typing import Annotated

from pydantic import UrlConstraints
from pydantic.networks import AnyUrl

HTTPsUrl = Annotated[AnyUrl, UrlConstraints(max_length=2083, allowed_schemes=["https"])]

__all__ = ["HTTPsUrl"]
