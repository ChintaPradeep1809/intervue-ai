"""Explicit interview state machine: allowed phase transitions are data, validated on every move."""

from __future__ import annotations

from intervue_engine.schemas import Phase

_WORK = {Phase.INTRODUCTION, Phase.TECHNICAL_QUESTION, Phase.CODING, Phase.SYSTEM_DESIGN, Phase.BEHAVIORAL}

TRANSITIONS: dict[Phase, set[Phase]] = {
    Phase.INTERVIEW_SETUP: _WORK | {Phase.FINAL_EVALUATION},
    Phase.INTRODUCTION: _WORK | {Phase.FOLLOW_UP, Phase.FINAL_EVALUATION},
    Phase.TECHNICAL_QUESTION: _WORK | {Phase.FOLLOW_UP, Phase.FINAL_EVALUATION},
    Phase.FOLLOW_UP: _WORK | {Phase.FOLLOW_UP, Phase.FINAL_EVALUATION},
    Phase.CODING: {Phase.CODE_REVIEW, Phase.FINAL_EVALUATION} | _WORK,
    Phase.CODE_REVIEW: _WORK | {Phase.FOLLOW_UP, Phase.FINAL_EVALUATION},
    Phase.SYSTEM_DESIGN: _WORK | {Phase.FOLLOW_UP, Phase.FINAL_EVALUATION},
    Phase.BEHAVIORAL: _WORK | {Phase.FOLLOW_UP, Phase.FINAL_EVALUATION},
    Phase.FINAL_EVALUATION: {Phase.COMPLETED},
    Phase.COMPLETED: set(),
}

ROUND_PHASE = {
    "introduction": Phase.INTRODUCTION,
    "technical": Phase.TECHNICAL_QUESTION,
    "coding": Phase.CODING,
    "sql": Phase.CODING,
    "system_design": Phase.SYSTEM_DESIGN,
    "behavioral": Phase.BEHAVIORAL,
}


class InvalidTransition(Exception):
    pass


def can_transition(src: Phase, dst: Phase) -> bool:
    return dst in TRANSITIONS.get(src, set())


def assert_transition(src: Phase, dst: Phase) -> None:
    if not can_transition(src, dst):
        raise InvalidTransition(f"{src} -> {dst} is not allowed")
