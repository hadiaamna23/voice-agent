import json
import logging
import os
import time
from typing import Any, Dict, List, Optional

import httpx
from jose import jwt

logger = logging.getLogger("backend.services.crm_service")
GOOGLE_SERVICE_ACCOUNT_INFO = os.getenv("GOOGLE_SHEETS_SERVICE_ACCOUNT_JSON")
SPREADSHEET_ID = os.getenv("GOOGLE_SHEETS_SPREADSHEET_ID")
SHEETS_SCOPE = "https://www.googleapis.com/auth/spreadsheets"
TOKEN_URI = "https://oauth2.googleapis.com/token"
BASE_SHEETS_URL = "https://sheets.googleapis.com/v4/spreadsheets"


class CRMService:
    def __init__(self) -> None:
        if not GOOGLE_SERVICE_ACCOUNT_INFO:
            raise ValueError("GOOGLE_SHEETS_SERVICE_ACCOUNT_JSON must be set")
        if not SPREADSHEET_ID:
            raise ValueError("GOOGLE_SHEETS_SPREADSHEET_ID must be set")
        self.service_account = self._load_service_account()
        self.access_token: Optional[str] = None
        self.token_expiry: float = 0

    def _load_service_account(self) -> Dict[str, Any]:
        try:
            return json.loads(GOOGLE_SERVICE_ACCOUNT_INFO)
        except json.JSONDecodeError:
            with open(GOOGLE_SERVICE_ACCOUNT_INFO, "r", encoding="utf-8") as handle:
                return json.load(handle)

    def _get_access_token(self) -> str:
        now = int(time.time())
        if self.access_token and now < self.token_expiry - 60:
            return self.access_token

        payload = {
            "iss": self.service_account["client_email"],
            "scope": SHEETS_SCOPE,
            "aud": TOKEN_URI,
            "exp": now + 3600,
            "iat": now,
        }
        private_key = self.service_account["private_key"]
        assertion = jwt.encode(payload, private_key, algorithm="RS256")
        response = httpx.post(
            TOKEN_URI,
            data={
                "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
                "assertion": assertion,
            },
            timeout=60.0,
        )
        response.raise_for_status()
        token_response = response.json()
        self.access_token = token_response["access_token"]
        self.token_expiry = now + int(token_response.get("expires_in", 3600))
        return self.access_token

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self._get_access_token()}",
            "Content-Type": "application/json",
        }

    def _sheet_range(self, sheet_name: str) -> str:
        return f"{sheet_name}!A1:E"

    def add_lead(
        self,
        name: str,
        email: str,
        phone: Optional[str] = None,
        company: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        values = [[
            name,
            email,
            phone or "",
            company or "",
            json.dumps(metadata or {}),
        ]]
        endpoint = f"{BASE_SHEETS_URL}/{SPREADSHEET_ID}/values/Leads!A:E:append"
        response = httpx.post(
            endpoint,
            headers=self._headers(),
            params={"valueInputOption": "RAW", "insertDataOption": "INSERT_ROWS"},
            json={"values": values},
            timeout=60.0,
        )
        response.raise_for_status()
        logger.info("Added lead %s to Google Sheets", email)
        return response.json()

    def list_contacts(self) -> List[Dict[str, Any]]:
        endpoint = f"{BASE_SHEETS_URL}/{SPREADSHEET_ID}/values/Leads!A:E"
        response = httpx.get(endpoint, headers=self._headers(), timeout=60.0)
        response.raise_for_status()
        payload = response.json()
        rows = payload.get("values", [])[1:]
        contacts = []
        for row in rows:
            contacts.append({
                "name": row[0] if len(row) > 0 else "",
                "email": row[1] if len(row) > 1 else "",
                "phone": row[2] if len(row) > 2 else "",
                "company": row[3] if len(row) > 3 else "",
                "metadata": json.loads(row[4]) if len(row) > 4 and row[4] else {},
            })
        return contacts

    def update_contact(self, email: str, metadata: Dict[str, Any]) -> Dict[str, Any]:
        contacts = self.list_contacts()
        for index, contact in enumerate(contacts, start=2):
            if contact["email"].lower() == email.lower():
                values = [[
                    contact["name"],
                    contact["email"],
                    contact.get("phone", ""),
                    contact.get("company", ""),
                    json.dumps({**contact.get("metadata", {}), **metadata}),
                ]]
                endpoint = f"{BASE_SHEETS_URL}/{SPREADSHEET_ID}/values/Leads!A{index}:E{index}"
                response = httpx.put(endpoint, headers=self._headers(), params={"valueInputOption": "RAW"}, json={"values": values}, timeout=60.0)
                response.raise_for_status()
                logger.info("Updated contact %s in Google Sheets", email)
                return response.json()
        raise ValueError(f"Contact with email {email} not found")

    def save_lead_webhook(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        lead = payload.get("lead", payload)
        return self.add_lead(
            name=lead.get("name", "Unknown"),
            email=lead.get("email", ""),
            phone=lead.get("phone"),
            company=lead.get("company"),
            metadata=lead.get("metadata", {}),
        )

    def send_webhook_notification(self, webhook_url: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        response = httpx.post(webhook_url, json=payload, timeout=60.0)
        response.raise_for_status()
        return response.json()
