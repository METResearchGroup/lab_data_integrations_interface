from __future__ import annotations

import pytest

from data_platform.utils.storage import BlueskyStorageManager, StorageStage
from tests.data_platform.constants import VALID_DATASET_ID


@pytest.fixture
def bluesky_storage(data_root) -> BlueskyStorageManager:
    return BlueskyStorageManager(StorageStage.RAW, VALID_DATASET_ID)
