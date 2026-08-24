import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from tinydb import TinyDB

from config import get_settings


class DatabaseManager:
    """Manager class for TinyDB storage operations."""

    def __init__(self, db_path: Optional[str] = None, table_name: str = "records"):
        if db_path is None:
            settings = get_settings()
            db_path = settings.DB_PATH

        self.db_path = db_path
        self.table_name = table_name
        self._ensure_db_dir()
        self.db = TinyDB(self.db_path)
        self.table = self.db.table(self.table_name)

    def _ensure_db_dir(self) -> None:
        """Ensures that the directory for the database file exists."""
        db_file = Path(self.db_path)
        if db_file.parent and str(db_file.parent) != "." and not db_file.parent.exists():
            db_file.parent.mkdir(parents=True, exist_ok=True)

    def insert_record(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Inserts a new payload into the database.
        Automatically attaches 'created_at' UTC ISO timestamp and returns the record with 'id'.
        """
        record_data = dict(payload)
        if "created_at" not in record_data:
            record_data["created_at"] = datetime.now(timezone.utc).isoformat()

        doc_id = self.table.insert(record_data)
        record_data["id"] = doc_id
        self.table.update({"id": doc_id}, doc_ids=[doc_id])
        return record_data

    def get_latest(self) -> Optional[Dict[str, Any]]:
        """
        Retrieves the single most recently inserted document.
        Returns None if the database table is empty.
        """
        all_docs = self.table.all()
        if not all_docs:
            return None
        latest_doc = max(all_docs, key=lambda d: d.doc_id)
        result = dict(latest_doc)
        result["id"] = latest_doc.doc_id
        return result

    def get_by_id(self, doc_id: int) -> Optional[Dict[str, Any]]:
        """
        Retrieves a document by its integer doc_id.
        """
        doc = self.table.get(doc_id=doc_id)
        if doc is None:
            return None
        result = dict(doc)
        result["id"] = doc.doc_id
        return result

    def delete_by_id(self, doc_id: int) -> bool:
        """
        Deletes a single document by its integer doc_id.
        Returns True if deleted, False if not found.
        """
        doc = self.table.get(doc_id=doc_id)
        if doc is None:
            return False
        self.table.remove(doc_ids=[doc_id])
        return True

    def delete_all(self) -> int:
        """
        Deletes all documents from the table (clears/purges the dataset).
        Returns the number of deleted documents.
        """
        all_docs = self.table.all()
        count = len(all_docs)
        self.table.truncate()
        return count

    def get_db_file_path(self) -> Path:
        """
        Returns the resolved absolute Path to the current TinyDB database file.
        """
        return Path(self.db_path).resolve()

    def sync_records(
        self,
        since: Optional[datetime] = None,
        after_id: Optional[int] = None,
        ids: Optional[List[int]] = None,
        fields: Optional[List[str]] = None,
        limit: Optional[int] = None,
        offset: int = 0,
    ) -> Tuple[List[Dict[str, Any]], int]:
        """
        Fetches records with sync / bulk / pluck capabilities.
        - since: ISO datetime filter (records with created_at >= since)
        - after_id: records with id > after_id (cursor-based incremental sync)
        - ids: records whose id is in the provided list
        - fields: plucks only specified keys from records
        - limit / offset: pagination controls
        """
        docs = self.table.all()

        formatted_docs = []
        for doc in docs:
            item = dict(doc)
            item["id"] = doc.doc_id
            formatted_docs.append(item)

        # Sort by doc_id ascending for consistent sync ordering
        formatted_docs.sort(key=lambda d: d["id"])

        # Filter by specific IDs
        if ids is not None:
            id_set = set(ids)
            formatted_docs = [d for d in formatted_docs if d["id"] in id_set]

        # Filter by after_id (incremental sync)
        if after_id is not None:
            formatted_docs = [d for d in formatted_docs if d["id"] > after_id]

        # Filter by since timestamp
        if since is not None:
            since_utc = since.astimezone(timezone.utc) if since.tzinfo else since.replace(tzinfo=timezone.utc)
            filtered = []
            for d in formatted_docs:
                created_at_str = d.get("created_at")
                if created_at_str:
                    try:
                        dt = datetime.fromisoformat(created_at_str)
                        if dt.tzinfo is None:
                            dt = dt.replace(tzinfo=timezone.utc)
                        else:
                            dt = dt.astimezone(timezone.utc)
                        if dt >= since_utc:
                            filtered.append(d)
                    except ValueError:
                        filtered.append(d)
                else:
                    filtered.append(d)
            formatted_docs = filtered

        total_count = len(formatted_docs)

        # Apply pagination
        if offset > 0:
            formatted_docs = formatted_docs[offset:]
        if limit is not None and limit >= 0:
            formatted_docs = formatted_docs[:limit]

        # Pluck fields if requested
        if fields:
            field_set = set(fields)
            plucked_docs = []
            for doc in formatted_docs:
                plucked = {k: v for k, v in doc.items() if k in field_set}
                plucked_docs.append(plucked)
            return plucked_docs, total_count

        return formatted_docs, total_count

    def close(self) -> None:
        """Closes the TinyDB instance."""
        self.db.close()


# Default singleton instance
db_manager = DatabaseManager()


def get_db() -> DatabaseManager:
    """Dependency provider for FastAPI routes."""
    return db_manager
