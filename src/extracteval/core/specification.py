"""Typed semantic values and external operational dictionary contracts."""

from datetime import date
from typing import Annotated, Literal, Self

from pydantic import (
    Field,
    StrictBool,
    StrictFloat,
    StrictInt,
    StrictStr,
    TypeAdapter,
    model_validator,
)

from extracteval.core.base import ArtifactRef, Contract, Identifier


class CategoryValue(Contract):
    kind: Literal["categorical"] = "categorical"
    value: StrictStr = Field(repr=False)


class BooleanValue(Contract):
    kind: Literal["boolean"] = "boolean"
    value: StrictBool = Field(repr=False)


class NumberValue(Contract):
    kind: Literal["numeric"] = "numeric"
    value: StrictInt | Annotated[StrictFloat, Field(allow_inf_nan=False)] = Field(repr=False)


class DateValue(Contract):
    kind: Literal["date"] = "date"
    value: date = Field(strict=True, repr=False)


class TextValue(Contract):
    kind: Literal["text"] = "text"
    value: StrictStr = Field(repr=False)


SemanticValue = Annotated[
    CategoryValue | BooleanValue | NumberValue | DateValue | TextValue,
    Field(discriminator="kind"),
]
SEMANTIC_VALUE_ADAPTER: TypeAdapter[SemanticValue] = TypeAdapter(SemanticValue)
VariableType = Literal["categorical", "boolean", "numeric", "date", "text"]


class InformationPolicy(Contract):
    """Operational instructions, not automatic extraction status mappings."""

    absent: str = Field(min_length=1, repr=False)
    indeterminate: str = Field(min_length=1, repr=False)
    not_applicable: str = Field(min_length=1, repr=False)


class VariableDefinition(Contract):
    variable_id: Identifier
    version: Identifier
    data_type: VariableType
    categories: tuple[StrictStr, ...] = ()
    operational_definition: str = Field(min_length=1, repr=False)
    interpretation_rules: tuple[str, ...] = Field(default=(), repr=False)
    correctness_criteria: tuple[str, ...] = Field(min_length=1, repr=False)
    information_policy: InformationPolicy
    normalization_rules: tuple[Identifier, ...] = ()

    @model_validator(mode="after")
    def valid_categories(self) -> Self:
        if self.data_type == "categorical":
            if not self.categories or len(set(self.categories)) != len(self.categories):
                raise ValueError("Categorical variables require unique categories")
        elif self.categories:
            raise ValueError("Only categorical variables can declare categories")
        return self

    def validate_value(self, value: SemanticValue) -> None:
        if value.kind != self.data_type:
            raise ValueError("Semantic value type does not match variable definition")
        if isinstance(value, CategoryValue) and value.value not in self.categories:
            raise ValueError("Semantic value is outside the variable domain")


class OperationalDictionary(Contract):
    artifact: ArtifactRef
    variables: tuple[VariableDefinition, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_variables(self) -> Self:
        ids = [variable.variable_id for variable in self.variables]
        if len(ids) != len(set(ids)):
            raise ValueError("Variable identifiers must be unique within a dictionary")
        return self

    def variable(self, variable_id: str) -> VariableDefinition:
        for variable in self.variables:
            if variable.variable_id == variable_id:
                return variable
        raise KeyError("Variable is not defined in this dictionary")
