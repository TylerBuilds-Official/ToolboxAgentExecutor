from dataclasses import dataclass
from typing import Optional


@dataclass
class UpdateInfo:
    version: str
    force: bool
    changelog: str
    download_url: str
    checksum: Optional[str] = None
    min_version: Optional[str] = None