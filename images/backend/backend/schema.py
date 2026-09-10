import json
import os
from functools import cache

import jsonschema

from backend import settings


@cache
def load(name: str) -> dict:
    with open(os.path.join(settings.schema_dir(), name), encoding="utf-8") as f:
        return json.load(f)


def validate(obj: object, name: str) -> None:
    jsonschema.validate(obj, load(name), cls=jsonschema.Draft202012Validator)
