# Copyright (c) Microsoft. All rights reserved.

from dataclasses import fields, is_dataclass
from typing import Any
from urllib.parse import urlencode

import urllib3
from urllib3.util import Url


def dict_to_dataclass(data: dict, dataclass_type: type[Any]) -> Any:
    if not is_dataclass(dataclass_type):
        raise ValueError(f"{dataclass_type} is not a dataclass")

    # Retrieve the dataclass fields
    field_names = {field.name: field.type for field in fields(dataclass_type)}
    filtered_data = {}

    for key, value in data.items():
        if key in field_names:
            field_type = field_names[key]
            if is_dataclass(field_type):  # Check for nested dataclass
                filtered_data[key] = dict_to_dataclass(value, field_type)
            else:
                filtered_data[key] = value

    return dataclass_type(**filtered_data)


def append_url_args(url: Url, args: dict) -> Url:
    encoded_args = ""
    if len(args) == 0:
        return url
    encoded_args += urlencode(args)
    if "?" in url.url:
        url = f"{url}&{encoded_args}"
    else:
        url = f"{url}?{encoded_args}"
    return urllib3.util.parse_url(url)
