from __future__ import annotations

import json
import os
from pathlib import Path, PureWindowsPath
from collections.abc import Sequence
from typing import Any

from .user_data import app_data_directory


class BookkeepingSkillError(RuntimeError):
    """A loaded bookkeeping skill could not be read or saved."""


def _settings_path(filename: str = "loaded_skill.json") -> Path:
    return app_data_directory() / filename


DEFAULT_SKILL_PATH = Path(__file__).resolve().parents[1] / ".agents" / "skills" / "household-bookkeeping-software-v0-2" / "SKILL.md"
DEFAULT_FOOD_HEALTH_SKILL_PATH = Path(__file__).resolve().parents[1] / ".agents" / "skills" / "household-food-health" / "SKILL.md"
MAX_SKILL_BYTES = 256 * 1024


class BookkeepingSkillStore:
    """Persist a selected Markdown skill and read its latest contents on demand."""

    def __init__(
        self,
        path: Path | None = None,
        *,
        default_path: Path = DEFAULT_SKILL_PATH,
        managed_paths: Sequence[Path] = (),
    ) -> None:
        self.path = path or _settings_path()
        self._default_path = default_path
        self._managed_paths = tuple(managed_paths)

    @property
    def default_path(self) -> Path:
        return self._default_path

    def current_path(self) -> Path | None:
        if not self.path.exists():
            return self._default_path if self._default_path.is_file() else None
        try:
            saved: Any = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(saved, dict) or saved.get("version") != 1:
                raise ValueError("unsupported settings version")
            value = saved.get("path")
            if value is None or value == "":
                return None
            if not isinstance(value, str):
                raise ValueError("path must be text")
            relative = saved.get("relative_path")
            if relative is not None:
                if not isinstance(relative, str) or not relative:
                    raise ValueError("relative path must be text")
                root = self.path.parent.resolve()
                candidate = (root / relative).resolve()
                if not candidate.is_relative_to(root):
                    raise ValueError("relative skill path escapes settings directory")
                return candidate
            # Legacy mobile backups stored another computer's absolute path.
            # Rebase only an explicitly managed suffix in this account's own
            # folder; never search other accounts or match a basename alone.
            old_parts = PureWindowsPath(value).parts
            root = self.path.parent.resolve()
            for managed in self._managed_paths:
                candidate = managed.resolve()
                if not candidate.is_relative_to(root):
                    continue
                suffix = candidate.relative_to(root).parts
                if len(suffix) == 1:
                    suffix = (root.name, *suffix)
                if tuple(p.casefold() for p in old_parts[-len(suffix):]) == tuple(p.casefold() for p in suffix) and candidate.is_file():
                    return candidate
            if self._managed_paths and not Path(value).resolve().is_relative_to(root):
                raise ValueError("managed skill path escapes account directory")
            return Path(value)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
            raise BookkeepingSkillError("记账 Skill 设置无法读取；请在软件中重新加载或卸载 Skill。") from exc

    def load(self) -> dict[str, str] | None:
        path = self.current_path()
        if path is None:
            return None
        try:
            if not path.is_file():
                raise BookkeepingSkillError(f"找不到已加载的 Skill 文件：{path}。请重新选择文件或卸载 Skill。")
            if path.stat().st_size > MAX_SKILL_BYTES:
                raise BookkeepingSkillError("Skill 文件超过256KB，无法加载。")
            content = path.read_text(encoding="utf-8-sig").strip()
        except BookkeepingSkillError:
            raise
        except (OSError, UnicodeDecodeError) as exc:
            raise BookkeepingSkillError("无法读取 Skill 文件；请确认文件可访问且使用 UTF-8 编码。") from exc
        if not content:
            raise BookkeepingSkillError("Skill 文件是空的，无法加载。")
        return {"path": str(path), "name": path.name, "content": content}

    def save_path(self, selected_path: str | Path) -> dict[str, str]:
        skill = self.read_path(selected_path)
        self._save_path(skill["path"])
        return skill

    def read_path(self, selected_path: str | Path) -> dict[str, str]:
        """Read and validate a selected skill without changing saved settings."""
        candidate = Path(selected_path).expanduser()
        if candidate.suffix.casefold() != ".md":
            raise BookkeepingSkillError("请选择 Markdown 格式的 Skill 文件（.md）。")
        try:
            resolved = candidate.resolve(strict=True)
        except OSError as exc:
            raise BookkeepingSkillError("所选 Skill 文件无法访问。") from exc
        if not resolved.is_file():
            raise BookkeepingSkillError("所选路径不是文件。")
        # Validate the selected file before persisting its path.
        try:
            content_size = resolved.stat().st_size
            if content_size > MAX_SKILL_BYTES:
                raise BookkeepingSkillError("Skill 文件超过256KB，无法加载。")
            content = resolved.read_text(encoding="utf-8-sig").strip()
        except BookkeepingSkillError:
            raise
        except (OSError, UnicodeDecodeError) as exc:
            raise BookkeepingSkillError("无法读取 Skill 文件；请确认文件可访问且使用 UTF-8 编码。") from exc
        if not content:
            raise BookkeepingSkillError("Skill 文件是空的，无法加载。")
        return {"path": str(resolved), "name": resolved.name, "content": content}

    def clear(self) -> None:
        self._save_path(None)

    def _save_path(self, value: str | None) -> None:
        saved: dict[str, Any] = {"version": 1, "path": value}
        if value:
            target = Path(value).resolve()
            root = self.path.parent.resolve()
            if target.is_relative_to(root):
                saved["relative_path"] = target.relative_to(root).as_posix()
        payload = json.dumps(saved, ensure_ascii=False, indent=2)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary.write_text(payload, encoding="utf-8")
            os.replace(temporary, self.path)
        except OSError as exc:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
            raise BookkeepingSkillError("无法保存 Skill 设置，请检查当前用户配置目录权限。") from exc


class FoodHealthSkillStore(BookkeepingSkillStore):
    """Manage the food-health Agent's Skill independently from bookkeeping."""

    def __init__(self, path: Path | None = None) -> None:
        super().__init__(
            path or _settings_path("loaded_food_health_skill.json"),
            default_path=DEFAULT_FOOD_HEALTH_SKILL_PATH,
        )
