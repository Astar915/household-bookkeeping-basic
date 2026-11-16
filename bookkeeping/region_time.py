"""Account-local calendar and clock helpers for the web ledger."""
from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo


DEFAULT_TIME_ZONE = "Asia/Tokyo"
TIME_ZONE_CHOICES = (
    "Asia/Tokyo",
    "Asia/Shanghai",
    "Asia/Hong_Kong",
    "Asia/Taipei",
    "Asia/Seoul",
    "Asia/Singapore",
    "Asia/Bangkok",
    "Asia/Dubai",
    "Europe/London",
    "Europe/Paris",
    "America/Los_Angeles",
    "America/Chicago",
    "America/New_York",
    "Australia/Sydney",
    "Pacific/Auckland",
)
SUPPORTED_TIME_ZONES = frozenset(TIME_ZONE_CHOICES)


def normalize_time_zone(value: object) -> str:
    candidate = str(value or "").strip()
    return candidate if candidate in SUPPORTED_TIME_ZONES else DEFAULT_TIME_ZONE


def region_label(value: object, language: str = "zh-CN") -> str:
    labels = {
        "Asia/Tokyo": ("日本·东京", "日本・東京", "Japan · Tokyo"),
        "Asia/Shanghai": ("中国大陆·上海", "中国本土・上海", "Mainland China · Shanghai"),
        "Asia/Hong_Kong": ("中国香港", "香港", "Hong Kong"),
        "Asia/Taipei": ("中国台湾·台北", "台湾・台北", "Taiwan · Taipei"),
        "Asia/Seoul": ("韩国·首尔", "韓国・ソウル", "South Korea · Seoul"),
        "Asia/Singapore": ("新加坡", "シンガポール", "Singapore"),
        "Asia/Bangkok": ("泰国·曼谷", "タイ・バンコク", "Thailand · Bangkok"),
        "Asia/Dubai": ("阿联酋·迪拜", "UAE・ドバイ", "UAE · Dubai"),
        "Europe/London": ("英国·伦敦", "英国・ロンドン", "UK · London"),
        "Europe/Paris": ("中欧·巴黎", "中央ヨーロッパ・パリ", "Central Europe · Paris"),
        "America/Los_Angeles": ("美国西部·洛杉矶", "米国西部・ロサンゼルス", "US Pacific · Los Angeles"),
        "America/Chicago": ("美国中部·芝加哥", "米国中部・シカゴ", "US Central · Chicago"),
        "America/New_York": ("美国东部·纽约", "米国東部・ニューヨーク", "US Eastern · New York"),
        "Australia/Sydney": ("澳大利亚东部·悉尼", "オーストラリア東部・シドニー", "Australia Eastern · Sydney"),
        "Pacific/Auckland": ("新西兰·奥克兰", "ニュージーランド・オークランド", "New Zealand · Auckland"),
    }
    language_index = {"zh-CN": 0, "ja-JP": 1, "en-US": 2}.get(language, 0)
    return labels.get(normalize_time_zone(value), labels[DEFAULT_TIME_ZONE])[language_index]


def is_supported_time_zone(value: object) -> bool:
    return isinstance(value, str) and value in SUPPORTED_TIME_ZONES


def region_timezone(value: object = None) -> ZoneInfo:
    return ZoneInfo(normalize_time_zone(value))


def regional_now(value: object = None) -> datetime:
    return datetime.now(timezone.utc).astimezone(region_timezone(value))


def regional_today(value: object = None) -> str:
    return regional_now(value).date().isoformat()
