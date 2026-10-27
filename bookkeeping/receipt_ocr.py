"""Optional Windows OCR. Image bytes and recognized text remain in memory."""
from __future__ import annotations

import base64
import json
import os
import re
import subprocess
import unicodedata
from datetime import date
from difflib import SequenceMatcher
from io import BytesIO
from decimal import Decimal
from typing import Any


_WINDOWS_OCR_SCRIPT = r"""
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
Add-Type -AssemblyName System.Runtime.WindowsRuntime
[Windows.Media.Ocr.OcrEngine,Windows.Foundation,ContentType=WindowsRuntime] > $null
[Windows.Globalization.Language,Windows.Globalization,ContentType=WindowsRuntime] > $null
[Windows.Storage.Streams.InMemoryRandomAccessStream,Windows.Storage.Streams,ContentType=WindowsRuntime] > $null
[Windows.Storage.Streams.DataWriter,Windows.Storage.Streams,ContentType=WindowsRuntime] > $null
[Windows.Graphics.Imaging.BitmapDecoder,Windows.Graphics.Imaging,ContentType=WindowsRuntime] > $null
[Windows.Graphics.Imaging.SoftwareBitmap,Windows.Graphics.Imaging,ContentType=WindowsRuntime] > $null
$asTask = [System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
    $_.Name -eq 'AsTask' -and $_.IsGenericMethod -and $_.GetParameters().Count -eq 1
} | Select-Object -First 1
function Await($operation, $resultType) {
    $task = $asTask.MakeGenericMethod($resultType).Invoke($null, @($operation))
    $task.GetAwaiter().GetResult()
}
$stream = New-Object Windows.Storage.Streams.InMemoryRandomAccessStream
$writer = New-Object Windows.Storage.Streams.DataWriter($stream)
$writer.WriteBytes([Convert]::FromBase64String([Console]::In.ReadToEnd()))
$stored = Await ($writer.StoreAsync()) ([uint32])
$null = $writer.DetachStream()
$stream.Seek(0)
$decoder = Await ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)) ([Windows.Graphics.Imaging.BitmapDecoder])
$bitmap = Await ($decoder.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])
$engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromUserProfileLanguages()
if ($null -eq $engine) { throw 'No installed OCR language' }
$result = Await ($engine.RecognizeAsync($bitmap)) ([Windows.Media.Ocr.OcrResult])
$lines = @($result.Lines | ForEach-Object {
    $words = @($_.Words)
    $left = ($words | ForEach-Object { $_.BoundingRect.X } | Measure-Object -Minimum).Minimum
    $top = ($words | ForEach-Object { $_.BoundingRect.Y } | Measure-Object -Minimum).Minimum
    $right = ($words | ForEach-Object { $_.BoundingRect.X + $_.BoundingRect.Width } | Measure-Object -Maximum).Maximum
    $bottom = ($words | ForEach-Object { $_.BoundingRect.Y + $_.BoundingRect.Height } | Measure-Object -Maximum).Maximum
    [ordered]@{text=$_.Text; x=$left; y=$top; width=($right-$left); height=($bottom-$top)}
})
[ordered]@{language=$engine.RecognizerLanguage.LanguageTag; lines=$lines} | ConvertTo-Json -Depth 5 -Compress
$bitmap.Dispose()
$writer.Dispose()
$stream.Dispose()
"""


def read_printed_text(image_bytes: bytes) -> dict[str, Any] | None:
    """Use installed OS OCR without writing images or spawning visible windows."""
    if os.name != "nt" or not image_bytes.startswith((b"\xff\xd8\xff", b"\x89PNG")):
        return None
    try:
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-EncodedCommand",
             base64.b64encode(_WINDOWS_OCR_SCRIPT.encode("utf-16-le")).decode("ascii")],
            input=base64.b64encode(image_bytes).decode("ascii"),
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=20,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if result.returncode:
            return None
        data = json.loads(result.stdout.lstrip("\ufeff").strip())
        if not isinstance(data, dict) or not isinstance(data.get("lines"), list):
            return None
        lines = [line for line in data["lines"] if isinstance(line, dict) and isinstance(line.get("text"), str)]
        if not lines:
            return None
        return {"language": str(data.get("language", "")), "lines": lines[:250]}
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


def normalized_print(value: str) -> str:
    return re.sub(r"[\s・･*＊:：,，]", "", unicodedata.normalize("NFKC", value)).casefold()


def joined_lines(document: dict[str, Any]) -> list[str]:
    """Join separated description/price columns using their printed baselines."""
    groups: list[list[dict[str, Any]]] = []
    for line in sorted(document.get("lines", []), key=lambda line: line.get("y", 0) + line.get("height", 0) / 2):
        center = line.get("y", 0) + line.get("height", 0) / 2
        if groups:
            previous = groups[-1][0]
            previous_center = previous.get("y", 0) + previous.get("height", 0) / 2
            tolerance = max(8, max(line.get("height", 0), previous.get("height", 0)) * 0.7)
            if abs(center - previous_center) <= tolerance:
                groups[-1].append(line)
                continue
        groups.append([line])
    return [" ".join(str(line["text"]) for line in sorted(group, key=lambda line: line.get("x", 0))) for group in groups]


