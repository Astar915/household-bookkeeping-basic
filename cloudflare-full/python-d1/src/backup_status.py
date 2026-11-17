"""Safe, user-facing classification for background cloud backup failures."""
from __future__ import annotations


def classify_backup_failure(provider: str, error: Exception) -> tuple[str, str]:
    """Return a stable UI category and a message that never includes credentials."""
    name = "Gitee" if str(provider).lower() == "gitee" else "GitHub"
    from bookkeeping.github_sync import GitHubAuthError, GitHubSyncConflict, GitHubSyncError
    from bookkeeping.gitee_sync import GiteeAuthError, GiteeSyncConflict, GiteeSyncError
    from bookkeeping.storage import LedgerError

    if isinstance(error, (GitHubAuthError, GiteeAuthError)):
        return (
            "reauthorize",
            f"{name} 授权已失效，请到“更多 → 设置 → 备份”重新连接 / 授权。账目仍保存在网页版云端。",
        )
    if isinstance(error, (GitHubSyncConflict, GiteeSyncConflict)):
        return (
            "conflict",
            f"{name} 云端版本已被其他设备更新，本次上传没有覆盖云端。请刷新账本后重试。",
        )

    if isinstance(error, LedgerError):
        detail = str(error).strip()
        if any(marker in detail for marker in ("其他设备更新", "版本已更新", "云端版本")):
            return (
                "conflict",
                f"{name} 云端版本已被其他设备更新，本次上传没有覆盖云端。请刷新账本后重试。",
            )
        if any(marker in detail for marker in ("请先连接备份服务", "连接已改变", "重新连接", "重新授权")):
            return (
                "reauthorize",
                f"{name} 连接需要重新确认，请到“更多 → 设置 → 备份”重新连接 / 授权。账目仍保存在网页版云端。",
            )
        return (
            "provider_error",
            f"{name} 备份操作未完成：{detail or '云端未确认备份'} 账目仍保存在网页版云端；若问题持续，请联系管理员。",
        )

    sync_error_types = tuple(
        cls for cls in (GitHubSyncError, GiteeSyncError)
        if isinstance(cls, type)
    )
    if sync_error_types and isinstance(error, sync_error_types):
        detail = str(error).strip()
        lower_detail = detail.lower()
        if any(marker in lower_detail for marker in (
            "无法连接", "网络", "timeout", "timed out", "超时", "temporarily unavailable",
        )):
            return (
                "temporary",
                f"{name} 上传暂时失败：{detail or '云端连接超时'} 账目已保存，请稍后重试。",
            )
        if any(marker in detail for marker in ("重新连接", "重新授权", "授权已失效", "令牌无效")):
            return (
                "reauthorize",
                f"{name} 授权需要更新，请到“更多 → 设置 → 备份”重新连接 / 授权。账目仍保存在网页版云端。",
            )
        return (
            "provider_error",
            f"{name} 上传失败：{detail or '云端服务未确认备份'} 账目仍保存在网页版云端；若问题持续，请联系管理员。",
        )

    if isinstance(error, (TimeoutError, ConnectionError)):
        return (
            "temporary",
            f"{name} 上传暂时失败：网络连接中断或超时。账目已保存，请稍后重试。",
        )

    return (
        "internal_error",
        f"{name} 上传遇到内部错误（{type(error).__name__}），请联系管理员。账目仍保存在网页版云端。",
    )


def backup_warning_kind(kinds: list[str]) -> str:
    """Choose the most useful banner action when one or more providers failed."""
    if "reauthorize" in kinds:
        return "reauthorize"
    if "internal_error" in kinds:
        return "internal_error"
    if "conflict" in kinds:
        return "conflict"
    if "provider_error" in kinds:
        return "provider_error"
    if "temporary" in kinds:
        return "temporary"
    return "ok"
