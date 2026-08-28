from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class CamelModel(BaseModel):
    """Base for models exposed over HTTP / logs / webhooks.

    Field names are snake_case in code and camelCase in JSON (``request_id`` ↔ ``requestId``); both
    are accepted on input, and serialisation always uses the alias.
    """

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, serialize_by_alias=True)
