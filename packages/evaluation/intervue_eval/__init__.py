"""Evaluation: per-answer scoring, evidence verification and report aggregation."""

from intervue_eval.report import AnswerRecord, TimeStats, build_report
from intervue_eval.schemas import (
    CATEGORIES,
    AnswerScore,
    CategoryScore,
    CodeFailure,
    CodeSubmissionSummary,
    DesignEdge,
    DesignNode,
    DesignSummary,
    Evidence,
    ExpectedConcept,
    Report,
)
from intervue_eval.scoring import EvaluationProvider, match_concepts, verify_evidence

__all__ = [
    "CATEGORIES",
    "AnswerRecord",
    "AnswerScore",
    "CategoryScore",
    "CodeFailure",
    "CodeSubmissionSummary",
    "DesignEdge",
    "DesignNode",
    "DesignSummary",
    "EvaluationProvider",
    "Evidence",
    "ExpectedConcept",
    "Report",
    "TimeStats",
    "build_report",
    "match_concepts",
    "verify_evidence",
]
