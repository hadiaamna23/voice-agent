from typing import Dict, Optional

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models import CrmLead
from app.db.session import AsyncSessionLocal


class CRMService:
    async def create_lead(self, user_id: int, name: str, email: str, phone: Optional[str] = None, company: Optional[str] = None, metadata: Optional[Dict[str, str]] = None) -> Dict[str, str]:
        url = f"{settings.crm_base_url.rstrip('/')}/leads"
        payload = {
            "name": name,
            "email": email,
            "phone": phone,
            "company": company,
            "metadata": metadata or {},
        }

        headers = {
            "Authorization": f"Bearer {settings.crm_api_key}",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, json=payload, headers=headers)
            response.raise_for_status()
            crm_data = response.json()

        external_id = crm_data.get("id", crm_data.get("lead_id", "unknown"))
        status = crm_data.get("status", "created")

        async with AsyncSessionLocal() as session:
            lead = CrmLead(user_id=user_id, external_id=external_id, status=status, metadata=crm_data)
            session.add(lead)
            await session.commit()

        return {"external_id": external_id, "status": status}

    async def sync_lead(self, user_id: int, external_id: str, status: str) -> Dict[str, str]:
        url = f"{settings.crm_base_url.rstrip('/')}/leads/{external_id}"
        headers = {
            "Authorization": f"Bearer {settings.crm_api_key}",
            "Content-Type": "application/json",
        }
        payload = {"status": status}

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.patch(url, json=payload, headers=headers)
            response.raise_for_status()
            crm_data = response.json()

        return {"external_id": external_id, "status": crm_data.get("status", status)}
