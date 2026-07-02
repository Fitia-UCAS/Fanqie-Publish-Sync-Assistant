from __future__ import annotations

from backend.crawling.sites.lanmeiwen import LanmeiwenAdapter
from backend.crawling.sites.renrenreshu import RenrenreshuAdapter
from backend.crawling.sites.adapter_contract import NovelSiteAdapter
from backend.crawling.sites.xsbook import XsbookAdapter

ADAPTER_TYPES: tuple[type[NovelSiteAdapter], ...] = (
    LanmeiwenAdapter,
    RenrenreshuAdapter,
    XsbookAdapter,
)


def adapter_for_url(url: str) -> type[NovelSiteAdapter] | None:
    for adapter_type in ADAPTER_TYPES:
        if adapter_type.supports(url):
            return adapter_type
    return None


def supported_sites() -> list[dict[str, str]]:
    return [
        {
            "key": adapter.site_key,
            "name": adapter.site_name,
            "domains": "、".join(adapter.domains),
        }
        for adapter in ADAPTER_TYPES
    ]
