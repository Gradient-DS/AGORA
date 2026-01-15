from typing import Optional, Dict, Any, List
from datetime import datetime
import uuid
import logging
from .file_storage import FileStorage

logger = logging.getLogger(__name__)


class SessionManager:
    def __init__(self, storage: FileStorage):
        self.storage = storage
        self.active_sessions: Dict[str, Dict[str, Any]] = {}
    
    def create_session(
        self,
        session_id: str,
        company_id: Optional[str] = None,
        company_name: Optional[str] = None,
        inspector_name: Optional[str] = None,
        inspector_email: Optional[str] = None,
    ) -> Dict[str, Any]:
        report_id = f"HAP-{datetime.now().strftime('%Y%m%d')}-{str(uuid.uuid4())[:8].upper()}"

        session_data = {
            "session_id": session_id,
            "report_id": report_id,
            "company_id": company_id,
            "company_name": company_name,
            "inspector_name": inspector_name,
            "inspector_email": inspector_email,
            "created_at": datetime.now().isoformat(),
            "status": "initialized",
            "phase": "data_extraction",
        }
        
        self.active_sessions[session_id] = session_data
        
        draft_data = {
            "metadata": session_data,
            "conversation_history": [],
            "extracted_data": {},
            "verification_questions": [],
            "verification_answers": [],
        }
        
        self.storage.save_draft(session_id, draft_data)
        
        logger.info(f"Created new inspection session {session_id} with report ID {report_id}")
        return session_data
    
    def update_session_status(self, session_id: str, status: str, phase: Optional[str] = None) -> None:
        if session_id in self.active_sessions:
            self.active_sessions[session_id]["status"] = status
            if phase:
                self.active_sessions[session_id]["phase"] = phase
            self.active_sessions[session_id]["updated_at"] = datetime.now().isoformat()
    
    def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        if session_id in self.active_sessions:
            return self.active_sessions[session_id]

        draft = self.storage.load_draft(session_id)
        if draft and "metadata" in draft:
            self.active_sessions[session_id] = draft["metadata"]
            return draft["metadata"]

        return None

    def _save_session(self, session_id: str, session_data: Dict[str, Any]) -> None:
        """Save updated session data to both memory and storage."""
        session_data["updated_at"] = datetime.now().isoformat()
        self.active_sessions[session_id] = session_data

        draft = self.storage.load_draft(session_id)
        if draft:
            draft["metadata"] = session_data
            draft["last_updated"] = datetime.now().isoformat()
            self.storage.save_draft(session_id, draft)
    
    def store_conversation(self, session_id: str, messages: List[Dict[str, str]]) -> None:
        self.storage.save_conversation_history(session_id, messages)
        
        draft = self.storage.load_draft(session_id)
        if draft:
            draft["conversation_history"] = messages
            draft["last_updated"] = datetime.now().isoformat()
            self.storage.save_draft(session_id, draft)
    
    def update_extracted_data(self, session_id: str, extracted_data: Dict[str, Any]) -> None:
        draft = self.storage.load_draft(session_id)
        if not draft:
            draft = {"metadata": self.get_session(session_id)}
        
        draft["extracted_data"] = extracted_data
        draft["last_updated"] = datetime.now().isoformat()
        self.storage.save_draft(session_id, draft)
    
    def add_verification_questions(self, session_id: str, questions: List[str]) -> None:
        draft = self.storage.load_draft(session_id)
        if not draft:
            return
        
        draft["verification_questions"] = questions
        draft["last_updated"] = datetime.now().isoformat()
        self.storage.save_draft(session_id, draft)
    
    def add_verification_answers(self, session_id: str, answers: Dict[str, Any]) -> None:
        draft = self.storage.load_draft(session_id)
        if not draft:
            return
        
        if "verification_answers" not in draft:
            draft["verification_answers"] = []
        
        draft["verification_answers"].append({
            "timestamp": datetime.now().isoformat(),
            "answers": answers
        })
        draft["last_updated"] = datetime.now().isoformat()
        self.storage.save_draft(session_id, draft)
    
    def finalize_report(self, session_id: str, report_data: Dict[str, Any], pdf_content: bytes) -> Dict[str, str]:
        json_path = self.storage.save_final_report(session_id, report_data)
        pdf_path = self.storage.save_pdf(session_id, pdf_content)
        
        self.update_session_status(session_id, "completed", "finalized")
        
        logger.info(f"Finalized report for session {session_id}")
        
        return {
            "json_path": json_path,
            "pdf_path": pdf_path,
            "report_id": report_data.get("metadata", {}).get("report_id", "unknown")
        }
    
    def get_report_status(self, session_id: str) -> Dict[str, Any]:
        session = self.get_session(session_id)
        draft = self.storage.load_draft(session_id)
        paths = self.storage.get_report_paths(session_id)
        
        if not session and not draft:
            return {
                "exists": False,
                "status": "not_found"
            }
        
        completion = 0.0
        if draft and "extracted_data" in draft:
            total = 0
            filled = 0
            for key, value in draft["extracted_data"].items():
                if isinstance(value, dict):
                    for k, v in value.items():
                        total += 1
                        if v is not None:
                            filled += 1
            if total > 0:
                completion = (filled / total) * 100
        
        return {
            "exists": True,
            "session_id": session_id,
            "report_id": session.get("report_id") if session else None,
            "status": session.get("status", "unknown") if session else "draft",
            "phase": session.get("phase", "unknown") if session else "unknown",
            "completion_percentage": completion,
            "has_draft": paths["draft"] is not None,
            "has_final": paths["final_json"] is not None,
            "has_pdf": paths["final_pdf"] is not None,
            "paths": paths,
        }