def printed_total(document: dict[str, Any]) -> str | None:
    """Accept a unique amount on an explicit final-total line, never a tax subtotal."""
    candidates: set[Decimal] = set()
    paid_amounts: set[Decimal] = set()
    for line in joined_lines(document):
        text = unicodedata.normalize("NFKC", line).replace("\\", "¥")
        compact = re.sub(r"\s", "", text)
        if re.search(r"小計|小计|税額|税额|対象|税率|subtotal|taxtotal", compact, re.IGNORECASE):
            continue
        label = re.search(r"合[計计]|総[計计]|お会計|お支払[い]?|領収金額|(?<![a-z])(?:grand\s*)?total(?=[^a-z]|$)", compact, re.IGNORECASE)
        payment_label = re.search(r"^(?:クレジット|現金|カード|credit|cash|card)", compact, re.IGNORECASE)
        if not label and not payment_label:
            continue
        suffix = compact[(label or payment_label).end():]
        amounts = re.findall(r"[¥￥]?\s*(\d{1,3}(?:,\d{3})+|\d+)(?:\.(\d{1,2}))?\s*(?:円|元)?", suffix)
        if len(amounts) != 1:
            continue
        whole, fraction = amounts[0]
        amount = Decimal(whole.replace(",", "") + ("." + fraction if fraction else ""))
        if amount > 0:
            (candidates if label else paid_amounts).add(amount)
    if not candidates:
        candidates = paid_amounts
    if len(candidates) != 1:
        return None
    return format(next(iter(candidates)), "f")


def printed_date(document: dict[str, Any]) -> str | None:
    dates: set[str] = set()
    for line in joined_lines(document):
        text = re.sub(r"\s", "", unicodedata.normalize("NFKC", line))
        for year, month, day in re.findall(r"(20\d{2})[年/.-](\d{1,2})[月/.-](\d{1,2})(?:日|\b)", text):
            try:
                dates.add(date(int(year), int(month), int(day)).isoformat())
            except ValueError:
                pass
    return next(iter(dates)) if len(dates) == 1 else None


def completed_receipt(document: dict[str, Any]) -> bool | None:
    text = normalized_print("\n".join(joined_lines(document)))
    if re.search(r"未払|未決済|見積|unpaid|pendingpayment|quotation|待付款|未付款", text):
        return False
    if re.search(r"領収書|領収証|売上票|お買上点数|receipt|paymentcompleted|已付款|收据", text):
        return True
    return None


def crop_printed_document(image_bytes: bytes, document: dict[str, Any]) -> bytes:
    """Use OCR geometry instead of guessing where a receipt lies in a photo."""
    from PIL import Image
    lines = document.get("lines", [])
    if not lines or any(not all(k in line for k in ("x", "y", "width", "height")) for line in lines):
        return image_bytes
    # Keep the retail receipt; a separate cardholder slip below it contains
    # repeated totals and sensitive account fragments that are unnecessary.
    footer_starts = [line["y"] for line in lines if re.search(
        r"売上票|お客様控え|cardholdercopy|customercopy", normalized_print(line["text"])
    )]
    if footer_starts:
        body = [line for line in lines if line["y"] < min(footer_starts)]
        if len(body) >= 5:
            lines = body
    with Image.open(BytesIO(image_bytes)) as image:
        left = min(line["x"] for line in lines)
        top = min(line["y"] for line in lines)
        right = max(line["x"] + line["width"] for line in lines)
        bottom = max(line["y"] + line["height"] for line in lines)
        pad_x, pad_y = (right - left) * 0.08, (bottom - top) * 0.10
        box = (max(0, int(left - pad_x)), max(0, int(top - pad_y)),
               min(image.width, int(right + pad_x)), min(image.height, int(bottom + pad_y)))
        cropped = image.crop(box).convert("RGB")
        output = BytesIO()
        cropped.save(output, format="JPEG", quality=95)
        return output.getvalue()


def grounded_fields(fields: dict[str, Any], document: dict[str, Any]) -> dict[str, Any] | None:
    """Constrain model guesses to OS-recognized characters and labeled money."""
    total = printed_total(document)
    if total is None:
        return None
    text = "\n".join(joined_lines(document))
    normalized = normalized_print(text)
    result = dict(fields)
    result["amount"] = total
    result["date"] = printed_date(document)
    if completed_receipt(document) is not None:
        result["completed"] = completed_receipt(document)
    # A partial, actually printed store name is preferable to an invented brand.
    merchant = fields.get("merchant")
    if not isinstance(merchant, str) or normalized_print(merchant) not in normalized:
        result["merchant"] = None
    def supported(item: str) -> bool:
        candidate = normalized_print(item)
        if candidate and candidate in normalized:
            return True
        # OCR may substitute a few characters in a clearly matching product
        # line. Full-string similarity is too strict for Japanese OCR: one
        # receipt line can contain several substitutions while preserving
        # distinctive product fragments (for example カロリーメイト and
        # ブロックチー). Accept a long candidate only when enough of its
        # characters match the same printed line and one matching run is long;
        # this keeps unrelated model-invented products out.
        for line in joined_lines(document):
            printed_line = normalized_print(line)
            matcher = SequenceMatcher(None, candidate, printed_line)
            if matcher.ratio() >= 0.65:
                return True
            blocks = matcher.get_matching_blocks()
            matched = sum(block.size for block in blocks)
            longest = max((block.size for block in blocks), default=0)
            if len(candidate) >= 10 and matched / len(candidate) >= 0.65 and longest >= 4:
                return True
        return False
    result["items"] = [item for item in fields.get("items", []) if isinstance(item, str) and supported(item)]
    result["ocr_source"] = "windows"
    return result
