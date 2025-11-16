import json
import os
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class FileStorage:
    def __init__(self, base_path: str = "./storage"):
        self.base_path = Path(base_path)
        self.reports_path = self.base_path / "reports"
        self.conversation_path = self.base_path / "conversation_history"
        self._ensure_directories()
    
    def _ensure_directories(self) -> None:
        self.reports_path.mkdir(parents=True, exist_ok=True)
        self.conversation_path.mkdir(parents=True, exist_ok=True)
    
    def _get_session_dir(self, session_id: str) -> Path:
        session_dir = self.reports_path / session_id
        session_dir.mkdir(parents=True, exist_ok=True)
        return session_dir
    
    def save_draft(self, session_id: str, data: Dict[str, Any]) -> str:
        session_dir = self._get_session_dir(session_id)
        draft_path = session_dir / "draft_data.json"
        
        data["last_updated"] = datetime.now().isoformat()
        
        with open(draft_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        
        logger.info(f"Saved draft report for session {session_id}")
        return str(draft_path)
    
    def load_draft(self, session_id: str) -> Optional[Dict[str, Any]]:
        draft_path = self._get_session_dir(session_id) / "draft_data.json"
        
        if not draft_path.exists():
            return None
        
        with open(draft_path, "r", encoding="utf-8") as f:
            return json.load(f)
    
    def save_final_report(self, session_id: str, report_data: Dict[str, Any]) -> str:
        session_dir = self._get_session_dir(session_id)
        final_path = session_dir / "final_report.json"
        
        with open(final_path, "w", encoding="utf-8") as f:
            json.dump(report_data, f, indent=2, ensure_ascii=False)
        
        logger.info(f"Saved final report for session {session_id}")
        return str(final_path)
    
    def save_pdf(self, session_id: str, pdf_content: bytes) -> str:
        session_dir = self._get_session_dir(session_id)
        pdf_path = session_dir / "final_report.pdf"
        
        with open(pdf_path, "wb") as f:
            f.write(pdf_content)
        
        logger.info(f"Saved PDF report for session {session_id}")
        return str(pdf_path)
    
    def save_conversation_history(self, session_id: str, history: list) -> str:
        conv_path = self.conversation_path / f"{session_id}.json"
        
        data = {
            "session_id": session_id,
            "saved_at": datetime.now().isoformat(),
            "messages": history
        }
        
        with open(conv_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        
        logger.info(f"Saved conversation history for session {session_id}")
        return str(conv_path)
    
    def load_conversation_history(self, session_id: str) -> Optional[list]:
        conv_path = self.conversation_path / f"{session_id}.json"
        
        if not conv_path.exists():
            return None
        
        with open(conv_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data.get("messages", [])
    
    def get_report_paths(self, session_id: str) -> Dict[str, Optional[str]]:
        session_dir = self._get_session_dir(session_id)
        
        draft_path = session_dir / "draft_data.json"
        final_path = session_dir / "final_report.json"
        pdf_path = session_dir / "final_report.pdf"
        
        return {
            "draft": str(draft_path) if draft_path.exists() else None,
            "final_json": str(final_path) if final_path.exists() else None,
            "final_pdf": str(pdf_path) if pdf_path.exists() else None,
        }
    
    def session_exists(self, session_id: str) -> bool:
        session_dir = self.reports_path / session_id
        return session_dir.exists()
    
    def delete_session(self, session_id: str) -> bool:
        import shutil
        session_dir = self.reports_path / session_id
        conv_file = self.conversation_path / f"{session_id}.json"
        
        deleted = False
        
        if session_dir.exists():
            shutil.rmtree(session_dir)
            deleted = True
        
        if conv_file.exists():
            conv_file.unlink()
            deleted = True
        
        if deleted:
            logger.info(f"Deleted session data for {session_id}")
        
        return deleted

