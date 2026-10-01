"""Resolve and localize the persisted interface language."""

import logging
import threading

from sqlalchemy.orm import Session

from src.platform.persistence.models import AppSettings

SUPPORTED_LANGUAGES = frozenset({"zh-TW", "zh-CN", "en-US"})
DEFAULT_LANGUAGE = "zh-TW"
logger = logging.getLogger(__name__)
_opencc = None
_opencc_lock = threading.Lock()
_opencc_warned = False

POSTPROCESS = (
    ("臺", "台"), ("賬", "帳"), ("日志", "日誌"), ("質量", "品質"), ("智慧體", "智慧代理"), ("盯盤俠", "盯盤俠"),
    # 台湾惯用直角引号
    ("“", "「"), ("”", "」"), ("‘", "『"), ("’", "』"),
)


def _setting_value(db: Session, key: str) -> str:
    row = db.query(AppSettings).filter(AppSettings.key == key).first()
    return str(row.value or "").strip() if row else ""


def resolve_report_language(db: Session) -> str:
    """Use the persisted interface locale for generated prose and background jobs."""
    interface_language = _setting_value(db, "ui_language")
    return interface_language if interface_language in SUPPORTED_LANGUAGES else DEFAULT_LANGUAGE


def localize_text(text: str | None, language: str | None) -> str | None:
    """Convert Simplified Chinese to Taiwan Traditional Chinese when requested."""
    global _opencc, _opencc_warned
    if language != "zh-TW" or not text:
        return text
    if _opencc is None:
        with _opencc_lock:
            if _opencc is None:
                try:
                    from opencc import OpenCC

                    _opencc = OpenCC("s2twp")
                except Exception:
                    if not _opencc_warned:
                        logger.warning("opencc unavailable; returning zh-TW text unchanged")
                        _opencc_warned = True
                    return text
    result = _opencc.convert(text)
    for old, new in POSTPROCESS:
        result = result.replace(old, new)
    return result
