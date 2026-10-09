from abc import ABC, abstractmethod
from pathlib import Path
from typing import Union


class BaseStorageService(ABC):
    @abstractmethod
    def save_file(self, content: bytes, storage_key: str) -> str:
        """Save file bytes and return storage path / identifier."""
        pass

    @abstractmethod
    def get_file(self, storage_key: str) -> bytes:
        """Retrieve file bytes by storage key."""
        pass

    @abstractmethod
    def file_exists(self, storage_key: str) -> bool:
        """Check if file exists in storage."""
        pass

    @abstractmethod
    def get_file_path(self, storage_key: str) -> Path:
        """Return Path object for streaming or reading."""
        pass

    @abstractmethod
    def delete_file(self, storage_key: str) -> bool:
        """Delete file by storage key."""
        pass
