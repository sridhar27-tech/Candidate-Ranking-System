from pydantic import BaseModel, Field, field_validator, model_validator
from typing import Any, List, Dict, Optional, Union


class SalaryRangeModel(BaseModel):
    min: float
    max: float


class RedRobSignalsModel(BaseModel):
    profile_completeness_score: float
    signup_date: Optional[str] = None
    last_active_date: Optional[str] = None
    open_to_work_flag: bool
    profile_views_received_30d: Optional[int] = 0
    applications_submitted_30d: Optional[int] = 0
    recruiter_response_rate: float
    avg_response_time_hours: Optional[float] = 0.0
    github_activity_score: float
    connection_count: Optional[int] = 0
    endorsements_received: Optional[int] = 0
    notice_period_days: int
    expected_salary_range_inr_lpa: SalaryRangeModel
    preferred_work_mode: Optional[str] = "onsite"
    willing_to_relocate: Optional[bool] = False
    search_appearance_30d: Optional[int] = 0
    saved_by_recruiters_30d: Optional[int] = 0
    interview_completion_rate: Optional[float] = 0.0
    offer_acceptance_rate: Optional[float] = 0.0
    verified_email: Optional[bool] = True
    verified_phone: Optional[bool] = False
    linkedin_connected: Optional[bool] = False
    skill_assessment_scores: Dict[str, float] = Field(default_factory=dict)


# =====================================================================
# CORE CANDIDATE PROFILE & LIFECYCLE SCHEMAS
# =====================================================================

class ProfileDetailsModel(BaseModel):
    anonymized_name: str
    headline: str
    summary: str
    location: str
    country: str
    years_of_experience: float
    current_title: Optional[str] = None
    current_company: Optional[str] = None
    current_company_size: Optional[str] = None
    current_industry: Optional[str] = None


class CareerHistoryModel(BaseModel):
    company: str
    title: str
    start_date: str
    end_date: Optional[str] = None
    duration_months: int
    is_current: bool
    industry: Optional[str] = None
    company_size: Optional[str] = None
    description: str


class EducationModel(BaseModel):
    institution: str
    degree: str
    field_of_study: str
    start_year: int
    end_year: int
    grade: Optional[str] = None
    tier: Optional[str] = "tier_4"


class SkillModel(BaseModel):
    name: str
    proficiency: str
    endorsements: Optional[int] = 0
    duration_months: int


# =====================================================================
# MAIN PIPELINE INPUT SCHEMA
# =====================================================================

class CandidateModel(BaseModel):
    candidate_id: str
    profile: ProfileDetailsModel
    career_history: List[CareerHistoryModel]
    education: List[EducationModel]
    skills: List[SkillModel]
    certifications: List[Any] = Field(default_factory=list)   # str or {name,issuer,year}
    languages: List[Dict[str, str]] = Field(default_factory=list)
    redrob_signals: RedRobSignalsModel


# =====================================================================
# JOB DESCRIPTION INPUT SCHEMA
# Accepts detailed_responsibilities as either a string or a list of
# strings (LLMs sometimes return a list) and coerces to a single string.
# =====================================================================

class JobDescriptionInput(BaseModel):
    """Structured JD produced by the parser pipeline."""
    job_title: str = "Unknown"
    department: str = "Unknown"
    experience_required: str = "Unknown"
    core_technical_skills: List[str] = Field(default_factory=list)
    behavioral_competencies: List[str] = Field(default_factory=list)
    detailed_responsibilities: Union[str, List[str]] = "Unknown"

    @model_validator(mode="before")
    @classmethod
    def parse_from_string(cls, v: Any) -> Any:
        if isinstance(v, str):
            return {
                "detailed_responsibilities": v
            }
        return v

    @field_validator("detailed_responsibilities", mode="before")
    @classmethod
    def coerce_responsibilities_to_str(cls, v: Any) -> str:
        """Accept list or string; always store as a single newline-joined string."""
        if isinstance(v, list):
            return "\n".join(str(item) for item in v if item)
        if v is None:
            return "Unknown"
        return str(v)

    @field_validator("core_technical_skills", "behavioral_competencies", mode="before")
    @classmethod
    def coerce_list_fields(cls, v: Any) -> List[str]:
        """If the LLM returns a plain string for a list field, wrap it."""
        if isinstance(v, str):
            return [v] if v.strip() else []
        if v is None:
            return []
        return v

    def to_evaluation_text(self) -> str:
        """Condense structured JD into a focused text string for semantic embedding."""
        skills_text = ", ".join(self.core_technical_skills) if self.core_technical_skills else ""
        parts = [
            f"Role: {self.job_title}.",
            f"Department: {self.department}.",
            f"Experience: {self.experience_required}.",
        ]
        if skills_text:
            parts.append(f"Required skills: {skills_text}.")
        responsibilities = self.detailed_responsibilities
        if responsibilities and responsibilities != "Unknown":
            parts.append(f"Responsibilities: {responsibilities}")
        return " ".join(parts)


class RankingPayloadSchema(BaseModel):
    job_description: str
    candidates: List[CandidateModel]
