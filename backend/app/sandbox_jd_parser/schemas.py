from pydantic import BaseModel, Field, field_validator
from typing import Any, List, Union


class JobDescriptionSchema(BaseModel):
    """
    Schema for a parsed Job Description.
    detailed_responsibilities accepts both a plain string and a list of strings
    (the LLM sometimes returns a list) and coerces to a single string.
    """
    job_title: str = Field(..., description="The official title of the job position.")
    department: str = Field(..., description="The department or team.")
    experience_required: str = Field(..., description="The experience requirements.")
    core_technical_skills: List[str] = Field(..., description="Required technical skills.")
    behavioral_competencies: List[str] = Field(..., description="Required soft skills / competencies.")
    detailed_responsibilities: Union[str, List[str]] = Field(
        ..., description="Detailed job responsibilities."
    )

    @field_validator("detailed_responsibilities", mode="before")
    @classmethod
    def coerce_responsibilities_to_str(cls, v: Any) -> str:
        if isinstance(v, list):
            return "\n".join(str(item) for item in v if item)
        if v is None:
            return "Unknown"
        return str(v)

    @field_validator("core_technical_skills", "behavioral_competencies", mode="before")
    @classmethod
    def coerce_list_fields(cls, v: Any) -> List[str]:
        if isinstance(v, str):
            return [v] if v.strip() else []
        if v is None:
            return []
        return v
