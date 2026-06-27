from datetime import datetime
from typing import Any, Dict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Workflow
from app.db.session import AsyncSessionLocal
from app.services.analytics import AnalyticsService
from app.services.crm import CRMService


class WorkflowService:
    def __init__(self) -> None:
        self.analytics_service = AnalyticsService()
        self.crm_service = CRMService()

    async def execute_trigger(self, user_id: int, trigger_type: str, payload: Dict[str, Any]) -> None:
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(Workflow).where(Workflow.user_id == user_id, Workflow.trigger_type == trigger_type, Workflow.active == True)
            )
            workflows = result.scalars().all()
            for workflow in workflows:
                if trigger_type == "call_completed":
                    await self._run_call_completed(workflow, payload)
                elif trigger_type == "new_lead":
                    await self._run_new_lead(workflow, payload)
                workflow.last_run_at = datetime.utcnow()
            await session.commit()

    async def _run_call_completed(self, workflow: Workflow, payload: Dict[str, Any]) -> None:
        metadata = workflow.config.get("metadata", {})
        lead_name = payload.get("customer_name") or payload.get("caller") or "Voice Contact"
        email = payload.get("email", metadata.get("default_email", "contact@example.com"))
        phone = payload.get("phone")
        company = payload.get("company")
        await self.crm_service.create_lead(
            user_id=workflow.user_id,
            name=lead_name,
            email=email,
            phone=phone,
            company=company,
            metadata={**metadata, **payload},
        )
        await self.analytics_service.record_event(workflow.user_id, "workflow_call_completed", {"workflow_id": workflow.id})

    async def _run_new_lead(self, workflow: Workflow, payload: Dict[str, Any]) -> None:
        email = payload.get("email")
        if not email:
            return
        await self.crm_service.create_lead(
            user_id=workflow.user_id,
            name=payload.get("name", "Prospective Contact"),
            email=email,
            phone=payload.get("phone"),
            company=payload.get("company"),
            metadata=payload,
        )
        await self.analytics_service.record_event(workflow.user_id, "workflow_new_lead", {"workflow_id": workflow.id})
