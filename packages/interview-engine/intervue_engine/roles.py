"""Predefined role configurations. Organisations can override via interview templates."""

from __future__ import annotations

from pydantic import BaseModel


class RoleConfig(BaseModel):
    key: str
    title: str
    description: str
    topic_weights: dict[str, float]  # technical topics only; sums ~1
    coding_language: str = "python"
    has_sql_round: bool = False
    design_tags: list[str] = []
    default_experience: str = "junior"


ROLES: dict[str, RoleConfig] = {
    r.key: r
    for r in [
        RoleConfig(
            key="aws_data_engineer",
            title="AWS Data Engineer",
            description="Builds batch and streaming data pipelines on AWS (S3, Glue, Athena, Redshift) with SQL, Python and PySpark.",
            topic_weights={
                "sql": 0.18,
                "python": 0.12,
                "pyspark": 0.15,
                "aws": 0.08,
                "s3": 0.06,
                "glue": 0.07,
                "athena": 0.04,
                "redshift": 0.06,
                "airflow": 0.06,
                "kafka": 0.05,
                "data_modeling": 0.05,
                "etl": 0.04,
                "data_quality": 0.04,
            },
            has_sql_round=True,
            design_tags=["data"],
            default_experience="junior",
        ),
        RoleConfig(
            key="python_developer",
            title="Python Developer",
            description="Builds backend services and tooling in Python.",
            topic_weights={"python": 0.4, "algorithms": 0.2, "api_design": 0.15, "databases": 0.15, "docker": 0.1},
            design_tags=["backend"],
        ),
        RoleConfig(
            key="software_engineer",
            title="Software Engineer",
            description="General software engineering: algorithms, APIs, databases and system design.",
            topic_weights={"algorithms": 0.35, "api_design": 0.2, "databases": 0.2, "python": 0.1, "javascript": 0.15},
            design_tags=["backend"],
        ),
        RoleConfig(
            key="ai_engineer",
            title="AI Engineer",
            description="Builds LLM-powered and ML systems: RAG, evaluation, model serving.",
            topic_weights={"llm": 0.35, "machine_learning": 0.2, "python": 0.25, "api_design": 0.1, "statistics": 0.1},
            design_tags=["ai"],
        ),
        RoleConfig(
            key="forward_deployed_engineer",
            title="Forward Deployed Engineer",
            description="Embeds with customers to scope problems and ship integrations quickly.",
            topic_weights={"customer_scenarios": 0.3, "python": 0.2, "api_design": 0.2, "sql": 0.15, "llm": 0.15},
            has_sql_round=False,
            design_tags=["backend", "ai"],
        ),
        RoleConfig(
            key="data_analyst",
            title="Data Analyst",
            description="Answers business questions with SQL, statistics and dashboards.",
            topic_weights={"sql": 0.4, "statistics": 0.25, "data_analysis": 0.25, "python": 0.1},
            coding_language="sql",
            has_sql_round=True,
            design_tags=[],
        ),
        RoleConfig(
            key="devops_engineer",
            title="DevOps Engineer",
            description="Owns CI/CD, infrastructure as code, containers and observability.",
            topic_weights={"ci_cd": 0.25, "docker": 0.2, "kubernetes": 0.2, "observability": 0.15, "linux": 0.1, "aws": 0.1},
            design_tags=["infra"],
        ),
    ]
}


def get_role(key: str) -> RoleConfig:
    return ROLES.get(key) or ROLES["software_engineer"]
