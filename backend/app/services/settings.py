"""Learning hyperparameters stored in the `settings` table (key `learning`)."""

from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.models import Setting


class LearningParams(BaseModel):
    shrink_k: float = Field(5.0, gt=0, description="Pseudo-count pulling a scope toward its parent.")
    actual_prior_k: float = Field(4.0, gt=0, description="Pseudo-count of the edit layer as prior for actuals.")
    default_sigma2: float = Field(0.25, gt=0, description="Log-space variance used before any data exists.")
    author_min_n: int = Field(5, ge=1, description="Edits needed before a PM-specific scope is used.")
    sim_min: float = Field(0.75, ge=0, le=1, description="Minimum cosine similarity for an analog.")
    analog_top_k: int = Field(5, ge=1, le=20)
    w_per_analog: float = Field(0.12, ge=0, le=1, description="Blend weight added per qualifying analog.")
    w_max: float = Field(0.6, ge=0, le=1, description="Maximum analog blend weight.")
    range_low_q: float = Field(0.10, gt=0, lt=0.5)
    range_high_q: float = Field(0.90, gt=0.5, lt=1)
    min_task_hours: float = Field(0.25, gt=0)
    max_range_multiple: float = Field(20.0, gt=1)
    sim_draws: int = Field(10_000, ge=500, le=200_000)
    empirical_min_n: int = Field(8, ge=2, description="Residual pool size to sample empirically.")
    project_factor_min_n: int = Field(5, ge=2)
    sigma_proj: float = Field(0.15, ge=0, description="Default shared project-level log sigma.")
    raw_samples: int = Field(3, ge=1, le=9)
    max_active_rules: int = Field(10, ge=0, le=50)
    large_edit_threshold: float = Field(0.2, ge=0, description="Relative change that shows 'Why?' chips.")
    retrieval_context_enabled: bool = Field(True, description="Inject similar past projects into prompts.")
    retrieval_k: int = Field(3, ge=0, le=10, description="Similar past projects used as context.")
    retrieval_min_similarity: float = Field(0.55, ge=0, le=1, description="Below this, return fewer (never pad).")
    retrieval_include_synthetic: bool = Field(True, description="Allow synthetic projects as references.")
    retrieval_mmr_lambda: float = Field(0.7, ge=0, le=1, description="Relevance vs diversity in re-ranking.")
    retrieval_delivered_boost: float = Field(0.05, ge=0, le=0.5, description="Score bonus for delivered projects.")
    retrieval_token_cap: int = Field(1500, ge=200, le=6000, description="Max tokens per reference context pack.")
    analog_blend_enabled: bool = Field(True, description="Blend task-level analogs into calibrated hours.")


DEFAULTS = LearningParams()


def get_params(db: Session) -> LearningParams:
    row = db.get(Setting, "learning")
    if row is None:
        return LearningParams()
    return LearningParams(**{**DEFAULTS.model_dump(), **(row.value or {})})


def save_params(db: Session, values: dict[str, Any]) -> LearningParams:
    params = LearningParams(**{**get_params(db).model_dump(), **values})
    row = db.get(Setting, "learning")
    if row is None:
        db.add(Setting(key="learning", value=params.model_dump()))
    else:
        row.value = params.model_dump()
    db.commit()
    return params


def reset_params(db: Session) -> LearningParams:
    return save_params(db, DEFAULTS.model_dump())
