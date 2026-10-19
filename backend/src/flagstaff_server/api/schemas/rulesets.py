from typing import Self

from flagstaff.engine.context import EvaluationContext
from flagstaff.engine.evaluation import Evaluation, EvaluationReason
from flagstaff.engine.variants import FlagKind
from pydantic import BaseModel, Field, JsonValue, StrictBool, StrictFloat, StrictInt, StrictStr

from flagstaff_server.api.schemas.common import Request
from flagstaff_server.api.schemas.flags import RuleSchema, ServeSchema, VariantSchema


# The ruleset document exactly as the engine writes it; documented here so SDKs in other
# languages can be generated from the schema.
class CompiledFlagSchema(BaseModel):
    key: str
    kind: FlagKind
    enabled: bool
    variants: list[VariantSchema]
    off_variant: str
    rules: list[RuleSchema]
    fallthrough: ServeSchema


class RulesetSchema(BaseModel):
    format: int = Field(description="Bumped only for changes an older SDK would misread.")
    version: int = Field(description="Also the ETag; send it in If-None-Match to get a 304.")
    flags: list[CompiledFlagSchema]


class ContextSchema(Request):
    key: str = Field(description="The user key rollouts bucket on.")
    attributes: dict[str, StrictStr | StrictBool | StrictInt | StrictFloat] = Field(
        default_factory=dict
    )

    def to_context(self) -> EvaluationContext:
        return EvaluationContext(self.key, self.attributes)


class EvaluateRequest(Request):
    context: ContextSchema
    flags: list[str] | None = Field(
        default=None,
        description="Only these flags; leave out for all. Unknown keys are left out of the answer.",
    )


class EvaluationResponse(BaseModel):
    variant: str
    value: JsonValue
    reason: EvaluationReason
    rule_id: str | None

    @classmethod
    def of(cls, evaluation: Evaluation) -> Self:
        return cls(
            variant=evaluation.variant.key,
            value=evaluation.value,
            reason=evaluation.reason,
            rule_id=evaluation.rule_id,
        )


class EvaluationsResponse(BaseModel):
    version: int = Field(description="The ruleset version the flags were evaluated against.")
    evaluations: dict[str, EvaluationResponse]
