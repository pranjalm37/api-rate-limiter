import pytest

from app.storage.memory import MemoryStore


@pytest.fixture
def store() -> MemoryStore:
    return MemoryStore()
