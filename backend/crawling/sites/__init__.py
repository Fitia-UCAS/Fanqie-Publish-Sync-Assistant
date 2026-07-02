from __future__ import annotations

from backend.crawling.sites.lanmeiwen import LanmeiwenAdapter
from backend.crawling.sites.renrenreshu import RenrenreshuAdapter
from backend.crawling.sites.xsbook import XsbookAdapter
from backend.crawling.sites.adapter_contract import NovelSiteAdapter
from backend.crawling.sites.registry import ADAPTER_TYPES, adapter_for_url, supported_sites

__all__ = [
    "ADAPTER_TYPES",
    "LanmeiwenAdapter",
    "XsbookAdapter",
    "NovelSiteAdapter",
    "RenrenreshuAdapter",
    "adapter_for_url",
    "supported_sites",
]
