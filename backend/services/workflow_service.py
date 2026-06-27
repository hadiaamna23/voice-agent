import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger("backend.services.workflow_service")
WORKFLOW_STORE_PATH = Path(__file__).resolve().parent.parent / "data" / "workflows.json"
WORKFLOW_STORE_PATH.parent.mkdir(parents=True, exist_ok=True)


class WorkflowService:
    def __init__(self) -> None:
        self.workflows = self._load_workflows()
        self.handlers: Dict[str, Callable[[Dict[str, Any]], Any]] = {}

    def register_handler(self, trigger_type: str, handler: Callable[[Dict[str, Any]], Any]) -> None:
        self.handlers[trigger_type] = handler
        logger.info("Registered workflow handler for trigger=%s", trigger_type)

    def create_workflow(self, name: str, trigger_type: str, action_type: str, config: Dict[str, Any]) -> Dict[str, Any]:
        workflow_id = f"wf_{int(datetime.now(timezone.utc).timestamp() * 1000)}"
        workflow = {
            "id": workflow_id,
            "name": name,
            "trigger_type": trigger_type,
            "action_type": action_type,
            "config": config,
            "active": True,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        self.workflows[workflow_id] = workflow
        self._persist_workflows()
        return workflow

    def list_workflows(self) -> List[Dict[str, Any]]:
        return list(self.workflows.values())

    def get_workflow(self, workflow_id: str) -> Optional[Dict[str, Any]]:
        return self.workflows.get(workflow_id)

    def delete_workflow(self, workflow_id: str) -> None:
        if workflow_id in self.workflows:
            del self.workflows[workflow_id]
            self._persist_workflows()

    def execute_trigger(self, trigger_type: str, payload: Dict[str, Any]) -> List[Dict[str, Any]]:
        matched = [wf for wf in self.workflows.values() if wf["trigger_type"] == trigger_type and wf["active"]]
        results: List[Dict[str, Any]] = []
        for workflow in matched:
            action_type = workflow.get("action_type")
            config = workflow.get("config", {})
            try:
                if action_type == "webhook":
                    result = self._execute_webhook(config, payload)
                elif action_type == "follow_up":
                    result = self._execute_follow_up(workflow, payload)
                elif action_type == "custom_handler":
                    result = self._execute_custom_handler(config, payload)
                else:
                    result = {"status": "skipped", "reason": "unknown action"}
                results.append({"workflow_id": workflow["id"], "result": result})
            except Exception as exc:
                logger.exception("Workflow execution failed for %s: %s", workflow["id"], exc)
                results.append({"workflow_id": workflow["id"], "error": str(exc)})
        return results

    def _execute_webhook(self, config: Dict[str, Any], payload: Dict[str, Any]) -> Dict[str, Any]:
        url = config.get("webhook_url")
        if not url:
            raise ValueError("Missing webhook_url in workflow configuration")
        import httpx

        response = httpx.post(url, json={"trigger": config.get("trigger_type"), "payload": payload})
        response.raise_for_status()
        return {"status": "webhook_called", "status_code": response.status_code}

    def _execute_follow_up(self, workflow: Dict[str, Any], payload: Dict[str, Any]) -> Dict[str, Any]:
        follow_up = workflow.get("config", {}).get("follow_up_message")
        delay = workflow.get("config", {}).get("delay_seconds", 60)
        if not follow_up:
            raise ValueError("Missing follow_up_message in workflow configuration")
        logger.info("Scheduled follow-up for workflow=%s delay=%s", workflow["id"], delay)
        return {
            "status": "follow_up_scheduled",
            "message": follow_up,
            "delay_seconds": delay,
            "payload": payload,
        }

    def _execute_custom_handler(self, config: Dict[str, Any], payload: Dict[str, Any]) -> Dict[str, Any]:
        handler_name = config.get("handler_name")
        if not handler_name or handler_name not in self.handlers:
            raise ValueError("Custom handler not configured or registered")
        handler = self.handlers[handler_name]
        result = handler(payload)
        return {"status": "custom_handler_called", "result": result}

    def _persist_workflows(self) -> None:
        with open(WORKFLOW_STORE_PATH, "w", encoding="utf-8") as handle:
            json.dump(self.workflows, handle, indent=2)

    def _load_workflows(self) -> Dict[str, Dict[str, Any]]:
        if not WORKFLOW_STORE_PATH.exists():
            return {}
        with open(WORKFLOW_STORE_PATH, "r", encoding="utf-8") as handle:
            return json.load(handle)
