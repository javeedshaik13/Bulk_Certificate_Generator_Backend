import os
import tempfile
from pathlib import Path
from app.core.config import settings
from app.core.logging import logger
from app.storage.base import BaseStorageService


class LocalStorageService(BaseStorageService):
    def __init__(self, base_dir: str = None):
        self.base_dir = Path(base_dir or settings.STORAGE_BASE_DIR).resolve()
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _resolve_safe_path(self, storage_key: str) -> Path:
        # Strip leading slashes to prevent root-relative override
        clean_key = storage_key.lstrip("/\\")
        target_path = (self.base_dir / clean_key).resolve()
        
        # Verify target is strictly within base_dir (prevent path traversal)
        try:
            target_path.relative_to(self.base_dir)
        except ValueError:
            logger.error("Path traversal attempt detected with key: %s", storage_key)
            raise ValueError(f"Security error: Invalid storage key '{storage_key}' outside storage directory.")
        return target_path

    def save_file(self, content: bytes, storage_key: str) -> str:
        target_path = self._resolve_safe_path(storage_key)
        target_path.parent.mkdir(parents=True, exist_ok=True)

        # Atomic write: write to temp file then rename
        temp_fd, temp_file_path = tempfile.mkstemp(
            prefix=".tmp_cert_",
            dir=str(target_path.parent)
        )
        try:
            with os.fdopen(temp_fd, "wb") as f:
                f.write(content)
                f.flush()
                os.fsync(f.fileno())
            os.replace(temp_file_path, str(target_path))
        except Exception:
            if os.path.exists(temp_file_path):
                try:
                    os.remove(temp_file_path)
                except OSError:
                    pass
            raise

        logger.debug("Safely saved file at %s (%d bytes)", target_path, len(content))
        return str(target_path)

    def get_file(self, storage_key: str) -> bytes:
        target_path = self._resolve_safe_path(storage_key)
        if not target_path.exists() or not target_path.is_file():
            raise FileNotFoundError(f"Storage file not found: {storage_key}")
        with open(target_path, "rb") as f:
            return f.read()

    def file_exists(self, storage_key: str) -> bool:
        try:
            target_path = self._resolve_safe_path(storage_key)
            return target_path.exists() and target_path.is_file()
        except ValueError:
            return False

    def get_file_path(self, storage_key: str) -> Path:
        target_path = self._resolve_safe_path(storage_key)
        if not target_path.exists() or not target_path.is_file():
            raise FileNotFoundError(f"Storage file not found: {storage_key}")
        return target_path

    def delete_file(self, storage_key: str) -> bool:
        try:
            target_path = self._resolve_safe_path(storage_key)
            if target_path.exists():
                target_path.unlink()
                return True
            return False
        except Exception as e:
            logger.error("Failed to delete storage file %s: %s", storage_key, e)
            return False


storage_service = LocalStorageService()
