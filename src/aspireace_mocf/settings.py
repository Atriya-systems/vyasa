from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Settings:
    provider: str
    model_name: str
    temperature: float
    max_tokens: int
    class_level: str
    subject: str
    exam_targets: list[str]
    source_type: str
    lmstudio_base_url: str
    lmstudio_api_key: str
    openai_base_url: str
    openai_api_key: str
    base_records_per_unit: int
    tutor_records_per_unit: int
    contentgen_records_per_unit: int
    app_cards_per_unit: int
    dpp_records_per_unit: int
    rubric_records_per_unit: int
    revision_records_per_unit: int
    eval_ratio: float
    random_seed: int
    enable_llm_judge: bool
    min_core_score: int
    similarity_warn_threshold: float
    agent_max_retries: int
    human_in_loop: bool
    mlflow_tracking_uri: str
    mlflow_experiment: str


def load_settings() -> Settings:
    load_dotenv()
    return Settings(
        provider=os.getenv("PROVIDER", "lmstudio").strip().lower(),
        model_name=os.getenv("MODEL_NAME", "qwen/qwen3").strip(),
        temperature=float(os.getenv("TEMPERATURE", "0.1")),
        max_tokens=int(os.getenv("MAX_TOKENS", "9000")),
        class_level=os.getenv("CLASS_LEVEL", "11").strip(),
        subject=os.getenv("SUBJECT", "Physics").strip(),
        exam_targets=[x.strip() for x in os.getenv("EXAM_TARGETS", "JEE,NEET").split(",") if x.strip()],
        source_type=os.getenv("SOURCE_TYPE", "SME_OWNED").strip(),
        lmstudio_base_url=os.getenv("LMSTUDIO_BASE_URL", "http://localhost:1234/v1").strip(),
        lmstudio_api_key=os.getenv("LMSTUDIO_API_KEY", "lm-studio").strip(),
        openai_base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").strip(),
        openai_api_key=os.getenv("OPENAI_API_KEY", "").strip(),
        base_records_per_unit=int(os.getenv("BASE_RECORDS_PER_UNIT", "4")),
        tutor_records_per_unit=int(os.getenv("TUTOR_RECORDS_PER_UNIT", "5")),
        contentgen_records_per_unit=int(os.getenv("CONTENTGEN_RECORDS_PER_UNIT", "5")),
        app_cards_per_unit=int(os.getenv("APP_CARDS_PER_UNIT", "2")),
        dpp_records_per_unit=int(os.getenv("DPP_RECORDS_PER_UNIT", "3")),
        rubric_records_per_unit=int(os.getenv("RUBRIC_RECORDS_PER_UNIT", "2")),
        revision_records_per_unit=int(os.getenv("REVISION_RECORDS_PER_UNIT", "3")),
        eval_ratio=float(os.getenv("EVAL_RATIO", "0.10")),
        random_seed=int(os.getenv("RANDOM_SEED", "42")),
        enable_llm_judge=os.getenv("ENABLE_LLM_JUDGE", "false").strip().lower() == "true",
        min_core_score=int(os.getenv("MIN_CORE_SCORE", "4")),
        similarity_warn_threshold=float(os.getenv("SIMILARITY_WARN_THRESHOLD", "0.82")),
        agent_max_retries=int(os.getenv("AGENT_MAX_RETRIES", "2")),
        human_in_loop=os.getenv("HUMAN_IN_LOOP", "false").strip().lower() == "true",
        mlflow_tracking_uri=os.getenv("MLFLOW_TRACKING_URI", "mlruns").strip(),
        mlflow_experiment=os.getenv("MLFLOW_EXPERIMENT", "aspireace-modelops-contentops").strip(),
    )
