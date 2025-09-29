# Copyright (c) Microsoft. All rights reserved.


from copy import deepcopy
from unittest.mock import MagicMock


class CopyingMock(MagicMock):
    def __call__(self, *args, **kwargs):
        args = deepcopy(args)
        kwargs = deepcopy(kwargs)
        return super().__call__(*args, **kwargs)
