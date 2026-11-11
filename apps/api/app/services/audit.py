from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AnalyticsEvent, AuditLog


def audit(
    db: AsyncSession,
    action: str,
    actor_id: uuid.UUID | None,
    organization_id: uuid.UUID | None = None,
    target_type: str = "",
    target_id: str = "",
    ip: str = "",
    **details: Any,
) -> None:
    db.add(AuditLog(action=action, actor_id=actor_id, organization_id=organization_id, target_type=target_type, target_id=target_id, ip=ip, details=details))


def track(
    db: AsyncSession,
    event: str,
    user_id: uuid.UUID | None = None,
    organization_id: uuid.UUID | None = None,
    interview_id: uuid.UUID | None = None,
    **properties: Any,
) -> None:
    db.add(AnalyticsEvent(event=event, user_id=user_id, organization_id=organization_id, interview_id=interview_id, properties=properties))
