from __future__ import annotations

import json
import os
import re
import uuid
from datetime import datetime
from io import BytesIO
from pathlib import Path

from .natural_language import ImageAttachment
from .user_data import app_data_directory


MAX_ARCHIVE_LONG_EDGE = 3200


class ReceiptImageError(ValueError):
    """Raised when a selected image cannot be added to the local archive."""


class ReceiptImageSettingsError(RuntimeError):
    """Raised when the local receipt-image preference cannot be read or saved."""


class ReceiptImageSettingsStore:
    """Persist the receipt-image toggle in the current Windows user profile."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or app_data_directory() / "receipt_image_settings.json"

    def load_enabled(self) -> bool:
        if not self.path.exists():
            return True
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict) or payload.get("version") != 1:
                raise ValueError("unrecognized settings format")
            enabled = payload.get("save_images_locally", True)
            if not isinstance(enabled, bool):
                raise ValueError("invalid save preference")
            return enabled
        except (OSError, UnicodeDecodeError, ValueError, TypeError, json.JSONDecodeError) as exc:
            raise ReceiptImageSettingsError("本机图片保存设置无法读取。") from exc

    def save_enabled(self, enabled: bool) -> None:
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary.write_text(
                json.dumps(
                    {"version": 1, "save_images_locally": bool(enabled)},
                    ensure_ascii=True,
                    indent=2,
                ),
                encoding="utf-8",
            )
            temporary.replace(self.path)
        except OSError as exc:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
            raise ReceiptImageSettingsError("无法保存本机图片保存设置。") from exc


def archive_receipt_image(
    attachment: ImageAttachment,
    directory: str | Path,
) -> Path:
    """Write a compressed, metadata-stripped copy of a GUI image selection."""
    source_path = Path(attachment.source_path) if attachment.source_path else None
    original_name = source_path.name if source_path is not None else Path(attachment.name).name
    try:
        original_data = source_path.read_bytes() if source_path is not None else attachment.data
    except OSError:
        # The already-loaded attachment still represents the bytes sent to the
        # model if its original file was moved after it was selected.
        original_data = attachment.data
    if not original_data:
        raise ReceiptImageError(f"图片文件为空：{attachment.name}")

    stored_data: bytes
    stored_suffix: str
    try:
        from PIL import Image, ImageOps

        with Image.open(BytesIO(original_data)) as source:
            image = ImageOps.exif_transpose(source)
            if max(image.size) > MAX_ARCHIVE_LONG_EDGE:
                image.thumbnail(
                    (MAX_ARCHIVE_LONG_EDGE, MAX_ARCHIVE_LONG_EDGE),
                    Image.Resampling.LANCZOS,
                )

            has_alpha = "A" in image.getbands() or "transparency" in image.info
            if Path(original_name).suffix.casefold() == ".png":
                if has_alpha:
                    rgba = image.convert("RGBA")
                    background = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
                    background.alpha_composite(rgba)
                    image = background.convert("RGB")
                output = BytesIO()
                image.save(output, format="PNG", optimize=True, compress_level=9)
                stored_data = output.getvalue()
                stored_suffix = ".png"
            else:
                if has_alpha:
                    rgba = image.convert("RGBA")
                    background = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
                    background.alpha_composite(rgba)
                    image = background.convert("RGB")
                else:
                    image = image.convert("RGB")
                output = BytesIO()
                image.save(
                    output,
                    format="JPEG",
                    quality=91,
                    optimize=True,
                    progressive=True,
                )
                stored_data = output.getvalue()
                stored_suffix = ".jpg"
    except ImportError:
        # Preserve attachment support on installations where Pillow is absent.
        # Pillow is listed in requirements.txt and enables archive compression.
        stored_data = original_data
        stored_suffix = Path(original_name).suffix.casefold()
    except (OSError, ValueError, SyntaxError, EOFError) as exc:
        raise ReceiptImageError(
            f"图片无法压缩：{attachment.name}（{exc.__class__.__name__}）"
        ) from None

    if not stored_data:
        raise ReceiptImageError(f"图片压缩结果为空：{attachment.name}")
    target_directory = Path(directory)
    readable_stem = re.sub(r"[^\w\-\u3400-\u9fff]+", "_", Path(original_name).stem).strip("_")
    readable_stem = readable_stem[:48] or "receipt"
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    stored_name = f"{timestamp}_{uuid.uuid4().hex[:8]}_{readable_stem}{stored_suffix}"
    target_path = target_directory / stored_name
    temporary_path = target_directory / f".{stored_name}.tmp"
    try:
        target_directory.mkdir(parents=True, exist_ok=True)
        temporary_path.write_bytes(stored_data)
        temporary_path.replace(target_path)
    except OSError as exc:
        try:
            temporary_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise ReceiptImageError(
            f"无法保存小票图片：{attachment.name}（{exc.__class__.__name__}）"
        ) from None

    return target_path
