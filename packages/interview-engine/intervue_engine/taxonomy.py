"""Skill and topic taxonomy used for resume/JD matching and question selection."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Topic:
    key: str
    label: str
    practice: tuple[str, ...] = field(default_factory=tuple)


TOPICS: dict[str, Topic] = {
    t.key: t
    for t in [
        Topic("introduction", "Introduction"),
        Topic("sql", "SQL", ("Solve 5 window-function problems (ROW_NUMBER, LAG, running totals).", "Read a query plan with EXPLAIN on a join-heavy query.")),
        Topic(
            "python",
            "Python",
            ("Implement a small CLI that streams and aggregates a large CSV with generators.", "Review dict/set complexity and common library modules."),
        ),
        Topic(
            "pyspark",
            "PySpark",
            (
                "Reproduce a skewed join locally and fix it with salting or broadcast.",
                "Compare repartition vs coalesce on a sample job and inspect the Spark UI.",
            ),
        ),
        Topic("aws", "AWS", ("Draw an end-to-end AWS data platform and label IAM boundaries.", "Review the AWS Well-Architected data analytics lens.")),
        Topic("s3", "Amazon S3", ("Design a partitioned S3 layout for event data and justify the partition keys.",)),
        Topic("glue", "AWS Glue", ("Build a Glue job with job bookmarks over a partitioned dataset.",)),
        Topic("athena", "Amazon Athena", ("Convert a CSV table to partitioned Parquet and compare Athena scan costs.",)),
        Topic("redshift", "Amazon Redshift", ("Choose distribution and sort keys for a star schema and justify them.",)),
        Topic("airflow", "Apache Airflow", ("Write a DAG with retries, SLAs and idempotent tasks; test a backfill.",)),
        Topic("kafka", "Apache Kafka", ("Explain partitions, consumer groups and offsets with a whiteboard sketch.",)),
        Topic("data_modeling", "Data modeling", ("Model a star schema for an orders domain including an SCD Type 2 dimension.",)),
        Topic("etl", "ETL / ELT", ("Design an incremental load with CDC and late-arriving data handling.",)),
        Topic("data_quality", "Data quality", ("Add row-count, null and uniqueness checks to a pipeline and alert on failure.",)),
        Topic("system_design", "System design", ("Practise one system design per day: requirements, components, data flow, failure modes.",)),
        Topic("behavioral", "Behavioral", ("Prepare 5 STAR stories: conflict, failure, ownership, ambiguity, impact.",)),
        Topic("algorithms", "Algorithms & data structures", ("Solve 2 hash-map and 2 two-pointer problems daily, stating complexity aloud.",)),
        Topic("javascript", "JavaScript / TypeScript", ("Review the event loop, promises and closures with small examples.",)),
        Topic("api_design", "API design", ("Design a REST API with pagination, idempotency keys and versioning.",)),
        Topic("databases", "Databases", ("Explain indexes, transactions and isolation levels with examples.",)),
        Topic("docker", "Docker & containers", ("Write a multi-stage Dockerfile and explain each layer.",)),
        Topic("kubernetes", "Kubernetes", ("Deploy a service with readiness probes, resource limits and an HPA.",)),
        Topic("ci_cd", "CI/CD", ("Build a pipeline with test, build, deploy and rollback stages.",)),
        Topic("observability", "Observability", ("Define SLIs/SLOs for a service and design alerts on them.",)),
        Topic("linux", "Linux & networking", ("Troubleshoot a slow service using top, ss, curl and logs.",)),
        Topic("machine_learning", "Machine learning", ("Explain bias/variance and evaluation metrics on a real dataset.",)),
        Topic("llm", "LLMs & GenAI", ("Build a small RAG app and evaluate retrieval quality.",)),
        Topic("statistics", "Statistics", ("Practise hypothesis testing and confidence intervals on A/B test data.",)),
        Topic("data_analysis", "Data analysis & BI", ("Build a dashboard answering three business questions and present it.",)),
        Topic("customer_scenarios", "Customer scenarios", ("Practise scoping an ambiguous customer request into a deliverable plan.",)),
    ]
}


@dataclass(frozen=True)
class Skill:
    name: str
    topic: str
    aliases: tuple[str, ...]


SKILLS: list[Skill] = [
    Skill("SQL", "sql", ("sql", "postgresql", "postgres", "mysql", "t-sql", "pl/sql", "sql server", "oracle")),
    Skill("Window functions", "sql", ("window function", "row_number", "rank()", "lag(", "lead(")),
    Skill("Python", "python", ("python", "pandas", "numpy")),
    Skill("PySpark", "pyspark", ("pyspark", "spark", "databricks", "spark sql")),
    Skill("AWS", "aws", ("aws", "amazon web services")),
    Skill("Amazon S3", "s3", ("s3", "amazon s3", "data lake")),
    Skill("AWS Glue", "glue", ("glue", "aws glue", "glue catalog")),
    Skill("Amazon Athena", "athena", ("athena",)),
    Skill("Amazon Redshift", "redshift", ("redshift",)),
    Skill("AWS Lambda", "aws", ("lambda",)),
    Skill("Amazon EMR", "aws", ("emr",)),
    Skill("Amazon Kinesis", "aws", ("kinesis", "firehose")),
    Skill("Step Functions", "aws", ("step functions",)),
    Skill("Apache Airflow", "airflow", ("airflow", "mwaa")),
    Skill("Apache Kafka", "kafka", ("kafka", "msk", "confluent")),
    Skill("Data modeling", "data_modeling", ("data modeling", "data modelling", "star schema", "dimensional model", "snowflake schema", "scd")),
    Skill("ETL/ELT", "etl", ("etl", "elt", "data pipeline", "pipelines", "ingestion", "cdc")),
    Skill("dbt", "etl", ("dbt",)),
    Skill("Data quality", "data_quality", ("data quality", "great expectations", "deequ", "data validation")),
    Skill("Snowflake", "databases", ("snowflake",)),
    Skill("Java", "algorithms", ("java",)),
    Skill("Scala", "pyspark", ("scala",)),
    Skill("JavaScript", "javascript", ("javascript", "node.js", "nodejs", "node")),
    Skill("TypeScript", "javascript", ("typescript",)),
    Skill("React", "javascript", ("react", "next.js", "nextjs")),
    Skill("REST APIs", "api_design", ("rest api", "restful", "fastapi", "flask", "django", "express", "graphql")),
    Skill("Docker", "docker", ("docker", "container")),
    Skill("Kubernetes", "kubernetes", ("kubernetes", "k8s", "eks", "helm")),
    Skill("CI/CD", "ci_cd", ("ci/cd", "jenkins", "github actions", "gitlab ci", "circleci")),
    Skill("Terraform", "ci_cd", ("terraform", "cloudformation", "cdk", "infrastructure as code")),
    Skill("Observability", "observability", ("prometheus", "grafana", "cloudwatch", "datadog", "observability")),
    Skill("Linux", "linux", ("linux", "bash", "shell scripting")),
    Skill("Machine learning", "machine_learning", ("machine learning", "scikit-learn", "sklearn", "xgboost", "tensorflow", "pytorch")),
    Skill("LLMs", "llm", ("llm", "large language model", "genai", "generative ai", "langchain", "rag", "prompt engineering", "embeddings")),
    Skill("Statistics", "statistics", ("statistics", "a/b test", "hypothesis testing", "regression")),
    Skill("Excel", "data_analysis", ("excel",)),
    Skill("Power BI", "data_analysis", ("power bi", "powerbi")),
    Skill("Tableau", "data_analysis", ("tableau",)),
    Skill("Algorithms", "algorithms", ("algorithms", "data structures", "leetcode")),
    Skill("System design", "system_design", ("system design", "distributed systems", "microservices", "scalability")),
    Skill("Git", "ci_cd", ("git", "github", "gitlab")),
]


def topic_label(key: str) -> str:
    t = TOPICS.get(key)
    return t.label if t else key.replace("_", " ").title()
