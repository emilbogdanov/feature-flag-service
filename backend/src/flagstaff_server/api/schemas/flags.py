from datetime import datetime
from typing import Annotated, Literal, Self

from flagstaff.engine.bucketing import BUCKET_COUNT
from flagstaff.engine.conditions import Operator
from flagstaff.engine.variants import FlagKind, Variant
from flagstaff.engine.wire import variants_from_document, variants_to_document
from pydantic import BaseModel, Field, JsonValue, StrictBool, StrictFloat, StrictInt, StrictStr

from flagstaff_server.api.schemas.common import Request
from flagstaff_server.domain.flags import Flag, Targeting
from flagstaff_server.domain.projects import Environment

# These models describe the engine's wire format for the OpenAPI schema and the dashboard's
# generated types. They don't decide what is valid: bodies are dumped back to JSON and read by
# the engine, so the API accepts exactly what an SDK would.


class VariantSchema(Request):
    key: str
    value: JsonValue


class AttributeConditionSchema(Request):
    type: Literal["attribute"]
    attribute: str
    operator: Operator
    # Strict, so "5" stays text instead of quietly becoming the number 5.
    values: list[StrictStr | StrictBool | StrictInt | StrictFloat]
    negate: bool = False


class UserListConditionSchema(Request):
    type: Literal["user_list"]
    user_keys: list[str]


ConditionSchema = Annotated[
    AttributeConditionSchema | UserListConditionSchema, Field(discriminator="type")
]


class FixedServeSchema(Request):
    variant: str


class WeightSchema(Request):
    variant: str
    weight: int = Field(
        description=f"Out of {BUCKET_COUNT}; the weights of one rollout add up to exactly that."
    )


class RolloutServeSchema(Request):
    rollout: list[WeightSchema]


ServeSchema = FixedServeSchema | RolloutServeSchema


class RuleSchema(Request):
    id: str = Field(description="Chosen by the client; reported back in evaluation reasons.")
    conditions: list[ConditionSchema]
    serve: ServeSchema


class TargetingSchema(Request):
    enabled: bool
    off_variant: str
    rules: list[RuleSchema] = Field(default_factory=list)
    fallthrough: ServeSchema

    @classmethod
    def of(cls, targeting: Targeting) -> Self:
        return cls.model_validate(targeting.to_document())

    def to_targeting(self) -> Targeting:
        return Targeting.from_document(self.model_dump(mode="json"))


def variants_of(schemas: list[VariantSchema]) -> tuple[Variant, ...]:
    return variants_from_document([schema.model_dump(mode="json") for schema in schemas])


class CreateFlag(Request):
    key: str = Field(description="What code asks for. Fixed once created.")
    name: str
    description: str = ""
    kind: FlagKind
    variants: list[VariantSchema]
    off_variant: str = Field(description="Served wherever the flag is off.")
    on_variant: str = Field(description="Served to everyone once the flag is first turned on.")


class ChangeFlagDetails(Request):
    name: str
    description: str = ""


class ChangeVariants(Request):
    variants: list[VariantSchema]


class FlagResponse(BaseModel):
    key: str
    name: str
    description: str
    kind: FlagKind
    variants: list[VariantSchema]
    version: int = Field(description="Also sent as the ETag; send it back in If-Match to edit.")
    environments: dict[str, TargetingSchema] = Field(
        description="How each environment evaluates the flag, by environment key."
    )
    created_at: datetime
    updated_at: datetime
    archived_at: datetime | None

    @classmethod
    def of(cls, flag: Flag, environments: list[Environment]) -> Self:
        return cls(
            key=flag.key,
            name=str(flag.name),
            description=str(flag.description),
            kind=flag.kind,
            variants=[
                VariantSchema.model_validate(document)
                for document in variants_to_document(flag.variants)
            ],
            version=flag.version,
            environments={
                str(environment.key): TargetingSchema.of(flag.targeting_in(environment.id))
                for environment in environments
            },
            created_at=flag.created_at,
            updated_at=flag.updated_at,
            archived_at=flag.archived_at,
        )
