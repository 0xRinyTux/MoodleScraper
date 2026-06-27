from dataclasses import dataclass
from typing import List

@dataclass
class DownloadItem:
    url: str
    section_path: str
    file_prefix: str
    is_direct: bool = False
    exact_path: str = ""

@dataclass
class Section:
    name: str
    downloads: List[DownloadItem]
