from __future__ import annotations

from copy import deepcopy
import calendar as calendar_module
import os
import multiprocessing
import queue
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import traceback
import tkinter as tk
import webbrowser
import uuid
import weakref
from datetime import date, datetime, timedelta
from io import BytesIO
from decimal import Decimal
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Any

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
except ImportError:
    DND_FILES = None
    TkinterDnD = None

try:
    from PIL import Image, ImageTk
except ImportError:
    Image = None
    ImageTk = None

from .natural_language import (
    API_KEY_ENV,
    API_URL_ENV,
    DEFAULT_API_URL,
    DEFAULT_MODEL,
    ImageAttachment,
    MAX_IMAGE_ATTACHMENTS,
    MAX_TOTAL_IMAGE_BYTES,
    MODEL_ENV,
    NaturalLanguageError,
    OpenAICompatibleClient,
    _account_mention_aliases,
    _normalize_account_label,
    _payment_priority_terms,
    _today_japan,
    is_local_http_api,
    is_deepseek_api,
    load_image_attachment,
)
from .request_worker import (RequestMergeError, merge_isolated_database, run_isolated_request,
                             receive_request_result, commit_request_result)
from .cloud_pull import PullState, automatic_pull, local_revision
from .receipt_images import (
    ReceiptImageError,
    ReceiptImageSettingsError,
    ReceiptImageSettingsStore,
    archive_receipt_image,
)
from .backup_scope import (
    BACKUP_SCOPE_KEYS,
    DEFAULT_BACKUP_SCOPE,
    BackupScopeError,
    BackupScopeStore,
)
from .cash_management import managed_balances, reconcile_account_balances, sort_managed_balances
from .credit_management import (
    credit_card_overview,
    next_month_due_date,
    recent_credit_repayments,
    process_due_credit_repayments,
    record_credit_card_repayment,
    save_credit_repayment_schedule,
    set_credit_repayment_schedule_enabled,
)
from .financial_statements import build_balance_sheet, build_profit_statement
from .github_sync import (
    DEVICE_VERIFY_URL,
    DEFAULT_BACKUP_REPOSITORY_NAME,
    GITHUB_APP_CLIENT_ID,
    GitHubAutoSyncSettingsError,
    GitHubAutoSyncSettingsStore,
    GitHubClient,
    GitHubSyncError,
    GitHubSyncSettingsStore,
    GitHubTokenStore,
    create_sync_bundle,
    github_sync_process_lock,
    is_github_app_user_token,
    poll_device_token,
    request_device_code,
    restore_sync_bundle,
)
from .github_app_config import GITHUB_APP_INSTALL_URL
from .gitee_sync import (
    DEFAULT_GITEE_BACKUP_REPOSITORY_NAME,
    GITEE_TOKEN_SETTINGS_URL,
    GiteeAutoSyncSettingsError,
    GiteeAutoSyncSettingsStore,
    GiteeClient,
    GiteeSyncError,
    GiteeSyncSettingsStore,
    GiteeTokenStore,
    MAX_GITEE_SYNC_BUNDLE_BYTES,
)
from .fixed_assets import open_fixed_asset_management
from .food_tracking import open_food_tracking as show_food_tracking
from .savings_planner import open_savings_plan as show_savings_plan
from .payment_preferences import (
    PaymentPromptSettingsConflict,
    PaymentPromptSettingsError,
    PaymentPromptStore,
)
from .recurring_transactions import (
    FREQUENCY_LABELS,
    FREQUENCY_UNITS,
    delete_recurring_schedule,
    list_recurring_schedules,
    process_due_recurring_transactions,
    save_recurring_schedule,
    set_recurring_schedule_enabled,
)
from .secure_settings import ApiKeyStore, ApiProfileStore, SecureSettingsError
from .skill_settings import (
    BookkeepingSkillError,
    BookkeepingSkillStore,
    FoodHealthSkillStore,
)
from .ui_fonts import configure_global_fonts, enable_windows_gdi_text_scaling
from .desktop_theme import PALETTE, RoundedPanel, color, configure_styles, apply_appearance, apply_titlebar
from .appearance import APPEARANCE_CHOICES, load_appearance, save_appearance
from .desktop_theme import fit_management_text, wrap_management_toolbar
from .desktop_shell import DesktopShell
from .desktop_frame import center_window, defer_during_interactive_resize
from .user_data import app_data_directory
from .ui_confirm import confirm_delete_once
from .single_instance import SingleInstance, repair_window_position
from .localization import (
    LANGUAGE_CHOICES,
    apply_language,
    current_language,
    install_tk_localization,
    load_language,
    save_language,
    set_language,
    translate,
    translate_tree_item,
)
from .storage import (
    Database,
    LedgerError,
    format_account_amount,
    minor_to_text,
    parse_date,
    to_minor_allow_zero,
)


def _default_database_path() -> Path:
    if getattr(sys, "frozen", False):
        return app_data_directory() / "data" / "household_bookkeeping.sqlite3"
    return Path(__file__).resolve().parents[1] / "data" / "household_bookkeeping.sqlite3"


DEFAULT_DB = _default_database_path()
REQUEST_TIMEOUT_SECONDS = 300
LOCAL_OLLAMA_REQUEST_TIMEOUT_SECONDS = 600
LEGACY_NVIDIA_API_URL = "https://integrate.api.nvidia.com/v1/chat/completions"
LEGACY_NVIDIA_MODEL = "moonshotai/kimi-k3"
AGENT_SELECTED_BACKGROUND = color("#1664df")
AGENT_SELECTED_ACTIVE_BACKGROUND = color("#124eae")
_DISPLAY_DIGIT_PATTERN = re.compile(r"\d")


def _mask_display_numbers(value: object) -> str:
    """Replace digits in account-page values while keeping the original text shape."""
    return _DISPLAY_DIGIT_PATTERN.sub("*", str(value))


class BookkeepingWindow:
    def __init__(self, root: tk.Tk, database_path: Path = DEFAULT_DB) -> None:
        self.root = root
        self.appearance_mode = load_appearance()
        self.language = load_language()
        install_tk_localization(root, self.language)
        self.ui_font_family = configure_global_fonts(root)
        self.database_path = database_path
        self.root.report_callback_exception = self._report_ui_exception
        self.github_auto_sync_settings_store = GitHubAutoSyncSettingsStore()
        self.github_auto_sync_enabled = True
        self.github_auto_sync_settings_error = ""
        try:
            self.github_auto_sync_enabled = self.github_auto_sync_settings_store.load_enabled()
        except GitHubAutoSyncSettingsError as exc:
            self.github_auto_sync_enabled = False
            self.github_auto_sync_settings_error = str(exc)
        self.gitee_auto_sync_settings_store = GiteeAutoSyncSettingsStore()
        self.gitee_auto_sync_enabled = True
        self.gitee_auto_sync_settings_error = ""
        try:
            self.gitee_auto_sync_enabled = self.gitee_auto_sync_settings_store.load_enabled()
        except GiteeAutoSyncSettingsError as exc:
            self.gitee_auto_sync_enabled = False
            self.gitee_auto_sync_settings_error = str(exc)
        self._github_auto_sync_state_lock = threading.Lock()
        self._github_auto_sync_running = False
        self._github_auto_sync_pending = False
        self._gitee_auto_sync_state_lock = threading.Lock()
        self._gitee_auto_sync_running = False
        self._gitee_auto_sync_pending = False
        self._github_upload_lock = threading.Lock()
        self.receipt_image_settings_store = ReceiptImageSettingsStore()
        self.receipt_image_settings_error = ""
        try:
            self.save_receipt_images_locally = self.receipt_image_settings_store.load_enabled()
        except ReceiptImageSettingsError as exc:
            self.save_receipt_images_locally = False
            self.receipt_image_settings_error = str(exc)
        self.clients: dict[tuple[str, bool, str], OpenAICompatibleClient] = {}
        self.history: list[dict[str, Any]] = []
        self.pending_state: dict[str, Any] | None = None
        self.agent_mode = "bookkeeping"
        self.agent_states: dict[str, dict[str, Any]] = {
            "bookkeeping": {"history": self.history, "pending_state": None, "messages": [], "workflow_profile_id": None},
            "food_health": {"history": [], "pending_state": None, "messages": [], "workflow_profile_id": None},
        }
        self.recurring_results: queue.Queue[tuple[list[dict[str, Any]], str | None]] = queue.Queue()
        self._recurring_processing = False
        self._request_process: multiprocessing.Process | None = None
        self._request_results = queue.Queue()
        self._request_started = 0.0
        self._request_deadline = 0.0
        self._request_inserted_ids = []
        self._startup_results = queue.Queue()
        self._startup_cancelled = threading.Event()
        self._startup_applying = False
        self._request_committing = False
        self._request_pipe: Any = None
        self._request_workspace: Path | None = None
        self._request_baseline_path: Path | None = None
        self._request_candidate_path: Path | None = None
        self._request_cancelled = False
        self._request_worker_message: tuple[Any, ...] | None = None
        self._request_history_snapshot: list[dict[str, Any]] = []
        self._request_pending_snapshot: dict[str, Any] | None = None
        self._request_profile_id: str | None = None
        self._pending_image_attachments: list[ImageAttachment] = []
        self._request_agent_mode = "bookkeeping"
        self.image_attachments: list[ImageAttachment] = []
        self._image_preview_refs: list[Any] = []
        self._pending_draft_text = ""
        self._pending_had_images = False
        self.busy = False
        self._restart_pending = False
        self._github_restore_in_progress = False
        self._finance_dropdown: tk.Frame | None = None
        self._finance_dropdown_canvas: tk.Canvas | None = None
        self._scroll_bindtag = f"HouseholdBookkeepingScroll-{id(self)}"
        self._scroll_remainders: weakref.WeakKeyDictionary[Any, float] = weakref.WeakKeyDictionary()
        self._touchpad_scroll_remainders: weakref.WeakKeyDictionary[Any, float] = weakref.WeakKeyDictionary()
        self.api_profile_store = ApiProfileStore()
        self.api_profiles = [self._default_api_profile()]
        self.active_api_profile_id = self.api_profiles[0]["id"]
        self.agent_profile_ids = {
            "bookkeeping": self.active_api_profile_id,
            "food_health": self.active_api_profile_id,
        }
        self.agent_vision_profile_ids = dict(self.agent_profile_ids)
        self.api_profile_settings_error = ""
        try:
            saved_api_settings = self.api_profile_store.load()
            saved_profiles = saved_api_settings["profiles"]
            if isinstance(saved_profiles, list) and saved_profiles:
                self.api_profiles = [dict(profile) for profile in saved_profiles if isinstance(profile, dict)]
                if not self.api_profiles:
                    raise SecureSettingsError("API服务配置中没有有效的服务项。")
                saved_active_id = saved_api_settings["active_profile_id"]
                known_ids = {profile["id"] for profile in self.api_profiles}
                self.active_api_profile_id = (
                    saved_active_id if isinstance(saved_active_id, str) and saved_active_id in known_ids
                    else self.api_profiles[0]["id"]
                )
                saved_agent_ids = saved_api_settings.get("agent_profile_ids", {})
                if isinstance(saved_agent_ids, dict):
                    self.agent_profile_ids = {
                        mode: (
                            saved_agent_ids.get(mode)
                            if isinstance(saved_agent_ids.get(mode), str)
                            and saved_agent_ids.get(mode) in known_ids
                            else self.active_api_profile_id
                        )
                        for mode in ("bookkeeping", "food_health")
                    }
                saved_vision_ids = saved_api_settings.get("agent_vision_profile_ids", {})
                if isinstance(saved_vision_ids, dict):
                    self.agent_vision_profile_ids = {
                        mode: (
                            saved_vision_ids.get(mode)
                            if isinstance(saved_vision_ids.get(mode), str)
                            and saved_vision_ids.get(mode) in known_ids
                            else self.agent_profile_ids[mode]
                        )
                        for mode in ("bookkeeping", "food_health")
                    }
            elif not self.api_profile_settings_error:
                legacy_key = ApiKeyStore().load()
                if legacy_key:
                    self.api_profiles.append(
                        {
                            "id": "legacy-nvidia-" + uuid.uuid4().hex,
                            "name": "旧 NVIDIA 配置（请更新密钥）",
                            "api_url": os.environ.get(API_URL_ENV, "").strip() or LEGACY_NVIDIA_API_URL,
                            "model": os.environ.get(MODEL_ENV, "").strip() or LEGACY_NVIDIA_MODEL,
                            "api_key": legacy_key,
                            "thinking_enabled": False,
                            "reasoning_effort": "low",
                        }
                    )
                    self.api_profile_store.save(
                        self.api_profiles,
                        self.active_api_profile_id,
                        self.agent_profile_ids,
                        self.agent_vision_profile_ids,
                    )
                    self.api_profile_settings_error = "旧版API Key已保留到独立服务项；该密钥曾贴入聊天，请轮换后再使用。"
        except SecureSettingsError as exc:
            self.api_profile_settings_error = str(exc)
        self.payment_prompt_store = PaymentPromptStore()
        self.payment_profiles: list[dict[str, Any]] = []
        self.payment_settings_load_error = ""
        self.payment_settings_revision = ""
        try:
            payment_settings, self.payment_settings_revision = self.payment_prompt_store.load_snapshot()
            self.payment_profiles = payment_settings["profiles"]
        except PaymentPromptSettingsError as exc:
            self.payment_settings_load_error = str(exc)
        self.skill_store = BookkeepingSkillStore()
        self.food_health_skill_store = FoodHealthSkillStore()
        self.loaded_skill: dict[str, str] | None = None
        self.loaded_food_health_skill: dict[str, str] | None = None
        self.skill_settings_error = ""
        self.food_health_skill_settings_error = ""
        try:
            self.loaded_skill = self.skill_store.load()
        except BookkeepingSkillError as exc:
            self.skill_settings_error = str(exc)
        try:
            self.loaded_food_health_skill = self.food_health_skill_store.load()
        except BookkeepingSkillError as exc:
            self.food_health_skill_settings_error = str(exc)
        self.root.title("家庭记账")
        initial_width = min(1120, self.root.winfo_screenwidth()-64)
        initial_height = min(720, self.root.winfo_screenheight()-64)
        initial_x = max(0, (self.root.winfo_screenwidth()-initial_width)//2)
        initial_y = max(0, (self.root.winfo_screenheight()-initial_height)//2)
        self.root.geometry(f"{initial_width}x{initial_height}+{initial_x}+{initial_y}")
        self.root.minsize(820, 560)
        self.root.resizable(True, True)
        self.root.configure(bg=color("#f3f5f8"))
        self.root.bind("<Map>", self._repair_main_window_position, add="+")
        self.root.bind_all("<Map>", self._theme_new_window, add="+")
        icon_path = Path(__file__).resolve().parents[1] / "assets" / "desktop-mark.ico"
        if icon_path.exists():
            try:
                self.root.iconbitmap(default=str(icon_path))
            except tk.TclError:
                pass
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self._build_widgets()
        self._install_copy_support()
        self.root.bind("<Configure>", self._position_finance_dropdown, add="+")
        self.root.bind_all("<Button-1>", self._dismiss_finance_dropdown_on_click, add="+")
        self.root.bind_all("<Button-1>", self._clear_selection_on_noninteractive_click, add="+")
        self.root.bind_all("<Escape>", self._dismiss_finance_dropdown_on_escape, add="+")
        self._install_mousewheel_support()
        self._append_message(
            "助手",
            "你好，直接告诉我一笔收入、消费、转账或还款。信息不够时我会先追问，确认后才写入本地账本。",
        )
        self.root.after(200, lambda: self.transcript.yview_moveto(0))
        self.input_box.focus_set()
        self.root.after(100, self._poll_results)
        self.root.after(0, self._start_startup_cloud_pull)
        self.root.after(150, self._poll_recurring_transaction_results)
        self.root.after(1000, self._check_due_credit_repayments)
        self.root.after(1200, self._check_due_recurring_transactions)
        self.root.after(2000, self._poll_appearance)

    def _report_ui_exception(self, kind, value, trace):
        # Store stack locations only: no model payloads, financial input or keys.
        try:
            folder = app_data_directory()
            folder.mkdir(parents=True, exist_ok=True)
            with (folder / 'desktop-errors.log').open('a', encoding='utf-8') as stream:
                stream.write(f'{datetime.now().isoformat()} {kind.__name__}\n')
                stream.writelines(traceback.format_tb(trace))
            self.status.configure(text=translate('界面发生错误，详细位置已保存至本机诊断日志。', self.language))
        except (OSError, tk.TclError, AttributeError):
            pass

    def _theme_new_window(self, event: Any) -> None:
        if isinstance(getattr(event, "widget", None), (tk.Tk, tk.Toplevel)):
            self.root.after_idle(lambda: apply_titlebar(event.widget) if event.widget.winfo_exists() else None)

    def _poll_appearance(self) -> None:
        try:
            apply_appearance(self.root, self.ui_font_family, self.appearance_mode)
            self.root.after(2000, self._poll_appearance)
        except tk.TclError:
            pass

    def _repair_main_window_position(self, event: Any) -> None:
        if getattr(event, "widget", None) is not self.root:
            return
        try:
            self.root.after_idle(
                lambda: repair_window_position(self.root.winfo_id())
                if self.root.winfo_exists()
                else None
            )
        except tk.TclError:
            pass

    @staticmethod
    def _default_api_profile() -> dict[str, Any]:
        api_url = os.environ.get(API_URL_ENV, DEFAULT_API_URL).strip() or DEFAULT_API_URL
        model = os.environ.get(MODEL_ENV, DEFAULT_MODEL).strip() or DEFAULT_MODEL
        api_key = os.environ.get(API_KEY_ENV, "").strip()
        return {
            "id": "default-" + uuid.uuid4().hex,
            "name": "Ollama 本机" if is_local_http_api(api_url) else "环境变量 API",
            "api_url": api_url,
            "model": model,
            "api_key": api_key,
            "thinking_enabled": False,
            "reasoning_effort": "low",
        }

    def _install_mousewheel_support(self) -> None:
        """Handle wheel events before Tk's class bindings and attach later widgets too."""
        for sequence in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            self.root.bind_class(self._scroll_bindtag, sequence, self._on_mousewheel, add="+")
        try:
            # Tk 8.7/9 reports Windows two-finger gestures separately from wheels.
            self.root.bind_class(
                self._scroll_bindtag, "<TouchpadScroll>", self._on_touchpad_scroll, add="+"
            )
        except tk.TclError:
            # Tk 8.6 does not define this event; its touchpad input uses MouseWheel.
            pass
        self.root.bind_all("<Map>", self._attach_mousewheel_bindtag, add="+")
        self._attach_mousewheel_bindtag_tree(self.root)

    def _attach_mousewheel_bindtag_tree(self, widget: Any) -> None:
        self._attach_mousewheel_bindtag(widget)
        try:
            children = widget.winfo_children()
        except (AttributeError, tk.TclError):
            return
        for child in children:
            self._attach_mousewheel_bindtag_tree(child)

    def _attach_mousewheel_bindtag(self, event: Any) -> None:
        """Place the app's wheel handler after widget bindings but before Tk defaults."""
        widget = getattr(event, "widget", event)
        try:
            tags = tuple(widget.bindtags())
            if self._scroll_bindtag in tags:
                return
            # Keep per-widget actions (for example, finishing an inline edit) first.
            insert_at = 1 if tags else 0
            widget.bindtags((*tags[:insert_at], self._scroll_bindtag, *tags[insert_at:]))
        except (AttributeError, tk.TclError):
            return

    def _mousewheel_targets(self, event: Any) -> list[Any]:
        """Return scrollable widgets from the pointer target out through its parents."""
        try:
            pointer_x, pointer_y = self.root.winfo_pointerxy()
            widget = self.root.winfo_containing(pointer_x, pointer_y)
        except (AttributeError, tk.TclError, TypeError, ValueError):
            widget = None
        if widget is None:
            try:
                widget = self.root.winfo_containing(
                    int(getattr(event, "x_root", 0)), int(getattr(event, "y_root", 0))
                )
            except (AttributeError, tk.TclError, TypeError, ValueError):
                widget = None
        if widget is None:
            widget = getattr(event, "widget", None)

        targets: list[Any] = []
        while widget is not None:
            if isinstance(widget, (tk.Scrollbar, ttk.Scrollbar)):
                command = str(widget.cget("command")).strip().split()
                if command:
                    try:
                        target = self.root.nametowidget(command[0])
                    except (KeyError, tk.TclError):
                        target = None
                    if target is not None and target not in targets:
                        targets.append(target)
            if callable(getattr(widget, "yview_scroll", None)) and callable(
                getattr(widget, "yview", None)
            ) and widget not in targets:
                targets.append(widget)
            widget = getattr(widget, "master", None)
        return targets

    @staticmethod
    def _mousewheel_unit_delta(event: Any) -> float:
        number = getattr(event, "num", None)
        if number == 4:
            return -1.0
        if number == 5:
            return 1.0
        try:
            delta = float(getattr(event, "delta", 0) or 0)
        except (TypeError, ValueError):
            return 0.0
        if not delta:
            return 0.0
        # Classic Windows wheels use 120 per notch. Trackpads and high-resolution
        # wheels often emit much smaller deltas, so scale and accumulate those.
        if abs(delta) >= 120:
            return -delta / 120.0
        return -delta / 15.0

    def _touchpad_vertical_delta(self, event: Any) -> int:
        """Decode Tk's packed TouchpadScroll delta and return its vertical component."""
        try:
            packed_delta = int(getattr(event, "delta", 0) or 0)
        except (TypeError, ValueError):
            return 0
        if not packed_delta:
            return 0
        try:
            values = self.root.tk.call("tk::PreciseScrollDeltas", packed_delta)
            delta_x, delta_y = self.root.tk.splitlist(values)
            return int(delta_y)
        except (tk.TclError, TypeError, ValueError):
            # Keep compatibility with Tk builds that emit the packed event but
            # do not expose tk::PreciseScrollDeltas.
            delta_y = packed_delta & 0xFFFF
            return delta_y - 0x10000 if delta_y & 0x8000 else delta_y

    @staticmethod
    def _touchpad_unit_height(target: Any) -> int:
        """Estimate one row for controls that cannot scroll by pixels."""
        if isinstance(target, ttk.Treeview):
            try:
                style_name = str(target.cget("style") or "Treeview")
                row_height = ttk.Style(target).lookup(style_name, "rowheight")
                if row_height:
                    return max(1, int(float(row_height)))
            except (tk.TclError, TypeError, ValueError):
                pass

        if isinstance(target, tk.Listbox):
            try:
                visible_rows = max(1, int(target.cget("height")))
                return max(1, int(target.winfo_height() / visible_rows))
            except (tk.TclError, TypeError, ValueError):
                pass
        return 20

    def _on_touchpad_scroll(self, event: Any) -> str | None:
        """Apply Tk 8.7/9 two-finger deltas to the scroll area under the pointer."""
        delta_y = self._touchpad_vertical_delta(event)
        if not delta_y:
            return None
        # Tk's packed delta uses the opposite sign from yview_scroll units.
        direction = -1 if delta_y > 0 else 1
        targets = self._mousewheel_targets(event)
        if not targets:
            return None

        for target in targets:
            try:
                first, last = target.yview()
                at_start = direction < 0 and float(first) <= 0
                at_end = direction > 0 and float(last) >= 1
                if at_start or at_end:
                    if target is self._finance_dropdown_canvas:
                        target = self.transcript
                        first, last = target.yview()
                        if (direction < 0 and float(first) <= 0) or (
                            direction > 0 and float(last) >= 1
                        ):
                            continue
                    else:
                        continue

                if getattr(target, "_bk_smooth_scroll", False):
                    self._scroll_canvas_pixels(target, -delta_y)
                    return "break"
                try:
                    # Tk 9 converts precise deltas into smooth movement for
                    # widgets that expose the standard xview/yview interface.
                    self.root.tk.call("tk::ScrollByPixels", target._w, 0, delta_y)
                except tk.TclError:
                    # Treeview/Listbox scroll by rows. Accumulate the high-rate
                    # touchpad deltas so they move only after a visible row's worth.
                    unit_delta = -delta_y / self._touchpad_unit_height(target)
                    accumulated = self._touchpad_scroll_remainders.get(target, 0.0) + unit_delta
                    amount = int(accumulated)
                    self._touchpad_scroll_remainders[target] = accumulated - amount
                    if amount:
                        target.yview_scroll(amount, "units")
                return "break"
            except (AttributeError, tk.TclError, TypeError, ValueError):
                continue

        return "break"

    @staticmethod
    def _scroll_canvas_pixels(target: Any, pixels: float) -> None:
        target._bk_pending_scroll = getattr(target, "_bk_pending_scroll", 0.0) + pixels
        if getattr(target, "_bk_scroll_animation", None) is not None:
            return
        def advance() -> None:
            try:
                pending = target._bk_pending_scroll
                amount = pending if abs(pending) < 1 else pending * .48
                bounds = target.tk.splitlist(target.cget("scrollregion"))
                height = max(1.0, float(bounds[3])-float(bounds[1])) if len(bounds)==4 else 1.0
                target.yview_moveto(float(target.yview()[0])+amount/height)
                target._bk_pending_scroll -= amount
                if abs(target._bk_pending_scroll) > .05:
                    target._bk_scroll_animation = target.after(12, advance)
                else:
                    target._bk_pending_scroll = 0.0
                    target._bk_scroll_animation = None
            except tk.TclError:
                pass
        target._bk_scroll_animation = target.after(0, advance)

    def _on_mousewheel(self, event: Any) -> str | None:
        """Route smooth wheel/trackpad input to the scroll area under the pointer."""
        unit_delta = self._mousewheel_unit_delta(event)
        if not unit_delta:
            return None

        targets = self._mousewheel_targets(event)
        if not targets:
            return None

        direction = 1 if unit_delta > 0 else -1
        for target in targets:
            try:
                first, last = target.yview()
                at_start = direction < 0 and float(first) <= 0
                at_end = direction > 0 and float(last) >= 1
                if at_start or at_end:
                    if target is self._finance_dropdown_canvas:
                        target = self.transcript
                        first, last = target.yview()
                        if (direction < 0 and float(first) <= 0) or (
                            direction > 0 and float(last) >= 1
                        ):
                            continue
                    else:
                        continue

                if getattr(target, "_bk_smooth_scroll", False):
                    self._scroll_canvas_pixels(target, unit_delta*44)
                    return "break"
                accumulated = self._scroll_remainders.get(target, 0.0) + unit_delta
                amount = int(accumulated)
                self._scroll_remainders[target] = accumulated - amount
                if amount:
                    target.yview_scroll(amount, "units")
                # Consume partial deltas too, so Tk's class binding cannot scroll
                # the focused widget instead of the control under the pointer.
                return "break"
            except (AttributeError, tk.TclError, TypeError, ValueError):
                continue

        # All nested scroll areas are already at the edge in this direction.
        return "break"

    def _install_copy_support(self) -> None:
        """Add standard edit commands and copy menus throughout the app."""
        for widget_class in (
            "TLabel",
            "Label",
            "Text",
            "Entry",
            "TEntry",
            "TCombobox",
            "TSpinbox",
            "Treeview",
        ):
            self.root.bind_class(
                widget_class,
                "<Button-3>",
                self._show_copy_context_menu,
                add="+",
            )
        self.root.bind_class(
            "Text", "<Control-c>", self._copy_readonly_text_selection, add="+"
        )
        self.root.bind_class(
            "Text", "<Control-C>", self._copy_readonly_text_selection, add="+"
        )
        self.root.bind_class(
            "Text", "<Control-a>", self._select_all_readonly_text, add="+"
        )
        self.root.bind_class(
            "Text", "<Control-A>", self._select_all_readonly_text, add="+"
        )
        # Tk's Text undo bindings vary by platform. Use the widget's native
        # undo stack directly so Ctrl+Z / Ctrl+Y behave consistently on Windows.
        self.root.bind_class("Text", "<Control-z>", self._undo_text_shortcut)
        self.root.bind_class("Text", "<Control-y>", self._redo_text_shortcut)
        for widget_class in ("Entry", "TEntry", "TCombobox", "TSpinbox"):
            self.root.bind_class(
                widget_class,
                "<Control-a>",
                self._select_all_readonly_text,
                add="+",
            )
            self.root.bind_class(
                widget_class, "<FocusIn>", self._prepare_entry_history, add="+"
            )
            self.root.bind_class(
                widget_class,
                "<KeyRelease>",
                self._schedule_entry_history_capture,
                add="+",
            )
            self.root.bind_class(
                widget_class,
                "<<Paste>>",
                self._schedule_entry_history_capture,
                add="+",
            )
            self.root.bind_class(
                widget_class,
                "<<Cut>>",
                self._schedule_entry_history_capture,
                add="+",
            )
            self.root.bind_class(
                widget_class,
                "<<Clear>>",
                self._schedule_entry_history_capture,
                add="+",
            )
            self.root.bind_class(widget_class, "<Control-z>", self._undo_entry_shortcut)
            self.root.bind_class(widget_class, "<Control-y>", self._redo_entry_shortcut)
            self.root.bind_class(
                widget_class,
                "<Control-A>",
                self._select_all_readonly_text,
                add="+",
            )
        self.root.bind_class(
            "Treeview", "<Control-c>", self._copy_treeview_selection, add="+"
        )
        self.root.bind_class(
            "Treeview", "<Control-C>", self._copy_treeview_selection, add="+"
        )

    def _copy_to_clipboard(self, text: str) -> None:
        if not text:
            return
        try:
            self.root.clipboard_clear()
            self.root.clipboard_append(text)
            self.root.update_idletasks()
        except tk.TclError:
            return

    def _widget_display_text(self, widget: tk.Widget) -> str:
        try:
            text = str(widget.cget("text") or "")
            variable = str(widget.cget("textvariable") or "")
        except tk.TclError:
            return ""
        if variable:
            try:
                text = str(self.root.getvar(variable) or "")
            except (tk.TclError, ValueError):
                pass
        return text.strip()

    def _treeview_selection_text(self, widget: ttk.Treeview) -> str:
        selected = list(widget.selection())
        if not selected:
            return ""
        headings = [
            str(widget.heading(column, "text") or "")
            for column in widget.cget("columns")
        ]
        rows = [
            [str(value) for value in widget.item(item_id, "values")]
            for item_id in selected
        ]
        lines = ["\t".join(headings)] if headings and any(headings) else []
        lines.extend("\t".join(row) for row in rows)
        return "\n".join(lines)

    def _clear_selection_on_noninteractive_click(self, event: Any) -> None:
        """Clear list selections after clicks outside rows and interactive controls."""
        widget = getattr(event, "widget", None)
        if not isinstance(widget, tk.Misc):
            return

        preserved_classes = {
            "TButton",
            "Button",
            "TRadiobutton",
            "Radiobutton",
            "TCheckbutton",
            "Checkbutton",
            "TMenubutton",
            "Menubutton",
            "Menu",
            "TEntry",
            "Entry",
            "TCombobox",
            "TSpinbox",
            "Spinbox",
            "Text",
        }
        try:
            if widget.winfo_class() in preserved_classes:
                return
            if isinstance(widget, ttk.Treeview) and widget.identify_row(event.y):
                return
            if isinstance(widget, tk.Listbox):
                index = widget.nearest(event.y)
                bounds = widget.bbox(index) if index >= 0 else None
                if bounds and bounds[1] <= event.y < bounds[1] + bounds[3]:
                    return
            window = widget.winfo_toplevel()
        except tk.TclError:
            return

        def clear_descendant_selections(parent: tk.Misc) -> None:
            try:
                children = parent.winfo_children()
            except tk.TclError:
                return
            for child in children:
                if isinstance(child, ttk.Treeview):
                    selected = child.selection()
                    if selected:
                        child.selection_remove(*selected)
                elif isinstance(child, tk.Listbox) and child.curselection():
                    child.selection_clear(0, "end")
                clear_descendant_selections(child)

        clear_descendant_selections(window)

    def _show_copy_context_menu(self, event: Any) -> str | None:
        widget = event.widget
        menu = tk.Menu(widget, tearoff=False)
        if isinstance(widget, (ttk.Label, tk.Label)):
            text = self._widget_display_text(widget)
            if not text:
                menu.destroy()
                return None
            menu.add_command(
                label=translate("复制文字", self.language),
                command=lambda: self._copy_to_clipboard(text),
            )
        elif isinstance(widget, tk.Text) and str(widget.cget("state")) != "disabled":
            try:
                can_undo = bool(widget.edit_canundo())
            except tk.TclError:
                can_undo = False
            try:
                can_redo = bool(widget.edit_canredo())
            except tk.TclError:
                can_redo = False
            try:
                selected = widget.get("sel.first", "sel.last")
            except tk.TclError:
                selected = ""
            menu.add_command(
                label=translate("撤销", self.language),
                state="normal" if can_undo else "disabled",
                command=lambda: self._undo_text_widget(widget),
            )
            menu.add_command(
                label=translate("重做", self.language),
                state="normal" if can_redo else "disabled",
                command=lambda: self._redo_text_widget(widget),
            )
            menu.add_separator()
            menu.add_command(
                label=translate("剪切", self.language),
                state="normal" if selected else "disabled",
                command=lambda: self._generate_widget_event(widget, "<<Cut>>"),
            )
            menu.add_command(
                label=translate("复制选中内容", self.language),
                state="normal" if selected else "disabled",
                command=lambda: self._generate_widget_event(widget, "<<Copy>>"),
            )
            menu.add_command(
                label=translate("粘贴", self.language),
                state="normal" if self._clipboard_has_text(widget) else "disabled",
                command=lambda: self._generate_widget_event(widget, "<<Paste>>"),
            )
            menu.add_command(
                label=translate("删除", self.language),
                state="normal" if selected else "disabled",
                command=lambda: self._generate_widget_event(widget, "<<Clear>>"),
            )
            menu.add_separator()
            menu.add_command(
                label=translate("全选", self.language),
                command=lambda: self._select_all_widget_text(widget),
            )
        elif self._is_entry_widget(widget):
            state = str(widget.cget("state"))
            editable = state not in {"disabled", "readonly"}
            history = self._entry_edit_history(widget)
            self._capture_entry_history(widget)
            try:
                selected = widget.selection_get() if widget.selection_present() else ""
            except (tk.TclError, AttributeError):
                selected = ""
            has_clipboard = self._clipboard_has_text(widget)
            menu.add_command(
                label=translate("撤销", self.language),
                state="normal" if editable and len(history["undo"]) > 1 else "disabled",
                command=lambda: self._undo_entry(widget),
            )
            menu.add_command(
                label=translate("重做", self.language),
                state="normal" if editable and history["redo"] else "disabled",
                command=lambda: self._redo_entry(widget),
            )
            menu.add_separator()
            menu.add_command(
                label=translate("剪切", self.language),
                state="normal" if editable and selected else "disabled",
                command=lambda: self._perform_edit_command(widget, "<<Cut>>"),
            )
            menu.add_command(
                label=translate("复制", self.language),
                state="normal" if selected else "disabled",
                command=lambda: self._perform_edit_command(widget, "<<Copy>>"),
            )
            menu.add_command(
                label=translate("粘贴", self.language),
                state="normal" if editable and has_clipboard else "disabled",
                command=lambda: self._perform_edit_command(widget, "<<Paste>>"),
            )
            menu.add_command(
                label=translate("删除", self.language),
                state="normal" if editable and selected else "disabled",
                command=lambda: self._perform_edit_command(widget, "<<Clear>>"),
            )
            menu.add_separator()
            menu.add_command(
                label=translate("全选", self.language),
                state="normal" if widget.get() else "disabled",
                command=lambda: self._select_all_widget_text(widget),
            )
        elif isinstance(widget, tk.Text):
            if str(widget.cget("state")) != "disabled":
                menu.destroy()
                return None
            try:
                selected = widget.get("sel.first", "sel.last")
            except tk.TclError:
                selected = ""
            menu.add_command(
                label=translate("复制选中内容", self.language),
                state="normal" if selected else "disabled",
                command=lambda: self._copy_to_clipboard(selected),
            )
            menu.add_command(
                label=translate("复制全部文字", self.language),
                command=lambda: self._copy_to_clipboard(widget.get("1.0", "end-1c")),
            )
            menu.add_command(
                label=translate("全选", self.language),
                command=lambda: self._select_all_widget_text(widget),
            )
        elif isinstance(widget, ttk.Treeview):
            row_id = widget.identify_row(event.y)
            if row_id and row_id not in widget.selection():
                widget.selection_set(row_id)
            selected_text = self._treeview_selection_text(widget)
            if not selected_text:
                menu.destroy()
                return None
            menu.add_command(
                label=translate("复制选中行", self.language),
                command=lambda: self._copy_to_clipboard(selected_text),
            )
        else:
            menu.destroy()
            return None
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()
        return "break"

    def _copy_readonly_text_selection(self, event: Any) -> str | None:
        widget = event.widget
        if not isinstance(widget, tk.Text) or str(widget.cget("state")) != "disabled":
            return None
        try:
            self._copy_to_clipboard(widget.get("sel.first", "sel.last"))
        except tk.TclError:
            return None
        return "break"

    @staticmethod
    def _is_entry_widget(widget: Any) -> bool:
        try:
            return str(widget.winfo_class()) in {
                "Entry",
                "TEntry",
                "TCombobox",
                "TSpinbox",
                "Spinbox",
            }
        except (AttributeError, tk.TclError):
            return False

    @staticmethod
    def _select_all_widget_text(widget: Any) -> None:
        if isinstance(widget, tk.Text):
            widget.tag_add("sel", "1.0", "end-1c")
            widget.mark_set("insert", "end-1c")
            widget.see("insert")
        elif BookkeepingWindow._is_entry_widget(widget):
            widget.selection_range(0, "end")
            widget.icursor("end")

    @staticmethod
    def _select_all_readonly_text(event: Any) -> str | None:
        widget = event.widget
        if isinstance(widget, tk.Text):
            widget.tag_add("sel", "1.0", "end-1c")
            widget.mark_set("insert", "end-1c")
            widget.see("insert")
        elif BookkeepingWindow._is_entry_widget(widget):
            if str(widget.cget("state")) == "disabled":
                return None
            widget.selection_range(0, "end")
            widget.icursor("end")
        else:
            return None
        return "break"

    @staticmethod
    def _generate_widget_event(widget: tk.Widget, sequence: str) -> None:
        try:
            widget.event_generate(sequence)
        except tk.TclError:
            pass

    def _perform_edit_command(self, widget: tk.Widget, sequence: str) -> None:
        self._generate_widget_event(widget, sequence)
        if self._is_entry_widget(widget):
            try:
                widget.after_idle(lambda target=widget: self._capture_entry_history(target))
            except tk.TclError:
                pass

    def _entry_edit_history(self, widget: tk.Widget) -> dict[str, list[tuple[str, int]]]:
        history = getattr(widget, "_bookkeeping_edit_history", None)
        if isinstance(history, dict):
            return history
        history: dict[str, list[tuple[str, int]]] = {"undo": [], "redo": []}
        try:
            history["undo"].append((str(widget.get()), int(widget.index("insert"))))
            setattr(widget, "_bookkeeping_edit_history", history)
        except (AttributeError, tk.TclError, TypeError, ValueError):
            pass
        return history

    def _prepare_entry_history(self, event: Any) -> None:
        widget = event.widget
        if self._is_entry_widget(widget):
            self._entry_edit_history(widget)

    def _schedule_entry_history_capture(self, event: Any) -> None:
        widget = event.widget
        if not self._is_entry_widget(widget):
            return
        try:
            widget.after_idle(lambda target=widget: self._capture_entry_history(target))
        except tk.TclError:
            pass

    def _capture_entry_history(self, widget: tk.Widget) -> None:
        if not self._is_entry_widget(widget):
            return
        history = self._entry_edit_history(widget)
        try:
            snapshot = (str(widget.get()), int(widget.index("insert")))
        except (tk.TclError, TypeError, ValueError):
            return
        if not history["undo"]:
            history["undo"].append(snapshot)
        elif history["undo"][-1][0] != snapshot[0]:
            history["undo"].append(snapshot)
            history["redo"].clear()

    def _restore_entry_snapshot(self, widget: tk.Widget, snapshot: tuple[str, int]) -> None:
        if str(widget.cget("state")) in {"disabled", "readonly"}:
            return
        text, insert_index = snapshot
        try:
            variable = str(widget.cget("textvariable") or "")
            if variable:
                self.root.setvar(variable, text)
            else:
                widget.delete(0, "end")
                widget.insert(0, text)
            widget.icursor(min(insert_index, len(text)))
        except (AttributeError, tk.TclError, TypeError):
            pass

    def _undo_entry(self, widget: tk.Widget) -> None:
        history = self._entry_edit_history(widget)
        self._capture_entry_history(widget)
        if len(history["undo"]) <= 1:
            return
        history["redo"].append(history["undo"].pop())
        self._restore_entry_snapshot(widget, history["undo"][-1])

    def _redo_entry(self, widget: tk.Widget) -> None:
        history = self._entry_edit_history(widget)
        self._capture_entry_history(widget)
        if not history["redo"]:
            return
        snapshot = history["redo"].pop()
        history["undo"].append(snapshot)
        self._restore_entry_snapshot(widget, snapshot)

    def _undo_entry_shortcut(self, event: Any) -> str | None:
        widget = event.widget
        if self._is_entry_widget(widget) and str(widget.cget("state")) not in {
            "disabled",
            "readonly",
        }:
            self._undo_entry(widget)
            return "break"
        return None

    def _redo_entry_shortcut(self, event: Any) -> str | None:
        widget = event.widget
        if self._is_entry_widget(widget) and str(widget.cget("state")) not in {
            "disabled",
            "readonly",
        }:
            self._redo_entry(widget)
            return "break"
        return None

    def _undo_text_shortcut(self, event: Any) -> str | None:
        widget = event.widget
        if isinstance(widget, tk.Text) and str(widget.cget("state")) != "disabled":
            self._undo_text_widget(widget)
            return "break"
        return None

    def _redo_text_shortcut(self, event: Any) -> str | None:
        widget = event.widget
        if isinstance(widget, tk.Text) and str(widget.cget("state")) != "disabled":
            self._redo_text_widget(widget)
            return "break"
        return None

    @staticmethod
    def _undo_text_widget(widget: tk.Text) -> None:
        try:
            widget.edit_undo()
        except tk.TclError:
            pass

    @staticmethod
    def _redo_text_widget(widget: tk.Text) -> None:
        try:
            widget.edit_redo()
        except tk.TclError:
            pass

    @staticmethod
    def _clipboard_has_text(widget: tk.Widget) -> bool:
        try:
            return bool(widget.clipboard_get())
        except tk.TclError:
            return False

    def _copy_treeview_selection(self, event: Any) -> str | None:
        widget = event.widget
        if not isinstance(widget, ttk.Treeview):
            return None
        self._copy_to_clipboard(self._treeview_selection_text(widget))
        return "break"

    def _check_due_credit_repayments(self) -> None:
        if self.busy or self._github_restore_in_progress:
            try:
                self.root.after(60_000, self._check_due_credit_repayments)
            except tk.TclError:
                pass
            return
        try:
            database = Database(self.database_path)
            try:
                database.initialize()
                events = process_due_credit_repayments(database, _today_japan())
            finally:
                database.close()
            for event in events:
                if event["status"] == "posted":
                    amount = minor_to_text(
                        int(event["amount_minor"]),
                        0 if event["currency"] == "JPY" else 2,
                        event["currency"],
                    )
                    self._append_message(
                        "助手",
                        f"已按本期单独填写的金额在本地账本记入 #{event['transaction_id']}："
                        f"{event['source_name']} → {event['card_name']}，{amount}。"
                        "这只是账本记录，不代表软件从银行实际扣款。",
                        agent_mode="bookkeeping",
                    )
                elif event["status"] == "insufficient":
                    self.status.configure(
                        text=f"{event['card_name']}本期填写的还款金额超过扣款账户余额，未记账；请核对。"
                    )
                elif event["status"] == "missed":
                    self.status.configure(
                        text=f"信用卡每月应还日期 {event['due_date']} 已过，软件未自动补记；请核对实际扣款。"
                    )
                elif event["status"] == "amount_missing":
                    self.status.configure(
                        text=f"{event['card_name']}今天是还款日，但本期金额未填写，未记账。"
                    )
                elif event["status"] == "partial_payment":
                    self.status.configure(
                        text=f"{event['card_name']}今天已有部分还款记录，软件没有自动补差；请核对本期金额。"
                    )
                elif event["status"] == "already_paid":
                    self.status.configure(
                        text=f"{event['card_name']}今天已有还款记录，本期计划没有重复记账。"
                    )
                elif event["status"] == "invalid":
                    self.status.configure(text=f"{event['card_name']}的每月应还计划设置有误，未记账。")
            if any(event["status"] == "posted" for event in events):
                self._queue_github_auto_sync()
        except (LedgerError, OSError, sqlite3.Error) as exc:
            self.status.configure(text=f"自动还款计划检查失败：{exc}")
        finally:
            try:
                self.root.after(60_000, self._check_due_credit_repayments)
            except tk.TclError:
                pass

    def _check_due_recurring_transactions(self) -> None:
        if self.busy or self._recurring_processing or self._github_restore_in_progress:
            try:
                self.root.after(60_000, self._check_due_recurring_transactions)
            except tk.TclError:
                pass
            return

        self._recurring_processing = True

        def process() -> None:
            database: Database | None = None
            try:
                database = Database(self.database_path)
                database.initialize()
                events = process_due_recurring_transactions(database, _today_japan())
                self.recurring_results.put((events, None))
            except Exception as exc:
                self.recurring_results.put(([], str(exc)))
            finally:
                if database is not None:
                    try:
                        database.close()
                    except sqlite3.Error:
                        pass

        threading.Thread(target=process, name="recurring-transactions", daemon=True).start()
        try:
            self.root.after(60_000, self._check_due_recurring_transactions)
        except tk.TclError:
            pass

    def _poll_recurring_transaction_results(self) -> None:
        try:
            events, error = self.recurring_results.get_nowait()
        except queue.Empty:
            events, error = None, None
        if events is not None:
            self._recurring_processing = False
            if error:
                self.status.configure(text=f"定期收支计划检查失败：{error}")
            else:
                posted = [event for event in events if event["status"] == "posted"]
                matched = [event for event in events if event["status"] == "matched"]
                failed = [event for event in events if event["status"] == "failed"]
                limited = [event for event in events if event["status"] == "catchup_limited"]
                if posted:
                    details = []
                    for event in posted[:3]:
                        amount = minor_to_text(
                            int(event["amount_minor"]),
                            0 if event["currency"] == "JPY" else 2,
                            event["currency"],
                        )
                        if event.get("account_amount_minor") is not None:
                            account_currency = str(event["account_currency"])
                            account_amount = minor_to_text(
                                int(event["account_amount_minor"]),
                                0 if account_currency == "JPY" else 2,
                                account_currency,
                            )
                            fx_note = (
                                f"，按{event['account_fx_rate_date']}参考汇率"
                                f"{event['account_fx_rate']} {account_currency}/{event['currency']}折算"
                            )
                            details.append(
                                f"{event['due_date']} {event['name']} 账单{amount}，账户扣款{account_amount}{fx_note}"
                            )
                        else:
                            details.append(f"{event['due_date']} {event['name']} {amount}")
                    suffix = f"；另有{len(posted) - 3}笔" if len(posted) > 3 else ""
                    self._append_message(
                        "助手",
                        f"定期收支已在本地账本自动记入{len(posted)}笔：{'；'.join(details)}{suffix}。"
                        "这只是账本记录，不代表银行已实际付款或收款。",
                        agent_mode="bookkeeping",
                    )
                    if not failed and not limited:
                        self.status.configure(text=f"定期收支已在本地账本自动记入 {len(posted)} 笔。")
                if matched:
                    self.status.configure(text=f"定期收支已匹配 {len(matched)} 条现有账本流水，没有重复记账。")
                if failed:
                    first = failed[0]
                    self.status.configure(text=f"定期收支“{first['name']}”处理失败，未推进日期：{first['error']}")
                elif limited:
                    self.status.configure(text="某项定期收支积欠超过100期；本轮已处理100期，将继续分批补记。")
                if posted:
                    self._queue_github_auto_sync()
        try:
            self.root.after(250, self._poll_recurring_transaction_results)
        except tk.TclError:
            pass

    def _cloud_stores(self):
        return dict(payment_store=self.payment_prompt_store,
                    bookkeeping_skill_store=self.skill_store,
                    food_skill_store=self.food_health_skill_store,
                    receipt_image_directory=self.database_path.parent / 'receipt_images')

    def _pull_state(self):
        return PullState(app_data_directory() / 'cloud_pull_state.json')

    def _mark_cloud_checkpoint(self, provider, repository, sha, revision=None):
        self._pull_state().synced(provider, repository, sha,
                                 revision or local_revision(self.database_path, **self._cloud_stores()))

    def _start_startup_cloud_pull(self):
        if self.busy or self._recurring_processing:
            self.root.after(500, self._start_startup_cloud_pull)
            return
        if self._github_restore_in_progress:
            return
        self._github_restore_in_progress = True
        self.send_button.configure(state='disabled')
        self.input_box.configure(state='disabled')
        self.status.configure(text=translate('正在检查云端最新账本…', self.language))
        def work():
            try:
                candidates = []
                for provider, settings_store, token_store in (
                    ('github', GitHubSyncSettingsStore(), GitHubTokenStore()),
                    ('gitee', GiteeSyncSettingsStore(), GiteeTokenStore()),
                ):
                    settings = settings_store.load()
                    repository = settings.get('repository', '')
                    if provider == 'github':
                        credentials = token_store.load_credentials()
                        token = credentials.get('access_token', '')
                        if not token or not repository:
                            continue
                        client = GitHubClient(token, refresh_token=credentials.get('refresh_token', ''),
                                              client_id=GITHUB_APP_CLIENT_ID, token_store=token_store)
                    else:
                        token = token_store.load()
                        if not token or not repository:
                            continue
                        client = GiteeClient(token)
                    if not token or not repository:
                        continue
                    def save(sha, store=settings_store, cfg=settings):
                        store.save(repository_name=cfg['repository_name'], repository=cfg['repository'], last_sync_sha=sha)
                    candidates.append((provider, repository, client, save))
                if candidates:
                    def restore(body, provider):
                        self._startup_applying = True
                        if self._startup_cancelled.is_set():
                            raise LedgerError('自动下载已取消，本机账本保持原样。')
                        return restore_sync_bundle(body, self.database_path,
                            **self._cloud_stores(), backup_provider=provider)
                    with self._github_upload_lock, github_sync_process_lock():
                        result = automatic_pull(self.database_path, candidates, self._pull_state(),
                            restore,
                            stores=self._cloud_stores(), cancelled=self._startup_cancelled.is_set)
                else:
                    result = {'status': 'unconnected', 'restored': False}
                self._startup_results.put((result, ''))
            except Exception as exc:
                self._startup_results.put(({}, str(exc)))
            finally:
                self._startup_applying = False
        threading.Thread(target=work, name='startup-cloud-download', daemon=True).start()
        self.root.after(100, self._poll_startup_cloud_pull)

    def _poll_startup_cloud_pull(self):
        try:
            result, error = self._startup_results.get_nowait()
        except queue.Empty:
            self.root.after(100, self._poll_startup_cloud_pull)
            return
        try:
            if result.get('restored'):
                self._clear_conversation_context()
                self._reload_payment_profiles()
                self.loaded_skill = self.skill_store.load()
                self.loaded_food_health_skill = self.food_health_skill_store.load()
                self._update_skill_summary()
                self.status.configure(text=translate('已自动下载最新云端账本，恢复前已备份本机数据。', self.language))
            elif error:
                self.status.configure(text=translate('自动下载未完成：{error}', self.language).format(error=translate(error, self.language)))
            elif result.get('status') == 'current':
                self.status.configure(text=translate('当前已是最新云端账本。', self.language))
            else:
                self.status.configure(text='')
        finally:
            self._github_restore_in_progress = False
            self.send_button.configure(state='normal')
            self.input_box.configure(state='normal')
            self.desktop_shell.refresh()

    def _queue_github_auto_sync(self) -> None:
        """Upload the latest full snapshot after a successful ledger mutation."""
        if hasattr(self, "desktop_shell"):
            # Successful writes already pass through this UI-thread entry point.
            self.desktop_shell.refresh()
        self._queue_gitee_auto_sync()
        if not self.github_auto_sync_enabled or self._github_restore_in_progress:
            return
        with self._github_auto_sync_state_lock:
            self._github_auto_sync_pending = True
            if self._github_auto_sync_running:
                return
            self._github_auto_sync_running = True
        try:
            threading.Thread(
                target=self._run_github_auto_sync,
                name="github-ledger-auto-sync",
                daemon=True,
            ).start()
        except RuntimeError as exc:
            with self._github_auto_sync_state_lock:
                self._github_auto_sync_pending = False
                self._github_auto_sync_running = False
            self._publish_github_auto_sync_status(
                translate("GitHub 自动同步无法启动：{error}", self.language).format(error=exc)
            )

    def _queue_gitee_auto_sync(self) -> None:
        """Queue an independent Gitee snapshot after a successful ledger mutation."""
        if not self.gitee_auto_sync_enabled or self._github_restore_in_progress:
            return
        with self._gitee_auto_sync_state_lock:
            self._gitee_auto_sync_pending = True
            if self._gitee_auto_sync_running:
                return
            self._gitee_auto_sync_running = True
        try:
            threading.Thread(
                target=self._run_gitee_auto_sync,
                name="gitee-ledger-auto-sync",
                daemon=True,
            ).start()
        except RuntimeError as exc:
            with self._gitee_auto_sync_state_lock:
                self._gitee_auto_sync_pending = False
                self._gitee_auto_sync_running = False
            self._publish_github_auto_sync_status(
                translate("Gitee 自动同步无法启动：{error}", self.language).format(error=exc)
            )

    def _run_gitee_auto_sync(self) -> None:
        while True:
            with self._gitee_auto_sync_state_lock:
                if not self._gitee_auto_sync_pending:
                    self._gitee_auto_sync_running = False
                    return
                self._gitee_auto_sync_pending = False

            if not self.gitee_auto_sync_enabled or self._github_restore_in_progress:
                with self._gitee_auto_sync_state_lock:
                    self._gitee_auto_sync_pending = False
                    self._gitee_auto_sync_running = False
                return

            try:
                with self._github_upload_lock, github_sync_process_lock():
                    settings_store = GiteeSyncSettingsStore()
                    settings = settings_store.load()
                    token = GiteeTokenStore().load()
                    repository = settings.get("repository", "")
                    if not token or not repository:
                        with self._gitee_auto_sync_state_lock:
                            self._gitee_auto_sync_pending = False
                            self._gitee_auto_sync_running = False
                        return
                    client = GiteeClient(token)
                    with tempfile.TemporaryDirectory(prefix="household-gitee-auto-upload-") as temp_name:
                        bundle_path = Path(temp_name) / "sync-bundle.zip"
                        sync_revision = local_revision(self.database_path, **self._cloud_stores())
                        bundle = create_sync_bundle(
                            self.database_path,
                            bundle_path,
                            receipt_image_directory=self.database_path.parent / "receipt_images",
                            max_bundle_bytes=MAX_GITEE_SYNC_BUNDLE_BYTES,
                            max_bundle_error="Gitee 同步包超过 45 MiB；请减少小票图片后重试。",
                        )
                        new_sha = client.upload_bundle(
                            repository,
                            bundle,
                            expected_sha=settings.get("last_sync_sha", "") or None,
                        )
                    settings_store.save(
                        repository_name=settings.get(
                            "repository_name", DEFAULT_GITEE_BACKUP_REPOSITORY_NAME
                        ),
                        repository=repository,
                        last_sync_sha=new_sha,
                    )
                    self._mark_cloud_checkpoint('gitee', repository, new_sha, sync_revision)
                self._publish_github_auto_sync_status(
                    translate("账本已记录并同步到 Gitee。", self.language)
                )
            except Exception as exc:
                self._publish_github_auto_sync_status(
                    translate("账本已记录在本地，但 Gitee 自动同步失败：{error}", self.language).format(
                        error=translate(str(exc), self.language)
                    )
                )
                with self._gitee_auto_sync_state_lock:
                    self._gitee_auto_sync_pending = False
                    self._gitee_auto_sync_running = False
                return

    def _run_github_auto_sync(self) -> None:
        while True:
            with self._github_auto_sync_state_lock:
                if not self._github_auto_sync_pending:
                    self._github_auto_sync_running = False
                    return
                self._github_auto_sync_pending = False

            if not self.github_auto_sync_enabled:
                with self._github_auto_sync_state_lock:
                    self._github_auto_sync_pending = False
                    self._github_auto_sync_running = False
                return

            self._publish_github_auto_sync_status(
                translate("账本已记录，正在自动同步到 GitHub…", self.language)
            )
            try:
                with self._github_upload_lock, github_sync_process_lock():
                    settings_store = GitHubSyncSettingsStore()
                    settings = settings_store.load()
                    credentials = GitHubTokenStore().load_credentials()
                    repository = settings.get("repository", "")
                    if not credentials["access_token"] or not repository:
                        self._publish_github_auto_sync_status(
                            translate(
                                "账本已记录在本地；请先连接 GitHub，连接后会上传当前同步数据。",
                                self.language,
                            )
                        )
                        with self._github_auto_sync_state_lock:
                            self._github_auto_sync_pending = False
                            self._github_auto_sync_running = False
                        return
                    if not is_github_app_user_token(credentials["access_token"]):
                        raise GitHubSyncError("旧版 GitHub 授权需要更新；请重新连接 GitHub。")
                    client = GitHubClient(
                        credentials["access_token"],
                        refresh_token=credentials["refresh_token"],
                        client_id=GITHUB_APP_CLIENT_ID,
                        token_store=GitHubTokenStore(),
                    )
                    with tempfile.TemporaryDirectory(prefix="household-github-auto-upload-") as temp_name:
                        bundle_path = Path(temp_name) / "sync-bundle.zip"
                        sync_revision = local_revision(self.database_path, **self._cloud_stores())
                        bundle = create_sync_bundle(
                            self.database_path,
                            bundle_path,
                            receipt_image_directory=self.database_path.parent / "receipt_images",
                        )
                        new_sha = client.upload_bundle(
                            repository,
                            bundle,
                            expected_sha=settings.get("last_sync_sha", "") or None,
                        )
                    settings_store.save(
                        repository_name=settings.get("repository_name", DEFAULT_BACKUP_REPOSITORY_NAME),
                        repository=repository,
                        last_sync_sha=new_sha,
                    )
                    self._mark_cloud_checkpoint('github', repository, new_sha, sync_revision)
                self._publish_github_auto_sync_status(
                    translate("账本已记录并同步到 GitHub。", self.language)
                )
            except Exception as exc:
                self._publish_github_auto_sync_status(
                    translate("账本已记录在本地，但自动同步失败：{error}", self.language).format(
                        error=translate(str(exc), self.language)
                    )
                )
                with self._github_auto_sync_state_lock:
                    self._github_auto_sync_pending = False
                    self._github_auto_sync_running = False
                return

    def _publish_github_auto_sync_status(self, message: str) -> None:
        def update_status() -> None:
            try:
                if self.busy:
                    self.root.after(250, update_status)
                    return
                self.status.configure(text=message)
            except tk.TclError:
                pass

        try:
            self.root.after(0, update_status)
        except tk.TclError:
            pass

    def _build_widgets(self) -> None:
        configure_styles(self.root, self.ui_font_family)

        self.desktop_shell = DesktopShell(self)
        shell = ttk.Frame(self.desktop_shell.record_page, style="App.TFrame", padding=(20, 18, 20, 10))
        shell.place(relx=.5, y=0, anchor="n", relheight=1, height=-8, width=1136)
        def resize_record_shell(event=None):
            page = self.desktop_shell.record_page
            if defer_during_interactive_resize(
                    page, (page, "record-shell"), lambda: resize_record_shell()):
                return
            width = page.winfo_width() if event is None else event.width
            shell.place_configure(width=min(1136, max(360, width-8)))
        self.desktop_shell.record_page.bind("<Configure>", resize_record_shell)
        shell.columnconfigure(0, weight=0)
        shell.columnconfigure(1, weight=1)
        shell.rowconfigure(1, weight=1)

        heading = ttk.Frame(shell, style="App.TFrame")
        heading.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 14))
        heading.grid_remove()
        heading.columnconfigure(0, weight=1)
        hero = RoundedPanel(heading, padding=20, radius=24, surface=PALETTE["hero"])
        hero.grid(row=0, column=0, sticky="ew", padx=(0, 16))
        heading_title = hero.body
        ttk.Label(heading_title, text="每一笔，都清楚。", style="Hero.TLabel",
                  font=(self.ui_font_family, 23, "bold")).pack(anchor="w")
        self.settings_button = ttk.Button(heading, text="设置", style="Settings.TButton", command=self.open_settings)
        self.settings_button.grid(row=0, column=2, sticky="e", padx=(8, 0))
        self.finance_button = ttk.Button(heading, text="更多功能  ▾", style="HeaderPrimary.TButton", command=self._toggle_finance_dropdown)
        self.finance_button.grid(row=0, column=3, sticky="e", padx=(8, 0))
        self.restart_button = ttk.Button(heading, text="重启软件", style="Settings.TButton", command=self.restart_application)
        self.restart_button.grid(row=0, column=1, sticky="e", padx=(8, 0))
        self.heading_hint = ttk.Label(
            heading_title,
            text="记录日常，安心管理。",
            style="HeroHint.TLabel",
        )
        self.heading_hint.pack(anchor="w", pady=(6, 0))

        agent_sidebar = ttk.Frame(shell, style="App.TFrame", padding=(0, 0, 0, 14))
        agent_sidebar.grid(row=0, column=0, columnspan=2, sticky="ew")
        ttk.Label(agent_sidebar, text="记录", style="Title.TLabel").pack(side="left", padx=(0, 24))
        self.agent_buttons: dict[str, ttk.Button] = {}
        for mode, label in (("bookkeeping", "记账"), ("food_health", "饮食健康")):
            button = ttk.Button(agent_sidebar, text=label, style="Selected.Agent.TButton" if mode == self.agent_mode else "Agent.TButton",
                                command=lambda selected=mode: self._select_agent(selected))
            button.pack(side="left", padx=(0, 8))
            self.agent_buttons[mode] = button

        content = ttk.Frame(shell, style="App.TFrame")
        content.grid(row=1, column=0, columnspan=2, sticky="nsew")
        content.columnconfigure(0, weight=1)
        content.rowconfigure(0, weight=1)

        history_card = RoundedPanel(content, padding=16, radius=12)
        history_card.grid(row=0, column=0, sticky="nsew")
        history_frame = history_card.body
        tk.Label(history_frame, text="对话记账", bg=PALETTE["surface"], fg=PALETTE["text"],
                 font=(self.ui_font_family, 14, "bold"), anchor="w").pack(fill="x", pady=(0, 14))
        self.transcript = tk.Text(
            history_frame,
            wrap="word",
            state="disabled",
            relief="flat",
            borderwidth=0,
            padx=18,
            pady=16,
            background=color("#ffffff"),
            foreground=color("#344054"),
            font=(self.ui_font_family, 11),
            spacing1=3,
            spacing3=7,
        )
        scrollbar = ttk.Scrollbar(history_frame, orient="vertical", command=self.transcript.yview)
        self.transcript.configure(yscrollcommand=scrollbar.set)
        self.transcript.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        self.transcript.tag_configure("user", foreground=color("#175cd3"), font=(self.ui_font_family, 11, "bold"))
        self.transcript.tag_configure("assistant", foreground=color("#039855"), font=(self.ui_font_family, 11, "bold"))

        # Message text shares the transcript background. Reserve blue highlighting
        # for the real selection tag so selecting and copying still work normally.
        for message_tag in ("user_body", "assistant_body"):
            self.transcript.tag_configure(message_tag, background="",
                                          lmargin1=4, lmargin2=4, rmargin=28,
                                          spacing1=8, spacing3=10)
        self.status = ttk.Label(content, text="", style="Status.TLabel")
        self.status.grid(row=1, column=0, sticky="ew", pady=(12, 3))
        self.progress = ttk.Progressbar(content, mode="indeterminate", length=300)
        self.progress.grid(row=2, column=0, sticky="ew", pady=(0, 10))
        self.progress.grid_remove()

        compose_card = RoundedPanel(content, padding=14, radius=12)
        compose_card.grid(row=3, column=0, sticky="ew", pady=(5, 0))
        compose = compose_card.body
        compose.columnconfigure(0, weight=1)
        compose.rowconfigure(1, weight=1)
        attachment_toolbar = ttk.Frame(compose, style="Surface.TFrame")
        attachment_toolbar.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 6))
        self.add_image_button = ttk.Button(
            attachment_toolbar,
            text="＋ 添加图片",
            style="Settings.TButton",
            command=self.choose_images,
        )
        self.add_image_button.pack(side="left")
        self.attachment_hint = ttk.Label(attachment_toolbar, text="", style="SurfaceHint.TLabel")
        self.attachment_hint.pack(side="left", padx=(8, 0))
        self.attachments_frame = ttk.Frame(attachment_toolbar, style="Surface.TFrame")
        self.attachments_frame.pack(side="left", padx=(8, 0))
        self.input_box = tk.Text(
            compose,
            height=4,
            wrap="word",
            undo=True,
            relief="flat",
            borderwidth=0,
            highlightthickness=1,
            highlightbackground=PALETTE["border"],
            highlightcolor=PALETTE["accent"],
            padx=12,
            pady=10,
            background=color("#ffffff"),
            foreground=color("#182230"),
            insertbackground=color("#182230"),
            font=(self.ui_font_family, 11),
        )
        self.input_box.grid(row=1, column=0, sticky="nsew", padx=(0, 12))
        self.input_box.edit_modified(False)
        self.input_box.bind("<<Modified>>", self._refresh_input_after_change, add="+")
        self.input_box.bind("<Control-Return>", self._send_shortcut)
        self.input_box.bind("<Control-KP_Enter>", self._send_shortcut)
        self.drag_drop_enabled = False
        self.drag_drop_error: str | None = None
        if DND_FILES is None:
            self.drag_drop_error = "tkinterdnd2 未安装"
        else:
            registered_targets = 0
            # Register both the text widget and its surrounding attachment
            # area. TkDND selects the most specific target, so drops over the
            # input remain reliable while the toolbar is also a drop zone.
            for target in (self.input_box, attachment_toolbar, self.attachments_frame, compose):
                try:
                    target.drop_target_register(DND_FILES)
                    target.dnd_bind("<<Drop>>", self._handle_image_drop)
                    registered_targets += 1
                except (tk.TclError, AttributeError) as exc:
                    self.drag_drop_error = str(exc)[:160]
            self.drag_drop_enabled = registered_targets > 0
        request_buttons = ttk.Frame(compose, style="Surface.TFrame")
        request_buttons.grid(row=1, column=1, sticky="s")
        self.send_button = ttk.Button(request_buttons, text="发送记账", style="Send.TButton", command=self.send)
        self.send_button.pack(side="top", fill="x")
        self.interrupt_button = ttk.Button(
            request_buttons,
            text="中断任务",
            style="Settings.TButton",
            command=self.interrupt_task,
            state="disabled",
        )
        self.interrupt_button.pack(side="top", fill="x", pady=(6, 0))
        self.reset_conversation_button = ttk.Button(
            request_buttons,
            text=translate("重置对话", self.language),
            style="Settings.TButton",
            command=self._reset_current_conversation,
        )
        self.reset_conversation_button.pack(side="top", fill="x", pady=(6, 0))
        self._refresh_image_attachments()
        self.payment_hint_summary = ttk.Label(content, text="", style="Hint.TLabel")
        self.payment_hint_summary.grid(row=4, column=0, sticky="ew", pady=(8, 0))
        self.skill_summary = ttk.Label(content, text="", style="Hint.TLabel")
        self.skill_summary.grid(row=5, column=0, sticky="ew", pady=(3, 0))
        self.hint = ttk.Label(
            content,
            style="Hint.TLabel",
            wraplength=800,
        )
        def resize_hint(event):
            callback = lambda width=event.width: self.hint.configure(
                wraplength=max(320, width-8)
            )
            if defer_during_interactive_resize(content, (content, "hint-wrap"), callback):
                return
            callback()
        content.bind("<Configure>", resize_hint, add="+")
        self._update_payment_hint_summary()
        self._update_skill_summary()
        self._refresh_agent_view()

    def _select_agent(self, mode: str) -> None:
        if self.busy or mode not in self.agent_states or mode == self.agent_mode:
            return
        if self.pending_state is not None:
            self.status.configure(text=self._pending_workflow_message())
            return
        current = self.agent_states[self.agent_mode]
        current["history"] = self.history
        current["pending_state"] = self.pending_state
        self.agent_mode = mode
        self._clear_agent_clients(mode)
        selected = self.agent_states[mode]
        if not selected["messages"] and mode == "food_health":
            selected["messages"].append((
                "助手",
                "我会先检索本地近期饮食记录，再交给饮食健康 Agent 单独配置的模型和 Skill 给出均衡饮食建议。记录不足时会说明限制；此模式不会修改记录。",
            ))
        self.history = selected["history"]
        self.pending_state = selected["pending_state"]
        self._update_skill_summary()
        self._refresh_agent_view()

    def _refresh_agent_view(self) -> None:
        if not hasattr(self, "agent_buttons"):
            return
        is_food = self.agent_mode == "food_health"
        workflow_pending = self.pending_state is not None
        for mode, button in self.agent_buttons.items():
            active = mode == self.agent_mode
            button.configure(
                style="Selected.Agent.TButton" if active else "Agent.TButton",
                state="disabled" if self.busy or (workflow_pending and not active) else "normal",
            )
        self.heading_hint.configure(text="饮食回顾与健康建议" if is_food else "记录日常，安心管理。")
        self.send_button.configure(text="发送饮食咨询" if is_food else "发送记账")
        self.reset_conversation_button.configure(
            text=translate("重置对话", self.language),
            state="disabled" if self.busy else "normal",
        )
        self.attachment_hint.configure(
            text=(
                "可拖入食物图片；记录与饮食 Skill 会发给饮食 Agent 的模型"
                if is_food
                else "可拖入 JPG/PNG/WebP 图片到输入框或附件栏"
            )
        )
        if is_food:
            self.payment_hint_summary.grid_remove()
            self.skill_summary.grid()
            self.hint.grid(row=6, column=0, sticky="ew", pady=(4, 0))
            self.hint.configure(
                text="饮食健康 Agent 会检索本地饮食回顾，并将记录摘要、此 Agent 单独选择的 Skill 正文和本轮问题发送给当前消息对应的服务；附图消息使用含图片服务，纯文字消息使用纯文字服务。本机 Ollama 留在本机，远程服务会收到这些内容。此模式只提供饮食建议，不会写入记录。Enter 换行，Ctrl+Enter 发送。"
            )
        else:
            self.payment_hint_summary.grid()
            self.skill_summary.grid()
            self.hint.grid_remove()
        if workflow_pending:
            self.status.configure(text=self._pending_workflow_message())
        self.transcript.configure(state="normal")
        self.transcript.delete("1.0", "end")
        for speaker, body in self.agent_states[self.agent_mode]["messages"]:
            tag = "user" if speaker == "你" else "assistant"
            display_speaker = translate(speaker)
            separator = ": " if current_language() == "en-US" else "："
            if body in {
                "你好，直接告诉我一笔收入、消费、转账或还款。信息不够时我会先追问，确认后才写入本地账本。",
                "我会先检索本地近期饮食记录，再交给饮食健康 Agent 单独配置的模型和 Skill 给出均衡饮食建议。记录不足时会说明限制；此模式不会修改记录。",
            }:
                body = translate(body)
            self.transcript.insert("end", f"{display_speaker}{separator}", tag)
            self.transcript.insert("end", f"{body}\n\n", tag+"_body")
        self.transcript.see("end")
        self.transcript.configure(state="disabled")

    def _close_finance_dropdown(self) -> None:
        popup = self._finance_dropdown
        self._finance_dropdown = None
        self._finance_dropdown_canvas = None
        if popup is not None:
            try:
                popup.destroy()
            except tk.TclError:
                pass

    def _position_finance_dropdown(self, event: Any = None) -> None:
        if event is not None and event.widget is not self.root:
            return
        if self._finance_dropdown is not None:
            if defer_during_interactive_resize(
                    self.root, (self, "finance-dropdown"), self._place_finance_dropdown):
                return
            self.root.after_idle(self._place_finance_dropdown)

    def _place_finance_dropdown(self) -> None:
        popup = self._finance_dropdown
        if popup is None:
            return
        window_width = self.root.winfo_width()
        window_height = self.root.winfo_height()
        if window_width <= 1 or window_height <= 1:
            return
        width, desired_height = min(286, window_width - 16), min(360, max(200, window_height - 48))
        anchor_x = self.finance_button.winfo_rootx() - self.root.winfo_rootx()
        anchor_y = self.finance_button.winfo_rooty() - self.root.winfo_rooty()
        below_y = anchor_y + self.finance_button.winfo_height() + 6
        space_below = max(0, window_height - below_y - 8)
        space_above = max(0, anchor_y - 8)
        if space_below >= space_above:
            height = min(desired_height, max(96, space_below))
            y = below_y
        else:
            height = min(desired_height, max(96, space_above))
            y = anchor_y - height - 6
        x = max(8, min(anchor_x + self.finance_button.winfo_width() - width, window_width - width - 8))
        y = max(8, min(y, window_height - height - 8))
        popup.place(x=x, y=y, width=width, height=height)
        popup.lift()

    def _dismiss_finance_dropdown_on_click(self, event: Any) -> None:
        popup = self._finance_dropdown
        if popup is None or getattr(event, "widget", None) is self.finance_button:
            return
        widget = getattr(event, "widget", None)
        while widget is not None:
            if widget is popup:
                return
            widget = getattr(widget, "master", None)
        self._close_finance_dropdown()

    def _dismiss_finance_dropdown_on_escape(self, _event: Any) -> str | None:
        if self._finance_dropdown is None:
            return None
        self._close_finance_dropdown()
        return "break"

    def _toggle_finance_dropdown(self) -> None:
        if self._finance_dropdown is not None:
            self._close_finance_dropdown()
            return

        popup = tk.Frame(
            self.root,
            bg=color("#ffffff"),
            highlightbackground=color("#d0d5dd"),
            highlightthickness=1,
        )
        self._finance_dropdown = popup
        popup.grid_rowconfigure(0, weight=1)
        popup.grid_columnconfigure(0, weight=1)
        menu_canvas = tk.Canvas(popup, bg=color("#ffffff"), highlightthickness=0, borderwidth=0)
        self._finance_dropdown_canvas = menu_canvas
        menu_scrollbar = ttk.Scrollbar(popup, orient="vertical", command=menu_canvas.yview)
        menu_canvas.configure(yscrollcommand=menu_scrollbar.set)
        menu_canvas.grid(row=0, column=0, sticky="nsew")
        menu_scrollbar.grid(row=0, column=1, sticky="ns")
        menu_scrollbar.grid_remove()
        menu_content = tk.Frame(menu_canvas, bg=color("#ffffff"))
        menu_window = menu_canvas.create_window((0, 0), window=menu_content, anchor="nw")

        def update_menu_scrollregion(_event: Any = None) -> None:
            if self._finance_dropdown is not popup:
                return
            if defer_during_interactive_resize(
                    menu_canvas, (menu_canvas, "finance-menu-layout"), update_menu_scrollregion):
                return
            menu_canvas.itemconfigure(menu_window, width=menu_canvas.winfo_width())
            menu_canvas.configure(scrollregion=menu_canvas.bbox("all"))
            needs_scroll = menu_content.winfo_reqheight() > menu_canvas.winfo_height() + 2
            if needs_scroll:
                menu_scrollbar.grid()
            else:
                menu_scrollbar.grid_remove()

        menu_content.bind("<Configure>", update_menu_scrollregion)
        menu_canvas.bind("<Configure>", update_menu_scrollregion)
        entries = (
            ("食材与饮食记录", "查看采购商品和自动分类结果", self.open_food_tracking),
            ("账单记录", "按日期查看近期收入、支出和转账", self.open_transaction_history),
            ("付款方式和定期付款", "管理支付规则与周期性收支", self.open_payment_recurring_workspace),
            ("银行账户和信用卡", "查看账户余额、信用额度和还款", self.open_accounts_workspace),
            ("资产管理", "管理投资资产与固定资产，查看资产价格、月度折旧和账面价值", self.open_fixed_assets),
            ("财务报表和预算", "查看家庭财务并管理分类预算", self.open_reports_savings_workspace),
        )
        for title, subtitle, callback in entries:
            row = tk.Frame(menu_content, bg=color("#ffffff"), cursor="hand2")
            row.pack(fill="x", padx=8, pady=2)
            tk.Label(
                row,
                text=translate(title, self.language),
                bg=color("#ffffff"),
                fg=color("#344054"),
                font=(self.ui_font_family, 11, "bold"),
                anchor="w",
            ).pack(fill="x", padx=9, pady=(7, 0))
            tk.Label(
                row,
                text=translate(subtitle, self.language),
                bg=color("#ffffff"),
                fg=color("#667085"),
                font=(self.ui_font_family, 9),
                anchor="w",
            ).pack(fill="x", padx=9, pady=(1, 7))

            def enter(_event: Any, target: tk.Frame = row) -> None:
                target.configure(bg=color("#f2f4f7"))
                for child in target.winfo_children():
                    child.configure(bg=color("#f2f4f7"))

            def leave(_event: Any, target: tk.Frame = row) -> None:
                target.configure(bg=color("#ffffff"))
                for child in target.winfo_children():
                    child.configure(bg=color("#ffffff"))

            def invoke(action: Any = callback) -> None:
                self._close_finance_dropdown()
                action()

            for widget in (row, *row.winfo_children()):
                widget.bind("<Enter>", enter)
                widget.bind("<Leave>", leave)
                widget.bind("<Button-1>", lambda _event, action=invoke: action())

        self._place_finance_dropdown()
        popup.after_idle(update_menu_scrollregion)

    def _open_finance_tabbed_workspace(
        self,
        title: str,
        pages: tuple[tuple[str, Any, bool], ...],
        max_width: int = 1080,
        min_width: int = 900,
    ) -> None:
        if self.busy:
            messagebox.showinfo(
                translate("正在记账", self.language),
                translate("当前记账请求完成后再打开财务管理。", self.language),
                parent=self.root,
            )
            return

        dialog = tk.Toplevel(self.root)
        dialog.title(translate(title, self.language))
        window_width = min(max_width, max(min_width, dialog.winfo_screenwidth() - 80))
        window_height = min(660, max(560, dialog.winfo_screenheight() - 100))
        dialog.geometry(f"{window_width}x{window_height}")
        dialog.minsize(min(min_width, window_width), min(540, window_height))
        dialog.transient(self.root)
        dialog.configure(bg=color("#f3f5f8"))
        shell = ttk.Frame(dialog, style="App.TFrame", padding=12)
        shell.pack(fill="both", expand=True)
        shell.columnconfigure(0, weight=1)
        shell.rowconfigure(0, weight=1)
        notebook = ttk.Notebook(shell)
        notebook.grid(row=0, column=0, sticky="nsew")
        for page_title, render_page, use_outer_scroll in pages:
            page = ttk.Frame(notebook, style="App.TFrame")
            if use_outer_scroll:
                page.columnconfigure(0, weight=1)
                page.rowconfigure(0, weight=1)
                page_canvas = tk.Canvas(
                    page,
                    background=color("#f3f5f8"),
                    highlightthickness=0,
                    borderwidth=0,
                )
                page_scrollbar = ttk.Scrollbar(page, orient="vertical", command=page_canvas.yview)
                page_canvas.configure(yscrollcommand=page_scrollbar.set)
                page_canvas.grid(row=0, column=0, sticky="nsew")
                page_scrollbar.grid(row=0, column=1, sticky="ns")
                page_content = ttk.Frame(page_canvas, style="App.TFrame")
                page_window = page_canvas.create_window((0, 0), window=page_content, anchor="nw")

                def update_page_scrollregion(_event=None, canvas=page_canvas):
                    def callback():
                        if canvas.winfo_exists():
                            canvas.configure(scrollregion=canvas.bbox("all"))
                    if defer_during_interactive_resize(
                            canvas, (canvas, "scrollregion"), callback):
                        return
                    callback()

                def resize_page_content(event, canvas=page_canvas, window=page_window):
                    def callback(width=event.width):
                        if canvas.winfo_exists():
                            canvas.itemconfigure(window, width=width)
                    if defer_during_interactive_resize(canvas, (canvas, "content-width"), callback):
                        return
                    callback()

                page_content.bind("<Configure>", update_page_scrollregion)
                page_canvas.bind("<Configure>", resize_page_content)
            else:
                page_content = page
            notebook.add(page, text=translate(page_title, self.language))
            render_page(page_content)
        dialog.bind("<Escape>", lambda _event: dialog.destroy())
        center_window(dialog, self.root)

    def open_payment_recurring_workspace(self) -> None:
        self._open_finance_tabbed_workspace(
            "付款方式和定期付款",
            (
                ("支付方式与用途", lambda page: self.open_payment_settings(page), True),
                ("定期收支", lambda page: self.open_recurring_transactions(page), False),
            ),
            max_width=1080,
        )

    def open_accounts_workspace(self) -> None:
        self._open_finance_tabbed_workspace(
            "银行账户和信用卡",
            (
                ("现金管理", lambda page: self.open_cash_management(page), False),
                ("信用卡管理", lambda page: self.open_credit_management(page), False),
            ),
            max_width=900,
            min_width=900,
        )

    def open_reports_savings_workspace(self) -> None:
        self.open_financial_statements()

    def create_database_backup(self, parent: tk.Misc | None = None) -> None:
        dialog_parent = parent or self.root
        backup_directory = self.database_path.parent.parent / "backups"
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        destination = backup_directory / f"household-bookkeeping-{stamp}.sqlite3"
        suffix = 1
        while destination.exists():
            destination = backup_directory / f"household-bookkeeping-{stamp}-{suffix}.sqlite3"
            suffix += 1
        database = Database(self.database_path)
        try:
            target = database.backup(destination)
        except (LedgerError, OSError, sqlite3.Error) as exc:
            messagebox.showerror("备份失败", str(exc), parent=dialog_parent)
            return
        finally:
            database.close()
        messagebox.showinfo("备份完成", f"账本备份已保存到：\n{target}", parent=dialog_parent)

    def open_food_tracking(self) -> None:
        if self.busy:
            messagebox.showinfo("正在记账", "当前记账请求完成后再查看食材与饮食记录。", parent=self.root)
            return
        show_food_tracking(self.root, self.database_path)

    def open_transaction_history(self) -> None:
        if self.busy:
            messagebox.showinfo("正在记账", "当前记账请求完成后再查看账单记录。", parent=self.root)
            return

        dialog = tk.Toplevel(self.root)
        dialog.title("账单记录")
        dialog.geometry("1040x640")
        dialog.minsize(820, 520)
        dialog.transient(self.root)
        dialog.configure(bg=color("#f3f5f8"))
        history_style = ttk.Style(dialog)
        history_style.configure("SearchHelp.TButton", padding=(1, 0))

        panel = ttk.Frame(dialog, style="App.TFrame", padding=12)
        panel.pack(fill="both", expand=True)
        fit_management_text(panel)
        panel.columnconfigure(0, weight=1)
        panel.rowconfigure(4, weight=1)
        ttk.Label(panel, text="账单记录", style="ManagementTitle.TLabel").grid(
            row=0, column=0, sticky="w"
        )
        ttk.Label(
            panel,
            text="查看本地账本中的收入、支出和转账。按账本日期筛选；各币种金额分别显示。",
            style="Hint.TLabel",
            wraplength=900,
        ).grid(row=1, column=0, sticky="ew", pady=(4, 8))

        filters = ttk.Frame(panel, style="App.TFrame")
        filters.grid(row=2, column=0, sticky="ew", pady=(0, 10))
        mode_var = tk.StringVar(value="recent")
        ttk.Radiobutton(
            filters, text="指定日期", variable=mode_var, value="day"
        ).pack(side="left", padx=(0, 10))
        ttk.Radiobutton(
            filters, text="最近几天", variable=mode_var, value="recent"
        ).pack(side="left", padx=(0, 16))
        ttk.Label(filters, text="日期 / 截止日期（支持202608、8月）", style="Hint.TLabel").pack(side="left")
        selected_date_var = tk.StringVar(value=_today_japan())

        def date_spinner_values(selected_date: date) -> tuple[str, ...]:
            values: list[str] = []
            for offset in (-1, 0, 1):
                try:
                    values.append((selected_date + timedelta(days=offset)).isoformat())
                except OverflowError:
                    continue
            return tuple(values)

        date_spinbox = ttk.Spinbox(
            filters,
            values=date_spinner_values(parse_date(selected_date_var.get())),
            textvariable=selected_date_var,
            width=12,
            wrap=False,
            command=lambda: step_date_and_refresh(),
        )
        date_spinbox.pack(side="left", padx=(6, 0))
        ttk.Button(
            filters,
            text="…",
            width=2,
            style="SearchHelp.TButton",
            command=lambda: open_date_picker(),
        ).pack(side="left", padx=(2, 12))
        ttk.Label(filters, text="天数", style="Hint.TLabel").pack(side="left")
        days_var = tk.StringVar(value="7")
        days_spinbox = ttk.Spinbox(
            filters, from_=1, to=3650, textvariable=days_var, width=6
        )
        days_spinbox.pack(side="left", padx=(6, 12))

        ttk.Button(
            filters, text="查看", style="Settings.TButton", command=lambda: refresh()
        ).pack(side="left", padx=(0, 6))
        ttk.Button(
            filters,
            text="今天",
            style="Settings.TButton",
            command=lambda: set_today_and_refresh(),
        ).pack(side="left")

        result_summary = ttk.Label(panel, text="", style="Hint.TLabel")
        result_summary.grid(row=3, column=0, sticky="ew", pady=(0, 6))

        table_frame = ttk.Frame(panel, style="App.TFrame")
        table_frame.grid(row=4, column=0, sticky="nsew")
        table_frame.columnconfigure(0, weight=1)
        table_frame.rowconfigure(0, weight=1)
        columns = ("id", "date", "kind", "description", "category", "amount", "account", "status")
        tree = ttk.Treeview(table_frame, columns=columns, show="headings")
        headers = (
            ("id", "编号", 68, "center"),
            ("date", "日期", 98, "center"),
            ("kind", "类型", 72, "center"),
            ("description", "说明", 230, "w"),
            ("category", "类别", 105, "w"),
            ("amount", "金额", 190, "e"),
            ("account", "账户 / 转账方向", 220, "w"),
            ("status", "状态", 105, "center"),
        )
        for column, title, width, anchor in headers:
            tree.heading(column, text=title)
            tree.column(column, width=width, minwidth=60, stretch=column in {"description", "account"}, anchor=anchor)
        tree.tag_configure("stripe_even", background=color("#ffffff"))
        tree.tag_configure("stripe_odd", background=color("#edf5ff"))
        tree.tag_configure("review", foreground=color("#b54708"))
        tree.grid(row=0, column=0, sticky="nsew")
        vertical = ttk.Scrollbar(table_frame, orient="vertical", command=tree.yview)
        vertical.grid(row=0, column=1, sticky="ns")
        horizontal = ttk.Scrollbar(table_frame, orient="horizontal", command=tree.xview)
        horizontal.grid(row=1, column=0, sticky="ew")
        tree.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)

        def update_mode(*_args: Any) -> None:
            days_spinbox.configure(state="disabled" if mode_var.get() == "day" else "normal")

        mode_var.trace_add("write", update_mode)
        update_mode()

        def set_today_and_refresh() -> None:
            selected_date_var.set(_today_japan())
            date_spinbox.configure(values=date_spinner_values(parse_date(selected_date_var.get())))
            mode_var.set("day")
            refresh()

        def step_date_and_refresh() -> None:
            try:
                selected_date = parse_date(selected_date_var.get().strip())
            except (LedgerError, ValueError):
                messagebox.showerror(
                    translate("筛选条件有误", self.language),
                    translate(
                        "日期无效或格式不支持。支持 YYYY-MM-DD、YYYY/M/D、YYYYMMDD、YYYYMM 和 M月；仅写月份时按当前日本年份的1日处理。",
                        self.language,
                    ),
                    parent=dialog,
                )
                return
            selected_date_var.set(selected_date.isoformat())
            date_spinbox.configure(values=date_spinner_values(selected_date))
            refresh()

        def refresh_date_spinner_values(*_args: Any) -> None:
            try:
                selected_date = parse_date(selected_date_var.get().strip())
            except (LedgerError, ValueError):
                return
            date_spinbox.configure(values=date_spinner_values(selected_date))

        def normalize_date_spinner(*_args: Any) -> None:
            try:
                selected_date = parse_date(selected_date_var.get().strip())
            except (LedgerError, ValueError):
                return
            selected_date_var.set(selected_date.isoformat())
            date_spinbox.configure(values=date_spinner_values(selected_date))

        def open_date_picker() -> None:
            try:
                selected_date = parse_date(selected_date_var.get().strip())
            except (LedgerError, ValueError):
                selected_date = parse_date(_today_japan())

            picker = tk.Toplevel(dialog)
            picker.title(translate("选择日期", self.language))
            picker.resizable(False, False)
            picker.transient(dialog)
            picker.configure(bg=color("#f3f5f8"))

            picker_panel = ttk.Frame(picker, style="App.TFrame", padding=12)
            picker_panel.pack(fill="both", expand=True)
            picker_panel.columnconfigure(1, weight=1)
            view = {"year": selected_date.year, "month": selected_date.month}
            month_title = ttk.Label(picker_panel, style="Hint.TLabel", anchor="center")
            month_title.grid(row=0, column=1, sticky="ew", padx=6, pady=(0, 8))
            calendar_grid = ttk.Frame(picker_panel, style="App.TFrame")
            calendar_grid.grid(row=1, column=0, columnspan=3, sticky="ew")
            for column in range(7):
                calendar_grid.columnconfigure(column, weight=1, uniform="weekday")

            def choose_month(offset: int) -> None:
                month_index = view["year"] * 12 + view["month"] - 1 + offset
                year, month_index = divmod(month_index, 12)
                if not 1 <= year <= 9999:
                    return
                view["year"] = year
                view["month"] = month_index + 1
                render_month()

            ttk.Button(
                picker_panel,
                text="‹",
                width=3,
                style="Settings.TButton",
                command=lambda: choose_month(-1),
            ).grid(row=0, column=0, sticky="w", pady=(0, 8))
            ttk.Button(
                picker_panel,
                text="›",
                width=3,
                style="Settings.TButton",
                command=lambda: choose_month(1),
            ).grid(row=0, column=2, sticky="e", pady=(0, 8))

            def choose_day(day_number: int) -> None:
                chosen = date(view["year"], view["month"], day_number)
                selected_date_var.set(chosen.isoformat())
                date_spinbox.configure(values=date_spinner_values(chosen))
                refresh()
                picker.destroy()

            def render_month() -> None:
                for child in calendar_grid.winfo_children():
                    child.destroy()
                month_title.configure(text=f"{view['year']:04d}-{view['month']:02d}")
                weekday_names = ("周一", "周二", "周三", "周四", "周五", "周六", "周日")
                for column, name in enumerate(weekday_names):
                    ttk.Label(
                        calendar_grid,
                        text=translate(name, self.language),
                        style="Hint.TLabel",
                        anchor="center",
                    ).grid(row=0, column=column, sticky="ew", padx=1, pady=(0, 4))
                weeks = calendar_module.Calendar(firstweekday=0).monthdayscalendar(
                    view["year"], view["month"]
                )
                for row_index, week in enumerate(weeks, start=1):
                    for column, day_number in enumerate(week):
                        if day_number == 0:
                            ttk.Label(calendar_grid, text="").grid(
                                row=row_index, column=column, padx=1, pady=1
                            )
                            continue
                        ttk.Button(
                            calendar_grid,
                            text=str(day_number),
                            width=3,
                            style="Send.TButton"
                            if (view["year"], view["month"], day_number)
                            == (selected_date.year, selected_date.month, selected_date.day)
                            else "Settings.TButton",
                            command=lambda day=day_number: choose_day(day),
                        ).grid(row=row_index, column=column, sticky="nsew", padx=1, pady=1)

            render_month()
            picker.bind("<Escape>", lambda _event: picker.destroy())
            picker.grab_set()

        date_spinbox.bind("<FocusOut>", normalize_date_spinner, add="+")
        date_spinbox.bind("<KeyRelease>", refresh_date_spinner_values, add="+")
        date_spinbox.bind(
            "<<Paste>>",
            lambda _event: dialog.after_idle(refresh_date_spinner_values),
            add="+",
        )

        def format_transaction_amount(row: Any) -> str:
            code = str(row["currency"])
            def for_account(value: int, currency: str, digits: int, account_type: str | None) -> str:
                return f"{value:,}点" if account_type == "points" else minor_to_text(value, digits, currency)

            amount = for_account(
                int(row["amount_minor"]),
                code,
                int(row["currency_minor_digits"]),
                row["account_type"],
            )
            if row["kind"] == "transfer":
                destination_currency = str(row["to_currency"])
                destination_amount = for_account(
                    int(row["to_amount_minor"]),
                    destination_currency,
                    int(row["to_minor_digits"]),
                    row["to_account_type"],
                )
                return f"{amount} → {destination_amount}"
            if row["account_amount_minor"] is not None and row["account_minor_digits"] is not None:
                account_currency = str(row["account_currency"])
                if account_currency != code:
                    account_amount = for_account(
                        int(row["account_amount_minor"]),
                        account_currency,
                        int(row["account_minor_digits"]),
                        row["account_type"],
                    )
                    return f"{amount}（账户扣款 {account_amount}）"
            return amount

        displayed_rows: dict[int, Any] = {}
        kind_labels = {"income": "收入", "expense": "支出", "transfer": "转账"}

        def refresh() -> None:
            raw_date = selected_date_var.get().strip()
            try:
                selected_date = parse_date(raw_date)
                selected_date_var.set(selected_date.isoformat())
                if mode_var.get() == "day":
                    start, end = selected_date, selected_date
                else:
                    days = int(days_var.get())
                    if not 1 <= days <= 3650:
                        raise LedgerError("天数请输入 1 到 3650 之间的整数")
                    end = selected_date
                    start = end - timedelta(days=days - 1)
            except (LedgerError, ValueError) as exc:
                messagebox.showerror(
                    translate("筛选条件有误", self.language),
                    translate(str(exc), self.language),
                    parent=dialog,
                )
                return

            database = Database(self.database_path)
            try:
                database.initialize()
                rows = database.transactions_between(start.isoformat(), end.isoformat())
            except (LedgerError, OSError, sqlite3.Error) as exc:
                messagebox.showerror("无法读取账单", str(exc), parent=dialog)
                return
            finally:
                database.close()

            tree.delete(*tree.get_children())
            displayed_rows.clear()
            tree._bk_i18n_item_values = {}
            tree._bk_i18n_row_translatable = {}
            for index, row in enumerate(rows):
                if row["kind"] == "transfer":
                    account_label = f"{row['account_name'] or '—'} → {row['to_account_name'] or '—'}"
                    category_label = "转账"
                    translatable_columns = {2, 4, 5, 7}
                else:
                    account_label = row["account_name"] or "备查"
                    category_label = row["category_name"] or "—"
                    translatable_columns = {2, 5, 7}
                    if not row["account_name"]:
                        translatable_columns.add(6)
                status_parts = ["备查" if row["balance_effect"] == "memo" else "已入账"]
                if row["needs_review"]:
                    status_parts.append("待核对")
                tags = ["stripe_even" if index % 2 == 0 else "stripe_odd"]
                if row["needs_review"]:
                    tags.append("review")
                source_values = (
                    f"#{row['id']}",
                    row["occurred_on"],
                    kind_labels.get(str(row["kind"]), str(row["kind"])),
                    row["description"],
                    category_label,
                    format_transaction_amount(row),
                    account_label,
                    " / ".join(status_parts),
                )
                display_values = tuple(
                    translate_tree_item(value) if column_index in translatable_columns else value
                    for column_index, value in enumerate(source_values)
                )
                item_id = tree.insert(
                    "",
                    "end",
                    iid=str(row["id"]),
                    values=display_values,
                    tags=tuple(tags),
                )
                displayed_rows[int(row["id"])] = row
                tree._bk_i18n_item_values[item_id] = source_values
                tree._bk_i18n_row_translatable[item_id] = translatable_columns
            result_summary.configure(
                text=f"找到 {len(rows)} 条记录：{start.isoformat()} 至 {end.isoformat()}"
            )
            update_delete_button()
            update_review_button()

        def delete_selected_transaction() -> None:
            selected = tree.selection()
            if not selected:
                messagebox.showinfo(
                    translate("未选择流水", self.language),
                    translate("请先选择一条账务记录。", self.language),
                    parent=dialog,
                )
                return
            try:
                transaction_id = int(selected[0])
            except (TypeError, ValueError):
                messagebox.showerror(
                    translate("无法删除", self.language),
                    translate("所选流水编号无效，请刷新账单记录后重试。", self.language),
                    parent=dialog,
                )
                return
            row = displayed_rows.get(transaction_id)
            if row is None:
                messagebox.showerror(
                    translate("无法删除", self.language),
                    translate("所选流水已不在当前列表中，请刷新后重试。", self.language),
                    parent=dialog,
                )
                return

            kind_label = translate(kind_labels.get(str(row["kind"]), str(row["kind"])), self.language)
            if row["kind"] == "transfer":
                account_label = f"{row['account_name'] or '—'} → {row['to_account_name'] or '—'}"
            else:
                account_label = row["account_name"] or translate("备查", self.language)
            target = (
                f"#{transaction_id} | {row['occurred_on']} | {kind_label} | "
                f"{row['description']} | {format_transaction_amount(row)} | {account_label}"
            )
            if not confirm_delete_once(
                dialog,
                title="删除账务分录",
                target=target,
                impact=(
                    "该流水将从本地账本永久删除，相关账户余额和收支报表会按剩余流水重新计算。"
                    "关联的采购商品会一并删除；若它是自动还款流水，关联的本期自动还款会取消，避免重复记账。"
                    "已有余额快照和独立食用记录不变。删除前会自动备份账本。"
                ),
            ):
                return

            database = Database(self.database_path)
            try:
                database.initialize()
                backup_path = database.delete_transaction_with_backup(transaction_id)
            except (LedgerError, OSError, sqlite3.Error) as exc:
                messagebox.showerror(
                    translate("删除失败", self.language),
                    str(exc),
                    parent=dialog,
                )
                return
            finally:
                database.close()

            refresh()
            self._queue_github_auto_sync()
            messagebox.showinfo(
                translate("分录已删除", self.language),
                translate("已删除流水 #{id}。删除前备份：{backup}", self.language).format(
                    id=transaction_id,
                    backup=str(backup_path),
                ),
                parent=dialog,
            )
            update_delete_button()

        def update_delete_button(_event: Any = None) -> None:
            delete_button.configure(state="normal" if tree.selection() else "disabled")

        def choose_review_account(row: Any) -> str | None:
            database = Database(self.database_path)
            try:
                database.initialize()
                accounts = database.selectable_account_rows()
            except (LedgerError, OSError, sqlite3.Error) as exc:
                messagebox.showerror(
                    translate("无法读取账户", self.language),
                    translate(str(exc), self.language),
                    parent=dialog,
                )
                return None
            finally:
                database.close()

            if not accounts:
                messagebox.showerror(
                    translate("无法核对", self.language),
                    translate("账本中没有可用于入账的账户。", self.language),
                    parent=dialog,
                )
                return None

            choices = [f"{account['name']} ({account['currency']})" for account in accounts]
            account_by_choice = dict(zip(choices, (str(account["name"]) for account in accounts)))
            transaction_currency = str(row["currency"])
            same_currency_choice = next(
                (choice for choice, account in zip(choices, accounts)
                 if str(account["currency"]) == transaction_currency),
                choices[0],
            )
            selected_choice = tk.StringVar(value=same_currency_choice)
            result: dict[str, str | None] = {"account": None}

            account_dialog = tk.Toplevel(dialog)
            account_dialog.title(translate("选择入账账户", self.language))
            account_dialog.geometry("540x240")
            account_dialog.minsize(480, 220)
            account_dialog.transient(dialog)
            account_dialog.configure(bg=color("#f3f5f8"))
            account_panel = ttk.Frame(account_dialog, style="App.TFrame", padding=12)
            account_panel.pack(fill="both", expand=True)
            account_panel.columnconfigure(0, weight=1)
            ttk.Label(
                account_panel,
                text=translate("这条备查记录尚未绑定账户。请选择实际付款账户；确认后会转为已入账并影响账户余额。", self.language),
                wraplength=490,
                justify="left",
            ).grid(row=0, column=0, sticky="w", pady=(0, 14))
            ttk.Label(account_panel, text=translate("入账账户", self.language)).grid(
                row=1, column=0, sticky="w", pady=(0, 5)
            )
            account_combo = ttk.Combobox(
                account_panel,
                textvariable=selected_choice,
                values=choices,
                state="readonly",
            )
            account_combo.grid(row=2, column=0, sticky="ew")
            ttk.Label(
                account_panel,
                text=translate("交易币种：{currency}；若账户币种不同，将按交易日参考汇率计算扣款金额。", self.language).format(
                    currency=transaction_currency,
                ),
                wraplength=490,
                justify="left",
            ).grid(row=3, column=0, sticky="w", pady=(10, 0))

            def accept_account() -> None:
                result["account"] = account_by_choice.get(selected_choice.get())
                if result["account"] is None:
                    messagebox.showerror(
                        translate("无法核对", self.language),
                        translate("请选择一个有效的入账账户。", self.language),
                        parent=account_dialog,
                    )
                    return
                account_dialog.destroy()

            buttons = ttk.Frame(account_panel, style="App.TFrame")
            buttons.grid(row=4, column=0, sticky="ew", pady=(16, 0))
            ttk.Button(
                buttons,
                text=translate("取消", self.language),
                command=account_dialog.destroy,
            ).pack(side="right")
            ttk.Button(
                buttons,
                text=translate("继续核对", self.language),
                style="Send.TButton",
                command=accept_account,
            ).pack(side="right", padx=(0, 8))
            account_dialog.bind("<Escape>", lambda _event: account_dialog.destroy())
            account_dialog.grab_set()
            account_combo.focus_set()
            dialog.wait_window(account_dialog)
            return result["account"]

        def mark_selected_reviewed() -> None:
            selected = tree.selection()
            if not selected:
                return
            try:
                transaction_id = int(selected[0])
            except (TypeError, ValueError):
                return
            row = displayed_rows.get(transaction_id)
            if row is None or not row["needs_review"]:
                return

            account_name: str | None = None
            if row["balance_effect"] == "memo":
                account_name = choose_review_account(row)
                if account_name is None:
                    return
                account_label = account_name
                impact = translate(
                    "备查流水会转为已入账，并从所选账户扣款或增加余额。", self.language
                )
            else:
                account_label = str(row["account_name"] or "—")
                impact = translate(
                    "流水会保留现有账户，只清除待核对状态。", self.language
                )

            prompt = translate(
                "确认将流水 #{id} 标记为已核对？\n{description}\n账户：{account}\n{impact}",
                self.language,
            ).format(
                id=transaction_id,
                description=row["description"],
                account=account_label,
                impact=impact,
            )
            if not messagebox.askyesno(
                translate("确认核对", self.language), prompt, parent=dialog
            ):
                return

            database = Database(self.database_path)
            try:
                database.initialize()
                converted_from_memo = database.confirm_transaction_review(
                    transaction_id,
                    account_name=account_name,
                )
            except (LedgerError, OSError, sqlite3.Error) as exc:
                messagebox.showerror(
                    translate("核对失败", self.language),
                    translate(str(exc), self.language),
                    parent=dialog,
                )
                return
            finally:
                database.close()

            refresh()
            self._queue_github_auto_sync()
            detail = (
                translate("备查流水已转为已入账。", self.language)
                if converted_from_memo
                else translate("原已入账流水的待核对标记已清除。", self.language)
            )
            messagebox.showinfo(
                translate("核对完成", self.language),
                translate("流水 #{id} 已核对。{detail}", self.language).format(
                    id=transaction_id,
                    detail=detail,
                ),
                parent=dialog,
            )

        def edit_selected_transaction() -> None:
            selected = tree.selection()
            if not selected:
                messagebox.showinfo(
                    translate("未选择流水", self.language),
                    translate("请先选择一条账务记录。", self.language),
                    parent=dialog,
                )
                return
            try:
                transaction_id = int(selected[0])
            except (TypeError, ValueError):
                messagebox.showerror(
                    translate("无法编辑", self.language),
                    translate("所选流水编号无效，请刷新账单记录后重试。", self.language),
                    parent=dialog,
                )
                return
            row = displayed_rows.get(transaction_id)
            if row is None:
                messagebox.showerror(
                    translate("无法编辑", self.language),
                    translate("所选流水已不在当前列表中，请刷新后重试。", self.language),
                    parent=dialog,
                )
                return

            database = Database(self.database_path)
            try:
                database.initialize()
                accounts = database.connection.execute(
                    "SELECT name,currency,account_type FROM accounts ORDER BY name"
                ).fetchall()
                currencies = database.connection.execute(
                    "SELECT code,minor_digits FROM currencies WHERE is_monetary=1 ORDER BY code"
                ).fetchall()
                categories = database.connection.execute(
                    "SELECT id,name,kind,is_active FROM categories ORDER BY name"
                ).fetchall()
                category_translations = database.category_translations()
            except (LedgerError, OSError, sqlite3.Error) as exc:
                messagebox.showerror(
                    translate("无法编辑", self.language),
                    translate(str(exc), self.language),
                    parent=dialog,
                )
                return
            finally:
                database.close()

            editor = tk.Toplevel(dialog)
            editor.title(translate("编辑账务分录", self.language))
            editor.geometry("650x500")
            editor.minsize(570, 460)
            editor.transient(dialog)
            editor.configure(bg=color("#f3f5f8"))
            editor.columnconfigure(0, weight=1)
            editor.rowconfigure(0, weight=1)
            edit_panel = ttk.Frame(editor, style="App.TFrame", padding=16)
            edit_panel.grid(row=0, column=0, sticky="nsew")
            edit_panel.columnconfigure(1, weight=1)
            edit_panel.columnconfigure(3, weight=1)
            ttk.Label(
                edit_panel,
                text=translate("编辑账务分录", self.language),
                style="ManagementTitle.TLabel",
            ).grid(row=0, column=0, columnspan=4, sticky="w", pady=(0, 12))

            def add_field_label(text: str, row_index: int, column: int = 0) -> None:
                ttk.Label(edit_panel, text=translate(text, self.language)).grid(
                    row=row_index, column=column, sticky="w", padx=(0, 8), pady=6
                )

            kind_values = {
                translate("收入", self.language): "income",
                translate("支出", self.language): "expense",
                translate("转账", self.language): "transfer",
            }
            kind_display = {value: label for label, value in kind_values.items()}
            kind_var = tk.StringVar(value=kind_display[str(row["kind"])])
            date_var = tk.StringVar(value=str(row["occurred_on"]))
            description_var = tk.StringVar(value=str(row["description"]))
            currency_var = tk.StringVar(value=str(row["currency"]))

            def amount_input(value: int, digits: int) -> str:
                return f"{Decimal(value).scaleb(-digits):,.{digits}f}"

            amount_var = tk.StringVar(
                value=amount_input(
                    int(row["amount_minor"]),
                    int(row["currency_minor_digits"]),
                )
            )
            transfer_amount_var = tk.StringVar(
                value=(
                    amount_input(
                        int(row["to_amount_minor"]),
                        int(row["to_minor_digits"]),
                    )
                    if row["kind"] == "transfer" and row["to_amount_minor"] is not None
                    else ""
                )
            )
            account_type_labels = {
                "bank": "银行", "wallet": "钱包", "prepaid": "券/预付",
                "transit": "交通卡", "credit": "信用卡", "points": "积分",
            }
            account_by_label: dict[str, str] = {}
            account_label_by_name: dict[str, str] = {}
            for account in accounts:
                name = str(account["name"])
                label = f"{name}（{account['currency']} · {translate(account_type_labels[str(account['account_type'])], self.language)}）"
                account_by_label[label] = name
                account_label_by_name[name] = label
            memo_label = translate("备查", self.language)
            account_choices_with_memo = (memo_label, *account_by_label.keys())
            account_choices = tuple(account_by_label)
            initial_account = (
                account_label_by_name.get(str(row["account_name"]))
                if row["account_name"] else memo_label
            )
            account_var = tk.StringVar(value=initial_account or memo_label)
            destination_var = tk.StringVar(
                value=account_label_by_name.get(str(row["to_account_name"]), "")
            )
            review_var = tk.BooleanVar(value=bool(row["needs_review"]))

            add_field_label("日期", 1)
            date_entry = ttk.Entry(edit_panel, textvariable=date_var, width=16)
            date_entry.grid(row=1, column=1, sticky="ew", pady=6)
            add_field_label("类型", 1, 2)
            kind_combo = ttk.Combobox(
                edit_panel,
                textvariable=kind_var,
                values=tuple(kind_values),
                state="readonly",
                width=14,
            )
            kind_combo.grid(row=1, column=3, sticky="ew", pady=6)

            add_field_label("说明", 2)
            description_entry = ttk.Entry(edit_panel, textvariable=description_var)
            description_entry.grid(row=2, column=1, columnspan=3, sticky="ew", pady=6)

            add_field_label("币种", 3)
            currency_combo = ttk.Combobox(
                edit_panel,
                textvariable=currency_var,
                values=tuple(str(item["code"]) for item in currencies),
                state="readonly",
                width=14,
            )
            currency_combo.grid(row=3, column=1, sticky="ew", pady=6)
            add_field_label("金额", 3, 2)
            amount_entry = ttk.Entry(edit_panel, textvariable=amount_var)
            amount_entry.grid(row=3, column=3, sticky="ew", pady=6)

            add_field_label("账户", 4)
            account_combo = ttk.Combobox(
                edit_panel,
                textvariable=account_var,
                values=account_choices_with_memo,
                state="readonly",
            )
            account_combo.grid(row=4, column=1, sticky="ew", pady=6)
            category_label = ttk.Label(edit_panel, text=translate("类别", self.language))
            category_label.grid(row=4, column=2, sticky="w", padx=(0, 8), pady=6)
            category_var = tk.StringVar()
            category_combo = ttk.Combobox(edit_panel, textvariable=category_var, state="readonly")
            category_combo.grid(row=4, column=3, sticky="ew", pady=6)

            destination_label = ttk.Label(edit_panel, text=translate("转入账户", self.language))
            destination_label.grid(row=5, column=0, sticky="w", padx=(0, 8), pady=6)
            destination_combo = ttk.Combobox(
                edit_panel,
                textvariable=destination_var,
                values=account_choices,
                state="readonly",
            )
            destination_combo.grid(row=5, column=1, sticky="ew", pady=6)
            transfer_amount_label = ttk.Label(
                edit_panel, text=translate("转入金额", self.language)
            )
            transfer_amount_label.grid(row=5, column=2, sticky="w", padx=(0, 8), pady=6)
            transfer_amount_entry = ttk.Entry(edit_panel, textvariable=transfer_amount_var)
            transfer_amount_entry.grid(row=5, column=3, sticky="ew", pady=6)

            review_check = ttk.Checkbutton(
                edit_panel,
                text=translate("待核对", self.language),
                variable=review_var,
            )
            review_check.grid(row=6, column=0, columnspan=2, sticky="w", pady=(6, 2))
            ttk.Label(
                edit_panel,
                text=translate(
                    "保存后会重新计算相关余额和报表；修改前会自动备份账本。",
                    self.language,
                ),
                style="Hint.TLabel",
                wraplength=580,
            ).grid(row=7, column=0, columnspan=4, sticky="w", pady=(4, 10))

            category_display_to_name: dict[str, str] = {}
            category_name_to_display: dict[str, str] = {}
            categories_by_kind: dict[str, list[Any]] = {"income": [], "expense": []}
            for category in categories:
                if category["kind"] in categories_by_kind:
                    categories_by_kind[str(category["kind"])].append(category)

            def update_category_choices(kind_value: str, preferred_name: str | None = None) -> None:
                category_display_to_name.clear()
                category_name_to_display.clear()
                options: list[str] = []
                for category in categories_by_kind.get(kind_value, []):
                    name = str(category["name"])
                    if not category["is_active"] and int(category["id"]) != int(row["category_id"] or 0):
                        continue
                    translated_name = category_translations.get(int(category["id"]), {}).get(
                        self.language, name
                    )
                    label = translated_name
                    if label in category_display_to_name:
                        label = f"{label} · {name}"
                    category_display_to_name[label] = name
                    category_name_to_display[name] = label
                    options.append(label)
                category_combo.configure(values=tuple(options))
                selected_name = preferred_name if preferred_name in category_name_to_display else None
                if selected_name is None and options:
                    selected_name = category_display_to_name[options[0]]
                category_var.set(category_name_to_display.get(selected_name or "", ""))

            def update_editor_fields(_event: Any = None) -> None:
                kind_value = kind_values.get(kind_var.get(), "expense")
                is_transfer = kind_value == "transfer"
                if is_transfer:
                    category_label.grid_remove()
                    category_combo.grid_remove()
                    destination_label.grid()
                    destination_combo.grid()
                    transfer_amount_label.grid()
                    transfer_amount_entry.grid()
                    currency_combo.configure(state="disabled")
                    account_combo.configure(values=account_choices, state="readonly")
                    if account_var.get() == memo_label or account_var.get() not in account_choices:
                        account_var.set(account_choices[0] if account_choices else "")
                    selected_source = account_by_label.get(account_var.get())
                    selected_row = next((item for item in accounts if item["name"] == selected_source), None)
                    if selected_row is not None:
                        currency_var.set(str(selected_row["currency"]))
                    if destination_var.get() not in account_choices:
                        destination_var.set(next(
                            (choice for choice in account_choices if choice != account_var.get()),
                            "",
                        ))
                else:
                    destination_label.grid_remove()
                    destination_combo.grid_remove()
                    transfer_amount_label.grid_remove()
                    transfer_amount_entry.grid_remove()
                    currency_combo.configure(state="readonly")
                    account_combo.configure(values=account_choices_with_memo, state="readonly")
                    old_category_name = str(row["category_name"]) if row["category_name"] else None
                    update_category_choices(kind_value, old_category_name)

            def update_transfer_currency(_event: Any = None) -> None:
                if kind_values.get(kind_var.get()) != "transfer":
                    return
                selected_source = account_by_label.get(account_var.get())
                selected_row = next((item for item in accounts if item["name"] == selected_source), None)
                if selected_row is not None:
                    currency_var.set(str(selected_row["currency"]))
                if destination_var.get() == account_var.get():
                    destination_var.set(next(
                        (choice for choice in account_choices if choice != account_var.get()),
                        "",
                    ))

            kind_combo.bind("<<ComboboxSelected>>", update_editor_fields, add="+")
            account_combo.bind("<<ComboboxSelected>>", update_transfer_currency, add="+")
            update_editor_fields()

            def save_transaction_edit() -> None:
                kind_value = kind_values.get(kind_var.get())
                if kind_value is None:
                    messagebox.showerror(
                        translate("无法保存修改", self.language),
                        translate("请选择有效的账务类型。", self.language),
                        parent=editor,
                    )
                    return
                selected_account = account_by_label.get(account_var.get())
                selected_destination = account_by_label.get(destination_var.get())
                selected_category = category_display_to_name.get(category_var.get())
                memo_only = kind_value in {"income", "expense"} and account_var.get() == memo_label
                if kind_value in {"income", "expense"} and not memo_only and selected_account is None:
                    messagebox.showerror(
                        translate("无法保存修改", self.language),
                        translate("请选择有效的账户，或选择备查。", self.language),
                        parent=editor,
                    )
                    return
                if kind_value in {"income", "expense"} and selected_category is None:
                    messagebox.showerror(
                        translate("无法保存修改", self.language),
                        translate("请选择有效类别。", self.language),
                        parent=editor,
                    )
                    return
                try:
                    database = Database(self.database_path)
                    try:
                        database.initialize()
                        backup_path = database.update_transaction_with_backup(
                            transaction_id,
                            occurred_on=date_var.get().strip(),
                            kind=kind_value,
                            amount=amount_var.get().strip(),
                            currency=currency_var.get().strip(),
                            description=description_var.get(),
                            category_name=selected_category,
                            account_name=None if memo_only else selected_account,
                            to_account_name=selected_destination if kind_value == "transfer" else None,
                            to_amount=transfer_amount_var.get().strip() or None,
                            memo_only=memo_only,
                            needs_review=review_var.get(),
                        )
                    finally:
                        database.close()
                except (LedgerError, OSError, sqlite3.Error) as exc:
                    messagebox.showerror(
                        translate("无法保存修改", self.language),
                        translate(str(exc), self.language),
                        parent=editor,
                    )
                    return

                editor.destroy()
                refresh()
                self._queue_github_auto_sync()
                messagebox.showinfo(
                    translate("分录已更新", self.language),
                    translate("流水 #{id} 已更新。修改前备份：{backup}", self.language).format(
                        id=transaction_id,
                        backup=str(backup_path),
                    ),
                    parent=dialog,
                )

            edit_buttons = ttk.Frame(editor, style="App.TFrame", padding=(16, 8, 16, 14))
            edit_buttons.grid(row=1, column=0, sticky="ew")
            ttk.Button(
                edit_buttons,
                text=translate("取消", self.language),
                command=editor.destroy,
            ).pack(side="right")
            ttk.Button(
                edit_buttons,
                text=translate("确认修改", self.language),
                style="Send.TButton",
                command=save_transaction_edit,
            ).pack(side="right", padx=(0, 8))
            editor.bind("<Escape>", lambda _event: editor.destroy())
            for entry in (date_entry, description_entry, amount_entry, transfer_amount_entry):
                entry.bind("<Return>", lambda _event: save_transaction_edit())
            editor.grab_set()
            date_entry.focus_set()
            editor.update_idletasks()
            center_window(editor, dialog)

        footer = ttk.Frame(panel, style="App.TFrame")
        footer.grid(row=5, column=0, sticky="ew", pady=(10, 0))
        review_button = ttk.Button(
            footer,
            text=translate("标记已核对", self.language),
            style="Send.TButton",
            command=mark_selected_reviewed,
            state="disabled",
        )
        review_button.pack(side="left", padx=(0, 8))
        edit_button = ttk.Button(
            footer,
            text=translate("编辑选中分录", self.language),
            style="Settings.TButton",
            command=edit_selected_transaction,
            state="disabled",
        )
        edit_button.pack(side="left", padx=(0, 8))
        delete_button = ttk.Button(
            footer,
            text="删除选中分录",
            style="Settings.TButton",
            command=delete_selected_transaction,
            state="disabled",
        )
        delete_button.pack(side="left")
        ttk.Button(footer, text="关闭", command=dialog.destroy).pack(side="right")
        tree.bind("<<TreeviewSelect>>", update_delete_button, add="+")

        def update_edit_button(_event: Any = None) -> None:
            edit_button.configure(state="normal" if tree.selection() else "disabled")

        tree.bind("<<TreeviewSelect>>", update_edit_button, add="+")

        def update_review_button(_event: Any = None) -> None:
            selected = tree.selection()
            row = displayed_rows.get(int(selected[0])) if selected else None
            review_button.configure(
                state="normal" if row is not None and row["needs_review"] else "disabled"
            )

        tree.bind("<<TreeviewSelect>>", update_review_button, add="+")

        date_spinbox.bind("<Return>", lambda _event: refresh())
        days_spinbox.bind("<Return>", lambda _event: refresh())
        refresh()

    def open_recurring_transactions(self, container: tk.Misc | None = None) -> None:
        if self.busy and container is None:
            messagebox.showinfo("正在记账", "当前记账请求完成后再管理定期收支。", parent=self.root)
            return

        if container is None:
            dialog = tk.Toplevel(self.root)
            dialog.title("定期收支")
            dialog.geometry("1040x640")
            dialog.minsize(880, 540)
            dialog.transient(self.root)
            dialog.configure(bg=color("#f3f5f8"))
            content_parent: tk.Misc = dialog
        else:
            dialog = container.winfo_toplevel()
            content_parent = container
        panel = ttk.Frame(content_parent, style="App.TFrame", padding=12)
        panel.pack(fill="both", expand=True)
        fit_management_text(panel)
        panel.columnconfigure(0, weight=1)
        panel.rowconfigure(3, weight=1)

        ttk.Label(panel, text="定期收支", style="ManagementTitle.TLabel").grid(
            row=0, column=0, sticky="w"
        )
        ttk.Label(
            panel,
            text="设置周期、首次日期、金额、账户和类别。到期时软件会自动在本地账本记入收入或支出；不会连接银行或实际发起付款、收款。软件关闭期间到期的项目会在下次启动时按原日期补记。",
            style="Hint.TLabel", wraplength=960,
        ).grid(row=1, column=0, sticky="ew", pady=(4, 8))

        toolbar = ttk.Frame(panel, style="App.TFrame")
        toolbar.grid(row=2, column=0, sticky="ew", pady=(0, 8))
        tree = ttk.Treeview(
            panel,
            columns=("name", "kind", "amount", "account", "category", "frequency", "next", "status"),
            show="headings", height=12,
        )
        headers = {
            "name": ("项目", 145), "kind": ("方向", 70), "amount": ("账单金额→扣款币种", 160),
            "account": ("账户（币种）", 175), "category": ("类别", 100),
            "frequency": ("周期", 85), "next": ("下次日期", 100), "status": ("状态", 170),
        }
        for column, (heading, width) in headers.items():
            tree.heading(column, text=heading)
            tree.column(column, width=width, minwidth=60, stretch=column in {"name", "account", "status"})
        tree.grid(row=3, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(panel, orient="vertical", command=tree.yview)
        scroll.grid(row=3, column=1, sticky="ns")
        tree.configure(yscrollcommand=scroll.set)
        status_var = tk.StringVar(value="新增定期收入或支出；暂停后不会自动记账。")
        ttk.Label(panel, textvariable=status_var, style="Hint.TLabel").grid(
            row=4, column=0, sticky="w", pady=(8, 0)
        )

        def refresh() -> None:
            for item in tree.get_children():
                tree.delete(item)
            database = Database(self.database_path)
            try:
                database.initialize()
                rows = list_recurring_schedules(database)
                for row in rows:
                    frequency_key = str(row["frequency"])
                    interval = int(row["interval_count"])
                    frequency = (
                        FREQUENCY_LABELS[frequency_key]
                        if interval == 1
                        else f"每{interval}{FREQUENCY_UNITS[frequency_key]}"
                    )
                    tree.insert(
                        "", "end", iid=str(row["id"]),
                        values=(
                            row["name"], "收入" if row["kind"] == "income" else "支出",
                            f"{minor_to_text(int(row['amount_minor']), int(row['minor_digits']), str(row['currency']))} → {row['account_currency']}",
                            f"{row['account_name']}（{row['account_currency']}）", row["category_name"], frequency,
                            row["next_due_date"], row["last_status"] if row["enabled"] else "已暂停",
                        ),
                    )
            finally:
                database.close()

        def open_schedule_form(schedule_id: int | None = None) -> None:
            target_schedule_id = schedule_id
            existing_schedule = None
            if target_schedule_id is not None:
                database = Database(self.database_path)
                try:
                    database.initialize()
                    existing_schedule = next(
                        (row for row in list_recurring_schedules(database) if int(row["id"]) == target_schedule_id),
                        None,
                    )
                finally:
                    database.close()
                if existing_schedule is None:
                    messagebox.showerror("无法编辑", "找不到所选定期收支规则。", parent=dialog)
                    refresh()
                    return

            form = tk.Toplevel(dialog)
            form.title("编辑定期收支" if existing_schedule is not None else "新增定期收支")
            form.geometry("710x640")
            form.minsize(620, 580)
            form.transient(dialog)
            form.configure(bg=color("#f3f5f8"))
            form_panel = ttk.Frame(form, style="App.TFrame", padding=12)
            form_panel.pack(fill="both", expand=True)
            form_panel.columnconfigure(1, weight=1)
            ttk.Label(
                form_panel,
                text="编辑定期收支" if existing_schedule is not None else "新增定期收支",
                style="ManagementTitle.TLabel",
            ).grid(
                row=0, column=0, columnspan=2, sticky="w", pady=(0, 12)
            )
            initial_amount = ""
            if existing_schedule is not None:
                initial_amount = format(
                    Decimal(int(existing_schedule["amount_minor"])).scaleb(
                        -int(existing_schedule["minor_digits"])
                    ),
                    "f",
                )
            values: dict[str, tk.StringVar] = {
                "name": tk.StringVar(value=str(existing_schedule["name"]) if existing_schedule is not None else ""),
                "kind": tk.StringVar(
                    value=("收入" if existing_schedule["kind"] == "income" else "支出")
                    if existing_schedule is not None else "支出"
                ),
                "currency": tk.StringVar(
                    value=str(existing_schedule["currency"]) if existing_schedule is not None else "JPY"
                ),
                "amount": tk.StringVar(value=initial_amount),
                "account": tk.StringVar(
                    value=str(existing_schedule["account_name"]) if existing_schedule is not None else ""
                ),
                "category": tk.StringVar(
                    value=str(existing_schedule["category_name"]) if existing_schedule is not None else ""
                ),
                "frequency": tk.StringVar(
                    value=FREQUENCY_LABELS[str(existing_schedule["frequency"])]
                    if existing_schedule is not None else "每月"
                ),
                "interval": tk.StringVar(
                    value=str(existing_schedule["interval_count"]) if existing_schedule is not None else "1"
                ),
                "date": tk.StringVar(
                    value=str(existing_schedule["next_due_date"])
                    if existing_schedule is not None else _today_japan()
                ),
            }
            labels = (
                ("name", "项目名称"), ("kind", "收支方向"), ("currency", "账单币种"),
                ("amount", "金额"),
                ("account", "账户"), ("category", "类别"), ("frequency", "周期"),
                ("interval", "间隔"),
                ("date", "下次日期（支持202608、8月）" if existing_schedule is not None else "首次日期（支持202608、8月）"),
            )
            widgets: dict[str, ttk.Widget] = {}
            amount_label: ttk.Label | None = None
            for row_index, (key, label) in enumerate(labels, start=1):
                label_widget = ttk.Label(form_panel, text=label)
                label_widget.grid(row=row_index, column=0, sticky="w", padx=(0, 14), pady=6)
                if key == "amount":
                    amount_label = label_widget
                if key == "kind":
                    widget = ttk.Combobox(form_panel, textvariable=values[key], values=("支出", "收入"), state="readonly")
                elif key == "currency":
                    widget = ttk.Combobox(form_panel, textvariable=values[key], values=("JPY", "CNY"), state="readonly")
                elif key == "account":
                    widget = ttk.Combobox(form_panel, textvariable=values[key], state="readonly")
                elif key == "category":
                    widget = ttk.Combobox(form_panel, textvariable=values[key], state="readonly")
                elif key == "frequency":
                    widget = ttk.Combobox(form_panel, textvariable=values[key], values=tuple(FREQUENCY_LABELS.values()), state="readonly")
                elif key == "interval":
                    widget = ttk.Spinbox(form_panel, from_=1, to=365, textvariable=values[key], width=10)
                else:
                    widget = ttk.Entry(form_panel, textvariable=values[key])
                widget.grid(row=row_index, column=1, sticky="ew", pady=6)
                widgets[key] = widget

            hint_var = tk.StringVar()
            ttk.Label(form_panel, textvariable=hint_var, style="Hint.TLabel").grid(
                row=10, column=0, columnspan=2, sticky="w", pady=(4, 10)
            )

            database = Database(self.database_path)
            try:
                database.initialize()
                account_rows = database.selectable_account_rows()
                category_rows = {
                    kind: [row["name"] for row in database.connection.execute(
                        "SELECT name FROM categories WHERE kind=? AND is_active=1 ORDER BY name", (kind,)
                    )]
                    for kind in ("income", "expense")
                }
            finally:
                database.close()
            account_details = {
                str(row["name"]): {
                    "currency": str(row["currency"]),
                    "type": str(row["account_type"]),
                }
                for row in account_rows
            }

            def refresh_accounts(_event: Any = None) -> None:
                currency = values["currency"].get().upper()
                choices = list(account_details)
                widgets["account"].configure(values=choices)
                selected_account = values["account"].get()
                if amount_label is not None:
                    amount_label.configure(text=f"账单金额（{currency}）")
                selected_details = account_details.get(selected_account)
                selected_currency = selected_details["currency"] if selected_details else None
                if selected_currency and selected_currency != currency:
                    conversion_hint = (
                        f"账单按{currency}记录；所选账户使用{selected_currency}。到期时按账单日期的日次参考汇率换算账户扣款金额并保存汇率。"
                    )
                    if selected_details["type"] == "credit":
                        hint_var.set(
                            conversion_hint
                            + "发卡行实际入账可能因汇率或手续费不同；请以卡账单为准。本功能只记本地账本，不会实际扣款。"
                        )
                    else:
                        hint_var.set(
                            conversion_hint
                            + "实际汇差或手续费可在现金管理中手动调整；本功能只记账，不会实际扣款。"
                        )
                elif selected_currency:
                    hint_var.set(
                        f"账单和付款账户均为{currency}，按原币记账。到期时只在本地账本记录，不会连接银行或实际扣款。"
                    )
                elif choices:
                    hint_var.set(
                        "账单币种与付款账户币种独立选择。下拉框含现金管理账户和信用卡、不含积分账户；币种不同时，到期按账单日期参考汇率换算账户扣款。"
                        "实际扣款可能与参考汇率有差异，请以付款账户账单核对。"
                    )
                else:
                    hint_var.set(
                        "账本中还没有可选的现金管理账户或信用卡；请先添加银行、钱包、券/预付、交通卡或信用卡账户。"
                    )

            def refresh_categories(_event: Any = None) -> None:
                kind = "income" if values["kind"].get() == "收入" else "expense"
                choices = category_rows[kind]
                widgets["category"].configure(values=choices)
                if values["category"].get() not in choices:
                    values["category"].set("")

            widgets["kind"].bind("<<ComboboxSelected>>", refresh_categories)
            widgets["currency"].bind("<<ComboboxSelected>>", refresh_accounts)
            widgets["account"].bind("<<ComboboxSelected>>", refresh_accounts)
            refresh_categories()
            refresh_accounts()

            buttons = ttk.Frame(form_panel, style="App.TFrame")
            buttons.grid(row=11, column=0, columnspan=2, sticky="e", pady=(8, 0))

            def save() -> None:
                try:
                    if not values["account"].get():
                        raise LedgerError("请选择资金账户")
                    if not values["category"].get():
                        raise LedgerError("请选择收入或支出类别")
                    database = Database(self.database_path)
                    try:
                        database.initialize()
                        schedule_id = save_recurring_schedule(
                            database,
                            name=values["name"].get(),
                            kind="income" if values["kind"].get() == "收入" else "expense",
                            amount=values["amount"].get(),
                            currency_code=values["currency"].get(),
                            account_name=values["account"].get(),
                            category_name=values["category"].get(),
                            frequency={label: key for key, label in FREQUENCY_LABELS.items()}[values["frequency"].get()],
                            interval_count=values["interval"].get(),
                            first_date=values["date"].get(),
                            schedule_id=target_schedule_id,
                        )
                    finally:
                        database.close()
                    form.destroy()
                    refresh()
                    if existing_schedule is None:
                        status_var.set(f"定期收支规则 #{schedule_id} 已保存。到期时自动写入本地账本。")
                        self.root.after(100, self._check_due_recurring_transactions)
                    else:
                        tree.selection_set(str(schedule_id))
                        status_var.set("定期收支规则已更新；只影响后续到期项目，已生成的流水不会改变。")
                except (LedgerError, sqlite3.Error, OSError, KeyError) as exc:
                    messagebox.showerror("无法保存", str(exc), parent=form)

            ttk.Button(
                buttons,
                text="保存修改" if existing_schedule is not None else "保存",
                command=save,
            ).pack(side="right")
            ttk.Button(buttons, text="取消", command=form.destroy).pack(side="right", padx=(0, 8))

        def edit_selected_schedule() -> None:
            schedule_id = selected_schedule_id()
            if schedule_id is None:
                status_var.set("请先选择一项定期收支。")
                return
            open_schedule_form(schedule_id)

        def selected_schedule_id() -> int | None:
            selected = tree.selection()
            return int(selected[0]) if selected else None

        def toggle_selected() -> None:
            schedule_id = selected_schedule_id()
            if schedule_id is None:
                status_var.set("请先选择一项定期收支。")
                return
            database = Database(self.database_path)
            try:
                database.initialize()
                row = database.connection.execute(
                    "SELECT enabled FROM recurring_transaction_schedules WHERE id=?", (schedule_id,)
                ).fetchone()
                if row is None:
                    return
                enabled = not bool(row["enabled"])
                set_recurring_schedule_enabled(database, schedule_id, enabled)
            finally:
                database.close()
            refresh()
            status_var.set("定期收支已启用。" if enabled else "定期收支已暂停。")

        def remove_selected() -> None:
            schedule_id = selected_schedule_id()
            if schedule_id is None:
                status_var.set("请先选择一项定期收支。")
                return
            selected_values = tree.item(str(schedule_id), "values")
            schedule_name = str(selected_values[0]) if selected_values else f"规则 #{schedule_id}"
            if not confirm_delete_once(
                dialog,
                title="删除定期收支规则",
                target=f"“{schedule_name}”",
                impact="删除后将不再自动记账；已经生成的账本流水会保留。",
            ):
                return
            database = Database(self.database_path)
            try:
                database.initialize()
                delete_recurring_schedule(database, schedule_id)
            finally:
                database.close()
            refresh()
            status_var.set("规则已删除，历史账本流水已保留。")

        ttk.Button(toolbar, text="＋ 新增定期收支", command=open_schedule_form).pack(side="left")
        ttk.Button(toolbar, text="编辑规则", command=edit_selected_schedule).pack(side="left", padx=(8, 0))
        ttk.Button(toolbar, text="暂停 / 启用", command=toggle_selected).pack(side="left", padx=(8, 0))
        ttk.Button(toolbar, text="删除规则", command=remove_selected).pack(side="left", padx=(8, 0))
        if container is None:
            ttk.Button(toolbar, text="关闭", command=dialog.destroy).pack(side="right")
        refresh()

    def open_database_folder(self, parent: tk.Misc | None = None) -> None:
        dialog_parent = parent or self.root
        folder = self.database_path.parent
        if not folder.exists():
            messagebox.showerror("无法打开", f"账本文件夹不存在：\n{folder}", parent=dialog_parent)
            return
        startfile = getattr(os, "startfile", None)
        if startfile is None:
            messagebox.showinfo("账本位置", str(folder), parent=dialog_parent)
            return
        try:
            startfile(str(folder))
        except OSError as exc:
            messagebox.showerror("无法打开", f"无法打开账本文件夹：\n{exc}", parent=dialog_parent)

    def open_receipt_image_folder(self, parent: tk.Misc | None = None) -> None:
        dialog_parent = parent or self.root
        folder = self.database_path.parent / "receipt_images"
        try:
            folder.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            messagebox.showerror(
                translate("无法打开图片文件夹", self.language),
                translate("无法创建图片文件夹：{error}", self.language).format(error=exc),
                parent=dialog_parent,
            )
            return
        startfile = getattr(os, "startfile", None)
        if startfile is None:
            messagebox.showinfo(
                translate("图片文件夹", self.language),
                str(folder),
                parent=dialog_parent,
            )
            return
        try:
            startfile(str(folder))
        except OSError as exc:
            messagebox.showerror(
                translate("无法打开图片文件夹", self.language),
                translate("无法打开图片文件夹：{error}", self.language).format(error=exc),
                parent=dialog_parent,
            )

    def open_savings_plan(self, container: tk.Misc | None = None) -> None:
        if self.busy and container is None:
            messagebox.showinfo("正在记账", translate("当前记账请求完成后再查看预算管理。", self.language), parent=self.root)
            return
        show_savings_plan(
            self.root,
            self.database_path,
            self.ui_font_family,
            container=container,
        )

    def open_financial_statements(self, container: tk.Misc | None = None) -> None:
        if self.busy and container is None:
            messagebox.showinfo("正在记账", "当前记账请求完成后再查看报表。", parent=self.root)
            return

        if container is None:
            dialog = tk.Toplevel(self.root)
            dialog.title("家庭财务报表")
            window_width = min(1080, max(900, dialog.winfo_screenwidth() - 80))
            window_height = min(680, max(560, dialog.winfo_screenheight() - 100))
            dialog.geometry(f"{window_width}x{window_height}")
            dialog.minsize(min(900, window_width), min(540, window_height))
            dialog.transient(self.root)
            dialog.configure(bg=color("#f3f5f8"))
            content_parent: tk.Misc = dialog
        else:
            dialog = container.winfo_toplevel()
            content_parent = container

        panel = ttk.Frame(content_parent, style="App.TFrame", padding=12)
        panel.pack(fill="both", expand=True)
        fit_management_text(panel)
        panel.columnconfigure(0, weight=1)
        panel.rowconfigure(1, weight=1)
        ttk.Label(panel, text="家庭财务报表", style="ManagementTitle.TLabel").grid(
            row=0, column=0, sticky="w"
        )

        notebook = ttk.Notebook(panel)
        notebook.grid(row=1, column=0, sticky="nsew")
        balance_page = ttk.Frame(notebook, padding=10)
        profit_page = ttk.Frame(notebook, padding=10)
        savings_page = ttk.Frame(notebook, padding=0)
        balance_page.columnconfigure(0, weight=1)
        balance_page.rowconfigure(1, weight=1)
        profit_page.columnconfigure(0, weight=1)
        profit_page.rowconfigure(2, weight=1)
        notebook.add(balance_page, text="资产负债表")
        notebook.add(profit_page, text="本期利润表")
        notebook.add(savings_page, text=translate("预算管理", self.language))
        self.open_savings_plan(savings_page)

        balance_summary = ttk.Label(
            balance_page, style="Hint.TLabel", wraplength=900, justify="left"
        )
        balance_summary.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        balance_tree = ttk.Treeview(
            balance_page,
            columns=("include", "item", "amount"),
            show="headings", height=18,
        )
        for column, heading, width, anchor in (
            ("include", "计入", 48, "center"),
            ("item", "项目", 650, "w"),
            ("amount", "金额", 190, "e"),
        ):
            balance_tree.heading(column, text=heading)
            balance_tree.column(
                column, width=width, minwidth=70,
                stretch=column == "item", anchor=anchor,
            )
        balance_tree.tag_configure(
            "section", foreground=color("#173b63"), font=(self.ui_font_family, 11, "bold")
        )
        balance_tree.tag_configure(
            "currency_header", foreground=color("#344054"), font=(self.ui_font_family, 11, "bold")
        )
        balance_tree.tag_configure(
            "subtotal", foreground=color("#344054"), font=(self.ui_font_family, 11, "bold")
        )
        balance_tree.tag_configure("warning", foreground=color("#b54708"))
        balance_tree.tag_configure("excluded_asset", foreground=color("#667085"))
        balance_tree.tag_configure("stripe_even", background=color("#ffffff"))
        balance_tree.tag_configure("stripe_odd", background=color("#edf5ff"))
        balance_tree.grid(row=1, column=0, sticky="nsew")
        balance_scroll = ttk.Scrollbar(balance_page, orient="vertical", command=balance_tree.yview)
        balance_scroll.grid(row=1, column=1, sticky="ns")
        balance_tree.configure(yscrollcommand=balance_scroll.set)

        profit_period = ttk.Label(profit_page, style="ManagementTitle.TLabel")
        profit_period.grid(row=0, column=0, sticky="w", pady=(0, 4))
        profit_summary = ttk.Label(
            profit_page, style="Hint.TLabel", wraplength=900, justify="left"
        )
        profit_summary.grid(row=1, column=0, sticky="ew", pady=(0, 8))
        profit_tree = ttk.Treeview(
            profit_page,
            columns=("currency", "item", "amount", "note"),
            show="headings", height=18,
        )
        for column, heading, width, anchor in (
            ("currency", "币种/单位", 85, "w"), ("item", "项目", 240, "w"),
            ("amount", "金额", 145, "e"), ("note", "说明", 360, "w"),
        ):
            profit_tree.heading(column, text=heading)
            profit_tree.column(
                column, width=width, minwidth=60,
                stretch=column in {"item", "note"}, anchor=anchor,
            )
        profit_tree.tag_configure("income", foreground=color("#16803c"))
        profit_tree.tag_configure("expense", foreground=color("#c62828"))
        profit_tree.tag_configure("net_positive", foreground=color("#16803c"))
        profit_tree.tag_configure("net_negative", foreground=color("#c62828"))
        profit_tree.tag_configure("warning", foreground=color("#b54708"))
        profit_tree.tag_configure("stripe_even", background=color("#ffffff"))
        profit_tree.tag_configure("stripe_odd", background=color("#edf5ff"))
        profit_tree.grid(row=2, column=0, sticky="nsew")
        profit_scroll = ttk.Scrollbar(profit_page, orient="vertical", command=profit_tree.yview)
        profit_scroll.grid(row=2, column=1, sticky="ns")
        profit_tree.configure(yscrollcommand=profit_scroll.set)

        footer = ttk.Frame(panel, style="App.TFrame")
        footer.grid(row=3, column=0, sticky="ew", pady=(8, 0))
        report_status = ttk.Label(footer, style="Hint.TLabel")
        report_status.pack(side="left", fill="x", expand=True)

        balance_asset_rows: dict[str, tuple[int, bool]] = {}

        def refresh() -> None:
            report_status.configure(text="正在读取账本…")
            database = Database(self.database_path)
            try:
                database.initialize()
                today = _today_japan()
                balance = build_balance_sheet(database, today)
                profit = build_profit_statement(database, today)
                currency_digits = {
                    row["code"]: int(row["minor_digits"])
                    for row in database.connection.execute("SELECT code,minor_digits FROM currencies")
                }
            except (LedgerError, ValueError) as exc:
                messagebox.showerror("无法读取报表", str(exc), parent=dialog)
                report_status.configure(text="读取失败。")
                return
            finally:
                database.close()

            def grouped_amounts(values: dict[str, int]) -> str:
                return "；".join(
                    minor_to_text(int(values.get(code, 0)), currency_digits[code], code)
                    for code in sorted(values)
                )

            balance_tree.delete(*balance_tree.get_children())
            balance_asset_rows.clear()
            balance_rows = balance["rows"]
            asset_sections = {"货币资产", "资产（信用卡贷余）", "固定资产"}
            liability_sections = {"信用卡负债估算", "已确认负债", "负债（待录入额度）", "信用卡"}
            uncertain_sections = {"负余额（待核对）", "积分负数（待核对）", "非货币负数（待核对）"}
            asset_rows = [row for row in balance_rows if row["section"] in asset_sections]
            liability_rows = [row for row in balance_rows if row["section"] in liability_sections]
            points_rows = [row for row in balance_rows if row["section"] == "积分（不计入资产）"]
            other_asset_rows = [row for row in balance_rows if row["section"] == "非货币资产"]
            uncertain_rows = [row for row in balance_rows if row["section"] in uncertain_sections]
            future_rows = [row for row in balance_rows if row["section"] == "未生效账户"]
            classified_ids = {
                id(row)
                for group in (asset_rows, liability_rows, points_rows, other_asset_rows, uncertain_rows, future_rows)
                for row in group
            }
            other_rows = [row for row in balance_rows if id(row) not in classified_ids]

            balance_stripe_index = 0
            def add_balance_row(
                item: str,
                amount: str = "",
                tag: str | None = None,
                *,
                asset_id: int | None = None,
                included: bool = False,
            ) -> None:
                nonlocal balance_stripe_index
                stripe = "stripe_even" if balance_stripe_index % 2 == 0 else "stripe_odd"
                balance_stripe_index += 1
                tags = (stripe, tag) if tag else (stripe,)
                checkbox = ("☑" if included else "☐") if asset_id is not None else ""
                tree_item_id = balance_tree.insert(
                    "", "end", values=(checkbox, translate_tree_item(item), amount), tags=tags,
                )
                if asset_id is not None:
                    balance_asset_rows[tree_item_id] = (asset_id, included)

            def row_label(row: dict[str, Any]) -> str:
                detail = str(row["status"]).strip()
                return f"  {row['name']}（{detail}）" if detail else f"  {row['name']}"

            def code_order(code: str) -> tuple[int, str]:
                return ({"JPY": 0, "CNY": 1}.get(code, 2), code)

            def add_currency_block(code: str) -> None:
                digits = currency_digits.get(code, 0)
                asset_total = int(balance["assets"].get(code, 0))
                liability_total = int(balance["known_liabilities"].get(code, 0)) + int(
                    balance["estimated_liabilities"].get(code, 0)
                )
                add_balance_row(f"{code}资产负债", tag="section")
                add_balance_row(f"{code}资产", tag="currency_header")
                for row in asset_rows:
                    if row["currency"] == code:
                        is_fixed_asset = row["section"] == "固定资产"
                        included = bool(row.get("include_in_balance_sheet", False))
                        add_balance_row(
                            row_label(row),
                            row["amount_text"],
                            "excluded_asset" if is_fixed_asset and not included else None,
                            asset_id=int(row["asset_id"]) if is_fixed_asset else None,
                            included=included,
                        )
                add_balance_row(
                    f"  {code}资产合计", minor_to_text(asset_total, digits, code), "subtotal",
                )
                add_balance_row(f"{code}负债", tag="currency_header")
                for row in liability_rows:
                    if row["currency"] == code:
                        add_balance_row(row_label(row), row["amount_text"])
                liability_label = f"  {code}负债小计" if balance["unknown_liability_count"] else f"  {code}负债合计"
                add_balance_row(
                    liability_label, minor_to_text(liability_total, digits, code), "subtotal",
                )
                add_balance_row(
                    f"  {code}净资产（已计负债）",
                    minor_to_text(int(balance["net_assets"].get(code, 0)), digits, code),
                    "subtotal",
                )

            for code in sorted(balance["assets"], key=code_order):
                add_currency_block(code)
                if code == "JPY":
                    add_balance_row("积分（单独展示，不计入资产）", tag="section")
                    for row in points_rows:
                        add_balance_row(row_label(row), row["amount_text"])
                    for row in uncertain_rows:
                        if row["section"] == "积分负数（待核对）":
                            add_balance_row(row_label(row), row["amount_text"], "warning")

            if other_asset_rows:
                add_balance_row("其他非货币资产", tag="currency_header")
                for row in other_asset_rows:
                    add_balance_row(row_label(row), row["amount_text"])

            other_uncertain_rows = [
                row for row in uncertain_rows if row["section"] != "积分负数（待核对）"
            ]
            if other_uncertain_rows:
                add_balance_row("待核对负余额（未计入资产合计）", tag="currency_header")
                for row in other_uncertain_rows:
                    add_balance_row(row_label(row), row["amount_text"], "warning")

            if balance["unknown_liability_count"]:
                count = int(balance["unknown_liability_count"])
                add_balance_row(
                    "  未估算信用卡负债",
                    f"{count}张（未计入负债小计）",
                    "warning",
                )

            if future_rows or other_rows:
                add_balance_row("其他/尚未生效项目", tag="currency_header")
                for row in future_rows + other_rows:
                    add_balance_row(row_label(row), row["amount_text"], "warning")
            balance_summary.configure(
                text=(
                    f"截至 {balance['as_of']}　银行存款：{grouped_amounts(balance['bank_deposits'])}　"
                    f"全部货币资产：{grouped_amounts(balance['assets'])}　"
                    f"信用卡欠款估算：{grouped_amounts(balance['estimated_liabilities'])}　"
                    f"已确认账面负债：{grouped_amounts(balance['known_liabilities'])}"
                )
            )
            profit_tree.delete(*profit_tree.get_children())
            profit_stripe_index = 0

            def add_profit_row(values: tuple[str, str, str, str], tags: tuple[str, ...] = ()) -> None:
                nonlocal profit_stripe_index
                stripe = "stripe_even" if profit_stripe_index % 2 == 0 else "stripe_odd"
                profit_stripe_index += 1
                profit_tree.insert(
                    "", "end", values=translate_tree_item(values), tags=(stripe, *tags)
                )

            profit_period.configure(text=f"本期：{profit['start']} 至 {profit['end']}")
            profit_summary.configure(
                text=(
                    f"统计截至 {profit['through']}；当前银行存款：{grouped_amounts(balance['bank_deposits'])}。"
                    "消费合计包含备查支出；备查不改变账户余额。转账和信用卡还款不计作支出。"
                )
            )
            for code, values in profit["currencies"].items():
                digits = values["minor_digits"]

                def money(value: int) -> str:
                    return minor_to_text(int(value), digits, code)

                add_profit_row(
                    (code, "收入合计", money(values["income_minor"]), "已记录收入"), ("income",),
                )
                add_profit_row(
                    (code, "消费合计", money(-int(values["expense_minor"])), "包含已入账与备查支出"),
                    ("expense",),
                )
                add_profit_row(
                    (code, "其中：已入账消费", money(-int(values["posted_expense_minor"])), "会影响账户余额"),
                    ("expense",),
                )
                if values["memo_expense_minor"]:
                    add_profit_row(
                        (code, "其中：仅备查消费", money(-int(values["memo_expense_minor"])), "不影响任何账户余额"),
                        ("expense",),
                    )
                if values["needs_review_expense_minor"]:
                    add_profit_row(
                        (code, "待核对消费", money(-int(values["needs_review_expense_minor"])), "包含在消费合计中，请核实"),
                        ("expense",),
                    )
                for category, amount in sorted(values["categories"].items(), key=lambda item: (-item[1], item[0])):
                    add_profit_row(
                        (code, f"支出分类：{category}", money(-int(amount)), "按账本分类汇总"),
                        ("expense",),
                    )
                net_minor = int(values["net_minor"])
                net_tag = "net_positive" if net_minor > 0 else "net_negative" if net_minor < 0 else ""
                add_profit_row(
                    (code, "本期合计", money(net_minor), "收入减消费；备查消费也计入"),
                    (net_tag,) if net_tag else (),
                )
            jpy_total = profit["jpy_equivalent"]
            jpy_money = lambda value: minor_to_text(int(value), currency_digits["JPY"], "JPY")
            add_profit_row(
                ("JPY合并口径", "收入合计", jpy_money(jpy_total["income_minor"]), "JPY原币收入 + CNY按交易日汇率折算"),
                ("income",),
            )
            add_profit_row(
                ("JPY合并口径", "消费合计", jpy_money(-int(jpy_total["expense_minor"])), "JPY原币消费 + CNY按交易日汇率折算"),
                ("expense",),
            )
            for category, amount in sorted(
                jpy_total["categories"].items(), key=lambda item: (-item[1], item[0])
            ):
                add_profit_row(
                    ("JPY合并口径", f"支出分类：{category}", jpy_money(-int(amount)), "含人民币交易日汇率折算"),
                    ("expense",),
                )
            net_minor = int(jpy_total["net_minor"])
            net_tag = "net_positive" if net_minor > 0 else "net_negative" if net_minor < 0 else ""
            add_profit_row(
                ("JPY合并口径", "本期合计", jpy_money(net_minor), "全部已折算收支相抵"),
                (net_tag,) if net_tag else (),
            )
            if jpy_total["missing_conversion_count"]:
                count = int(jpy_total["missing_conversion_count"])
                add_profit_row(
                    ("待补汇率", "未折算流水", f"{count} 笔", "不计入JPY合并口径；需补充历史汇率"),
                    ("warning",),
                )
            report_status.configure(text="报表已按账本最新记录刷新。")

        def toggle_fixed_asset(event: Any) -> str | None:
            if balance_tree.identify_region(event.x, event.y) != "cell":
                return None
            if balance_tree.identify_column(event.x) != "#1":
                return None
            item_id = balance_tree.identify_row(event.y)
            asset_info = balance_asset_rows.get(item_id)
            if asset_info is None:
                return None
            asset_id, currently_included = asset_info
            database = Database(self.database_path)
            try:
                database.initialize()
                database.set_fixed_asset_inclusion(asset_id, not currently_included)
            except (LedgerError, sqlite3.Error, OSError) as exc:
                messagebox.showerror("更新失败", str(exc), parent=dialog)
                return "break"
            finally:
                database.close()
            refresh()
            return "break"

        balance_tree.bind("<Button-1>", toggle_fixed_asset, add="+")

        ttk.Button(footer, text="刷新报表", command=refresh).pack(side="right", padx=(8, 0))
        if container is None:
            ttk.Button(footer, text="关闭", command=dialog.destroy).pack(side="right")
        refresh()

    def open_fixed_assets(self) -> None:
        if self.busy:
            messagebox.showinfo("正在记账", "当前记账请求完成后再管理固定资产。", parent=self.root)
            return
        open_fixed_asset_management(self.root, self.database_path)

    def open_cash_management(self, container: tk.Misc | None = None) -> None:
        if self.busy and container is None:
            messagebox.showinfo("正在记账", "当前记账请求完成后再调整现金。", parent=self.root)
            return

        database = Database(self.database_path)
        try:
            database.initialize()
        finally:
            database.close()

        if container is None:
            dialog = tk.Toplevel(self.root)
            dialog.title("现金管理")
            dialog.geometry("860x640")
            dialog.minsize(760, 560)
            dialog.transient(self.root)
            dialog.configure(bg=color("#f3f5f8"))
            content_parent: tk.Misc = dialog
        else:
            dialog = container.winfo_toplevel()
            content_parent = container

        panel = ttk.Frame(content_parent, style="App.TFrame", padding=12)
        panel.pack(fill="both", expand=True)
        fit_management_text(panel)
        panel.columnconfigure(0, weight=1)
        panel.rowconfigure(3, weight=1)
        ttk.Label(panel, text="现金管理表", style="ManagementTitle.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(
            panel,
            text="表内显示非信用卡资金账户和积分；余额平时只读。可新增银行、钱包、券/预付、交通卡或积分账户。未关联流水或计划的账户可删除，删除前会自动备份并确认一次。信用卡单独管理，不计入现金表。",
            style="Hint.TLabel",
            wraplength=740,
        ).grid(row=1, column=0, sticky="ew", pady=(4, 8))

        toolbar = ttk.Frame(panel, style="App.TFrame")
        toolbar.grid(row=2, column=0, sticky="ew")
        ttk.Label(toolbar, text="排序：", style="Hint.TLabel").pack(side="left")
        sort_var = tk.StringVar(value="默认排序")
        sort_box = ttk.Combobox(
            toolbar, textvariable=sort_var, values=("默认排序", "按币种"),
            state="readonly", width=12,
        )
        sort_box.pack(side="left", padx=(0, 12))

        scroll_frame = ttk.Frame(panel, style="App.TFrame")
        scroll_frame.grid(row=3, column=0, sticky="nsew", pady=(8, 0))
        scroll_frame.columnconfigure(0, weight=1)
        scroll_frame.rowconfigure(0, weight=1)
        table_canvas = tk.Canvas(scroll_frame, background=color("#f3f5f8"), highlightthickness=0)
        table_canvas.grid(row=0, column=0, sticky="nsew")
        table_scrollbar = ttk.Scrollbar(scroll_frame, orient="vertical", command=table_canvas.yview)
        table_scrollbar.grid(row=0, column=1, sticky="ns")
        table_canvas.configure(yscrollcommand=table_scrollbar.set)
        table = ttk.Frame(table_canvas, style="App.TFrame", padding=(0, 4))
        table_canvas_item = table_canvas.create_window((0, 0), window=table, anchor="nw")
        def update_table_scrollregion(_event=None):
            def callback():
                if table_canvas.winfo_exists():
                    table_canvas.configure(scrollregion=table_canvas.bbox("all"))
            if defer_during_interactive_resize(
                    table_canvas, (table_canvas, "scrollregion"), callback):
                return
            callback()

        def resize_table_content(event):
            def callback(width=event.width):
                if table_canvas.winfo_exists():
                    table_canvas.itemconfigure(table_canvas_item, width=width)
            if defer_during_interactive_resize(
                    table_canvas, (table_canvas, "content-width"), callback):
                return
            callback()

        table.bind("<Configure>", update_table_scrollregion)
        table_canvas.bind("<Configure>", resize_table_content)

        row_widgets: dict[str, dict[str, Any]] = {}
        type_labels = {
            "cash": "现金",
            "bank": "银行",
            "wallet": "钱包",
            "prepaid": "券/预付",
            "transit": "交通卡",
            "points": "积分",
        }
        current_rows: dict[str, dict[str, Any]] = {}
        editing = False
        numbers_hidden = tk.BooleanVar(value=bool(getattr(getattr(self, "desktop_shell", None), "hidden", False)))
        record_difference_var = tk.BooleanVar(value=True)
        status_var = tk.StringVar(
            value="可按当前顺序或币种排序。点击“调整差额”后编辑余额；新增账户时请填写真实期初余额和日期。"
        )
        status_message = status_var.get()

        def set_status(message: str) -> None:
            nonlocal status_message
            status_message = message
            status_var.set(
                _mask_display_numbers(message) if numbers_hidden.get() else message
            )

        ttk.Label(
            panel,
            textvariable=status_var,
            style="Hint.TLabel",
            wraplength=740,
        ).grid(row=4, column=0, sticky="ew", pady=(10, 4))
        buttons = ttk.Frame(panel, style="App.TFrame")
        buttons.grid(row=5, column=0, sticky="ew", pady=(8, 0))

        def render_table(rows: list[dict[str, Any]]) -> None:
            for child in table.winfo_children():
                child.destroy()
            row_widgets.clear()
            for column, weight in ((0, 0), (1, 1), (2, 1), (3, 0), (4, 0)):
                table.columnconfigure(column, weight=weight)
            headers = ("币种/单位", "账户", "余额/点数（平时只读）", "状态", "操作")
            for column, heading in enumerate(headers):
                ttk.Label(table, text=heading, style="Hint.TLabel").grid(
                    row=0, column=column, sticky="w", padx=(4, 16), pady=(0, 8)
                )

            for row_index, row in enumerate(rows, start=1):
                account_name = row["account_name"]
                currency_text = row.get("display_currency", row["currency"])
                account_label = f"{account_name}（{type_labels.get(row['account_type'], row['account_type'])}）"
                if numbers_hidden.get():
                    currency_text = _mask_display_numbers(currency_text)
                    account_label = _mask_display_numbers(account_label)
                ttk.Label(table, text=currency_text, style="Hint.TLabel").grid(
                    row=row_index, column=0, sticky="w", padx=4, pady=3
                )
                ttk.Label(table, text=account_label, style="Hint.TLabel").grid(
                    row=row_index, column=1, sticky="w", padx=(4, 16), pady=3
                )
                amount_var = tk.StringVar()
                amount_entry = ttk.Entry(
                    table, textvariable=amount_var,
                    state="normal" if editing else "readonly", font=(self.ui_font_family, 10),
                )
                amount_entry.grid(row=row_index, column=2, sticky="ew", padx=(4, 16), pady=2)
                state_label = ttk.Label(table, text="", style="Hint.TLabel")
                state_label.grid(row=row_index, column=3, sticky="w", padx=(4, 10), pady=3)
                delete_button: ttk.Button | None = None
                if row["initialized"]:
                    delete_button = ttk.Button(
                        table,
                        text="删除账户",
                        command=lambda name=account_name: delete_managed_account(name),
                    )
                    delete_button.grid(row=row_index, column=4, sticky="ew", padx=(4, 0), pady=2)
                else:
                    ttk.Label(table, text="—", style="Hint.TLabel").grid(
                        row=row_index, column=4, sticky="w", padx=(4, 10), pady=3
                    )
                row_widgets[account_name] = {
                    "amount": amount_var,
                    "entry": amount_entry,
                    "status": state_label,
                    "delete": delete_button,
                }

                if row["initialized"]:
                    balance = Decimal(row["balance_minor"]).scaleb(-row["minor_digits"])
                    amount_text = format(balance, "f")
                    amount_var.set(
                        _mask_display_numbers(amount_text)
                        if numbers_hidden.get() and not editing
                        else amount_text
                    )
                    if row["completeness"] == "inferred":
                        status_text = "包含推算期初"
                    elif row["completeness"] == "partial":
                        status_text = "记录不完整"
                    elif row["account_type"] == "points":
                        status_text = "积分余额已载入"
                    else:
                        status_text = "账面余额已载入"
                else:
                    amount_var.set("")
                    status_text = "等待首次盘点"
                state_label.configure(text="输入实际余额" if editing else status_text)

        def selected_sort_mode() -> str:
            return "currency" if sort_var.get() == "按币种" else "default"

        def refresh_table() -> None:
            nonlocal current_rows
            database = Database(self.database_path)
            try:
                database.initialize()
                rows = managed_balances(database)
                current_rows = {row["account_name"]: row for row in rows}
                ordered_rows = sort_managed_balances(rows, selected_sort_mode())
                render_table(ordered_rows)
            finally:
                database.close()

        def delete_managed_account(account_name: str) -> None:
            if editing:
                messagebox.showinfo("请先退出调整", "保存或取消余额调整后再删除账户。", parent=dialog)
                return
            row = current_rows.get(account_name)
            if not row or not row["initialized"] or row["account_id"] is None:
                messagebox.showinfo("账户尚未创建", "这行是等待首次盘点的实体现金项目，目前没有可删除的账户。", parent=dialog)
                return
            if not confirm_delete_once(
                dialog,
                title="删除现金管理账户",
                target=f"账户“{account_name}”及其余额快照",
                impact=(
                    "已有账本流水、定期收支或还款计划的账户不能删除。删除前会自动备份账本；"
                    "若支付规则中写有此账户名称，删除后请到“支付方式与用途”同步修改。"
                ),
            ):
                return

            database = Database(self.database_path)
            try:
                database.initialize()
                backup_path = database.delete_managed_account(account_name)
            except (LedgerError, sqlite3.Error, OSError) as exc:
                messagebox.showerror("无法删除账户", str(exc), parent=dialog)
                return
            finally:
                database.close()
            refresh_table()
            status_text = f"账户“{account_name}”已删除。删除前备份：{backup_path}"
            if account_name in {"现金（日元）", "现金（人民币）"}:
                status_text += " 默认首次盘点行已一并移除；需要时可用同名钱包账户重新添加。"
            set_status(status_text)

        def set_editing_controls(is_editing: bool) -> None:
            nonlocal editing
            editing = is_editing
            add_account_button.configure(state="disabled" if is_editing else "normal")
            sort_box.configure(state="disabled" if is_editing else "readonly")
            number_visibility_button.configure(
                state="disabled" if is_editing else "normal"
            )
            for row_widgets_for_account in row_widgets.values():
                delete_button = row_widgets_for_account.get("delete")
                if delete_button is not None:
                    delete_button.configure(state="disabled" if is_editing else "normal")

        def update_adjustment_button_label(*_args: Any) -> None:
            if editing:
                edit_button.configure(
                    text="确认调整并记账" if record_difference_var.get() else "确认调整（不记账）"
                )

        def open_add_account() -> None:
            add_dialog = tk.Toplevel(dialog)
            add_dialog.title("添加资金账户")
            add_dialog.geometry("560x500")
            add_dialog.minsize(520, 470)
            add_dialog.transient(dialog)
            add_dialog.grab_set()
            form = ttk.Frame(add_dialog, style="App.TFrame", padding=12)
            form.pack(fill="both", expand=True)
            form.columnconfigure(1, weight=1)
            ttk.Label(form, text="添加资金账户", style="ManagementTitle.TLabel").grid(
                row=0, column=0, columnspan=2, sticky="w", pady=(0, 8)
            )
            ttk.Label(
                form,
                text="信用卡不属于现金管理表；此处新增账户只建立期初余额，不会自动生成收支。",
                style="Hint.TLabel", wraplength=460,
            ).grid(row=1, column=0, columnspan=2, sticky="ew", pady=(0, 14))

            account_types = {
                "银行": "bank",
                "钱包": "wallet",
                "券/预付": "prepaid",
                "交通卡": "transit",
                "积分": "points",
            }
            completeness_values = {
                "已确认": "known",
                "推算值": "inferred",
                "记录不完整": "partial",
            }
            name_var = tk.StringVar()
            type_var = tk.StringVar(value="银行")
            currency_var = tk.StringVar(value="JPY")
            amount_var = tk.StringVar()
            date_var = tk.StringVar(value=_today_japan())
            completeness_var = tk.StringVar(value="已确认")
            note_var = tk.StringVar()

            currency_box = ttk.Combobox(
                form, textvariable=currency_var, values=("JPY", "CNY"), state="readonly"
            )
            fields = (
                ("账户名称", ttk.Entry(form, textvariable=name_var)),
                ("账户类型", ttk.Combobox(form, textvariable=type_var, values=tuple(account_types), state="readonly")),
                ("币种/单位（积分按JPY等值）", currency_box),
                ("期初余额/点数", ttk.Entry(form, textvariable=amount_var)),
                ("期初日期", ttk.Entry(form, textvariable=date_var)),
                ("余额完整度", ttk.Combobox(form, textvariable=completeness_var, values=tuple(completeness_values), state="readonly")),
                ("备注", ttk.Entry(form, textvariable=note_var)),
            )
            field_widgets: dict[str, Any] = {}
            for index, (label, widget) in enumerate(fields, start=2):
                ttk.Label(form, text=label, style="Hint.TLabel").grid(
                    row=index, column=0, sticky="w", padx=(0, 12), pady=5
                )
                widget.grid(row=index, column=1, sticky="ew", pady=5)
                field_widgets[label] = widget

            def sync_account_currency(*_args: Any) -> None:
                if type_var.get() == "积分":
                    currency_var.set("JPY")
                    currency_box.configure(state="disabled")
                else:
                    currency_box.configure(state="readonly")

            type_var.trace_add("write", sync_account_currency)
            sync_account_currency()

            def save_new_account() -> None:
                name = name_var.get().strip()
                amount = amount_var.get().strip()
                if not name:
                    messagebox.showwarning("缺少账户名称", "请填写账户名称。", parent=add_dialog)
                    return
                if not amount:
                    messagebox.showwarning("缺少期初余额", "请填写当前已确认的余额/点数；未知时可填0并标记为记录不完整。", parent=add_dialog)
                    return
                database = Database(self.database_path)
                try:
                    database.initialize()
                    database.add_account(
                        name=name,
                        account_type=account_types[type_var.get()],
                        currency=currency_var.get(),
                        opening_balance=amount,
                        opening_date=date_var.get().strip(),
                        completeness=completeness_values[completeness_var.get()],
                        note=note_var.get().strip(),
                    )
                except LedgerError as exc:
                    messagebox.showerror("无法添加账户", str(exc), parent=add_dialog)
                    return
                finally:
                    database.close()
                add_dialog.destroy()
                refresh_table()
                set_status(f"账户“{name}”已添加，并按当前排序规则排列。没有创建额外收支分录。")

            actions = ttk.Frame(form, style="App.TFrame")
            actions.grid(row=9, column=0, columnspan=2, sticky="ew", pady=(16, 0))
            ttk.Button(actions, text="取消", command=add_dialog.destroy).pack(side="right", padx=(8, 0))
            ttk.Button(actions, text="保存账户", style="Send.TButton", command=save_new_account).pack(side="right")
            field_widgets["账户名称"].focus_set()

        def start_edit() -> None:
            if numbers_hidden.get():
                messagebox.showinfo("请先显示数字", "点击“显示数字”后再调整账户余额。", parent=dialog)
                return
            set_editing_controls(True)
            set_status(
                "所有账户余额和积分格已解锁。将数值改成实际余额/积分；留空项目不变。"
                "勾选“将差额记入账本”会新增盘盈/盘亏流水；取消时已建账户只更新余额快照，首次盘点只建立期初余额。"
            )
            for account_name, row in current_rows.items():
                if not row["initialized"]:
                    row_widgets[account_name]["amount"].set("")
                row_widgets[account_name]["status"].configure(text="输入实际余额")
                row_widgets[account_name]["entry"].configure(state="normal")
            edit_button.configure(
                text="确认调整并记账" if record_difference_var.get() else "确认调整（不记账）",
                command=save_adjustments,
            )
            cancel_button.configure(state="normal")
            first_name = next(iter(current_rows))
            row_widgets[first_name]["entry"].focus_set()

        def cancel_edit() -> None:
            set_editing_controls(False)
            record_difference_var.set(True)
            refresh_table()
            set_status("已取消调整；账本未变更。")
            edit_button.configure(text="调整差额", command=start_edit)
            cancel_button.configure(state="disabled")

        def save_adjustments() -> None:
            counts: dict[str, str] = {}
            database = Database(self.database_path)
            try:
                database.initialize()
                for account_name, row_widgets_for_account in row_widgets.items():
                    value = row_widgets_for_account["amount"].get().strip()
                    if not value:
                        continue
                    row = current_rows[account_name]
                    to_minor_allow_zero(value, row["currency"], row["minor_digits"])
                    counts[account_name] = value
                if not counts:
                    messagebox.showinfo("没有填写余额", "请输入至少一个账户的余额或积分数。", parent=dialog)
                    return
                results = reconcile_account_balances(
                    database,
                    counts,
                    _today_japan(),
                    post_differences=record_difference_var.get(),
                )
            except LedgerError as exc:
                messagebox.showerror("无法调整余额", str(exc), parent=dialog)
                return
            finally:
                database.close()

            messages: list[str] = []
            for result in results:
                account_name = result["account_name"]
                currency = result["currency"]
                digits = result["minor_digits"]
                if result["opening_balance"]:
                    messages.append(
                        f"{account_name}首次盘点：期初余额 {format_account_amount(result['balance_minor'], digits, currency, result['account_type'])}。"
                    )
                elif result["difference_minor"] == 0:
                    messages.append(f"{account_name}与账面一致，没有新增分录。")
                elif not result["difference_posted"]:
                    balance_text = format_account_amount(
                        result["balance_minor"], digits, currency, result["account_type"]
                    )
                    messages.append(
                        f"{account_name}余额已校准为{balance_text}；差额已保存为余额快照，未生成账本分录。"
                    )
                else:
                    difference = result["difference_minor"]
                    signed = "+" if difference > 0 else "−"
                    amount_text = format_account_amount(abs(difference), digits, currency, result["account_type"])
                    balance_text = format_account_amount(result["balance_minor"], digits, currency, result["account_type"])
                    messages.append(
                        f"{result['category_name']} #{result['transaction_id']}：{account_name} {signed}{amount_text}；新余额 {balance_text}。"
                    )
            set_editing_controls(False)
            record_difference_var.set(True)
            refresh_table()
            set_status("调整已保存。")
            edit_button.configure(text="调整差额", command=start_edit)
            cancel_button.configure(state="disabled")
            messagebox.showinfo("余额调整完成", "\n".join(messages), parent=dialog)
            if any(result["transaction_id"] is not None for result in results):
                self._queue_github_auto_sync()

        add_account_button = ttk.Button(toolbar, text="＋ 添加账户", command=open_add_account)
        add_account_button.pack(side="left")
        number_visibility_button = ttk.Button(
            toolbar, text="显示数字" if numbers_hidden.get() else "隐藏数字", command=lambda: toggle_number_visibility()
        )
        number_visibility_button.pack(side="right")

        def toggle_number_visibility() -> None:
            numbers_hidden.set(not numbers_hidden.get())
            number_visibility_button.configure(
                text="显示数字" if numbers_hidden.get() else "隐藏数字"
            )
            set_status(status_message)
            refresh_table()

        record_difference_check = ttk.Checkbutton(
            buttons,
            text="将差额记入账本",
            variable=record_difference_var,
            command=update_adjustment_button_label,
        )
        record_difference_check.pack(side="left", padx=(0, 12))
        edit_button = ttk.Button(buttons, text="调整差额", command=start_edit)
        edit_button.pack(side="left")
        record_difference_var.trace_add("write", update_adjustment_button_label)
        cancel_button = ttk.Button(buttons, text="取消编辑", command=cancel_edit, state="disabled")
        cancel_button.pack(side="left", padx=(8, 0))
        if container is None:
            ttk.Button(buttons, text="关闭", command=dialog.destroy).pack(side="right")
        sort_box.bind("<<ComboboxSelected>>", lambda _event: refresh_table())
        wrap_management_toolbar(buttons)
        refresh_table()

    def open_credit_management(self, container: tk.Misc | None = None) -> None:
        if self.busy and container is None:
            messagebox.showinfo("正在记账", "当前记账请求完成后再管理信用卡。", parent=self.root)
            return

        if container is None:
            dialog = tk.Toplevel(self.root)
            dialog.title("信用卡管理")
            dialog.geometry("980x660")
            dialog.minsize(840, 560)
            dialog.transient(self.root)
            dialog.configure(bg=color("#f3f5f8"))
            content_parent: tk.Misc = dialog
        else:
            dialog = container.winfo_toplevel()
            content_parent = container
        panel = ttk.Frame(content_parent, style="App.TFrame", padding=12)
        panel.pack(fill="both", expand=True)
        fit_management_text(panel)
        panel.columnconfigure(0, weight=1)
        panel.rowconfigure(3, weight=3)
        panel.rowconfigure(5, weight=2)

        ttk.Label(panel, text="信用卡管理", style="ManagementTitle.TLabel").grid(
            row=0, column=0, sticky="w"
        )
        ttk.Label(
            panel,
            text="当前欠款估算 = 总额度 − 当前可用额度。可用额度从手工快照按账内消费、退款和还款更新。还款只记账户间转账。每张卡固定扣款账户和还款日；本期金额需要每月填写，空白不记账、下月不沿用。计划只会写入本地账本，不会操作银行扣款。",
            style="Hint.TLabel", wraplength=920,
        ).grid(row=1, column=0, sticky="ew", pady=(4, 8))

        controls = ttk.Frame(panel, style="App.TFrame")
        controls.grid(row=2, column=0, sticky="ew", pady=(0, 8))
        numbers_hidden = tk.BooleanVar(value=bool(getattr(getattr(self, "desktop_shell", None), "hidden", False)))
        status_var = tk.StringVar(value="可登记新卡、保存额度快照或记录还款。")
        status_message = status_var.get()
        card_names_by_id: dict[int, str] = {}

        def set_status(message: str) -> None:
            nonlocal status_message
            status_message = message
            status_var.set(
                _mask_display_numbers(message) if numbers_hidden.get() else message
            )

        card_area = ttk.Frame(panel,style="App.TFrame")
        card_area.grid(row=3,column=0,columnspan=2,sticky="nsew")
        card_area.columnconfigure(0,weight=1);card_area.rowconfigure(0,weight=1)
        card_tree = ttk.Treeview(
            card_area,
            columns=("name", "currency", "limit", "available", "debt", "monthly_due", "due_date", "snapshot", "history"),
            show="headings", height=4,
        )
        card_headers = {
            "name": ("信用卡", 125),
            "currency": ("币种", 55),
            "limit": ("总额度", 95),
            "available": ("当前可用额度", 110),
            "debt": ("当前欠款估算", 115),
            "monthly_due": ("本期金额", 100),
            "due_date": ("下次还款日", 95),
            "snapshot": ("快照日期", 90),
            "history": ("历史记录", 90),
        }
        for column, (heading, width) in card_headers.items():
            card_tree.heading(column, text=heading)
            card_tree.column(column, width=width, minwidth=55, stretch=column in {"name", "history"})
        card_tree.grid(row=0, column=0, sticky="nsew")
        card_scroll = ttk.Scrollbar(card_area, orient="vertical", command=card_tree.yview)
        card_scroll.grid(row=0, column=1, sticky="ns")
        card_horizontal=ttk.Scrollbar(card_area,orient="horizontal",command=card_tree.xview)
        card_horizontal.grid(row=1,column=0,sticky="ew")
        card_tree.configure(yscrollcommand=card_scroll.set,xscrollcommand=card_horizontal.set)

        ttk.Label(panel, text="最近信用卡还款", style="ManagementSection.TLabel").grid(
            row=4, column=0, sticky="w", pady=(14, 4)
        )
        history_area=ttk.Frame(panel,style="App.TFrame")
        history_area.grid(row=5,column=0,columnspan=2,sticky="nsew")
        history_area.columnconfigure(0,weight=1);history_area.rowconfigure(0,weight=1)
        history_tree = ttk.Treeview(
            history_area, columns=("date", "source", "card", "amount", "description"),
            show="headings", height=4,
        )
        history_headers = {
            "date": ("日期", 100),
            "source": ("转出账户", 150),
            "card": ("信用卡", 150),
            "amount": ("还款金额", 120),
            "description": ("备注", 300),
        }
        for column, (heading, width) in history_headers.items():
            history_tree.heading(column, text=heading)
            history_tree.column(column, width=width, minwidth=70, stretch=column == "description")
        history_tree.grid(row=0, column=0, sticky="nsew")
        history_scroll = ttk.Scrollbar(history_area, orient="vertical", command=history_tree.yview)
        history_scroll.grid(row=0, column=1, sticky="ns")
        history_horizontal=ttk.Scrollbar(history_area,orient="horizontal",command=history_tree.xview)
        history_horizontal.grid(row=1,column=0,sticky="ew")
        history_tree.configure(yscrollcommand=history_scroll.set,xscrollcommand=history_horizontal.set)

        ttk.Label(panel, textvariable=status_var, style="Status.TLabel", wraplength=920).grid(
            row=6, column=0, sticky="ew", pady=(10, 2)
        )
        buttons = ttk.Frame(panel, style="App.TFrame")
        buttons.grid(row=7, column=0, sticky="ew", pady=(8, 0))

        def refresh_cards() -> None:
            nonlocal card_names_by_id
            database = Database(self.database_path)
            try:
                database.initialize()
                cards = credit_card_overview(database)
                repayments = recent_credit_repayments(database)
            finally:
                database.close()
            card_names_by_id = {
                int(card["account_id"]): str(card["name"])
                for card in cards
            }
            card_tree.delete(*card_tree.get_children())
            for card in cards:
                digits = card["minor_digits"]
                code = card["currency"]
                limit_text = (
                    minor_to_text(card["limit_minor"], digits, code)
                    if card["limit_minor"] is not None else "未录入"
                )
                available_text = (
                    minor_to_text(card["available_minor"], digits, code)
                    if card["available_minor"] is not None else "未录入"
                )
                debt_text = (
                    minor_to_text(card["debt_estimate_minor"], digits, code)
                    if card["debt_estimate_minor"] is not None else "无法估算"
                )
                schedule = card["repayment_schedule"]
                monthly_due = (
                    minor_to_text(schedule["amount_minor"], digits, code)
                    if schedule and schedule.get("amount_minor") is not None
                    else ("本期未填写" if schedule else "未设置")
                )
                next_due = (
                    schedule["next_due_date"] if schedule and schedule["enabled"]
                    else ("已暂停" if schedule else "—")
                )
                completeness = {
                    "partial": "历史不完整",
                    "inferred": "期初为推算",
                    "known": "完整记录",
                }.get(card["completeness"], "待核对")
                card_values = (
                    card["name"], code, limit_text, available_text, debt_text,
                    monthly_due, next_due,
                    card["snapshot_date"] or "未录入",
                    completeness,
                )
                if numbers_hidden.get():
                    card_values = tuple(_mask_display_numbers(value) for value in card_values)
                card_tree.insert(
                    "", "end",
                    iid=str(card["account_id"]),
                    values=card_values,
                )
            history_tree.delete(*history_tree.get_children())
            for row in repayments:
                repayment_values = (
                    row["occurred_on"], row["source_name"], row["card_name"],
                    minor_to_text(row["amount_minor"], row["minor_digits"], row["currency"]),
                    row["description"],
                )
                if numbers_hidden.get():
                    repayment_values = tuple(
                        _mask_display_numbers(value) for value in repayment_values
                    )
                history_tree.insert(
                    "", "end",
                    values=repayment_values,
                )
            if not cards:
                set_status("还没有登记信用卡；点击“新增信用卡”开始。")

        def open_credit_recovery_dialog() -> None:
            selected_cards = card_tree.selection()
            if not selected_cards:
                messagebox.showinfo("先选择信用卡", "请先在上方选中要恢复的信用卡。", parent=dialog)
                return
            account_id = int(selected_cards[0])
            card_name = card_names_by_id.get(account_id, "")
            if not card_name:
                messagebox.showerror("信用卡信息已更新", "请刷新列表后再操作。", parent=dialog)
                return
            recovery_dialog = tk.Toplevel(dialog)
            recovery_dialog.title(f"{card_name}：恢复额度快照")
            recovery_dialog.geometry("980x720")
            recovery_dialog.minsize(820, 620)
            recovery_dialog.transient(dialog)
            recovery_dialog.grab_set()
            body = ttk.Frame(recovery_dialog, style="App.TFrame", padding=12)
            body.pack(fill="both", expand=True)
            body.columnconfigure(0, weight=1)
            body.rowconfigure(3, weight=1)
            body.rowconfigure(5, weight=1)
            ttk.Label(body, text=f"{card_name}：恢复额度快照", style="ManagementTitle.TLabel").grid(
                row=0, column=0, sticky="w"
            )
            ttk.Label(
                body,
                text="信用卡每笔流水后会自动保存额度恢复点。回退快照只移除较新的快照记录并保留账目；撤销流水会先备份账本，再删除选中的信用卡流水。",
                style="Hint.TLabel", wraplength=910,
            ).grid(row=1, column=0, sticky="ew", pady=(4, 10))
            ttk.Label(body, text="额度快照历史", style="ManagementTitle.TLabel").grid(
                row=2, column=0, sticky="nw", pady=(2, 4)
            )
            snapshot_tree = ttk.Treeview(
                body, columns=("date", "type", "limit", "available", "details"),
                show="headings", height=6,
            )
            snapshot_headers = {
                "date": ("日期", 100), "type": ("来源", 120), "limit": ("总额度", 115),
                "available": ("当时可用额度", 135), "details": ("说明", 420),
            }
            for column, (heading, width) in snapshot_headers.items():
                snapshot_tree.heading(column, text=heading)
                snapshot_tree.column(column, width=width, minwidth=75, stretch=column == "details")
            snapshot_tree.grid(row=3, column=0, sticky="nsew")
            snapshot_scroll = ttk.Scrollbar(body, orient="vertical", command=snapshot_tree.yview)
            snapshot_scroll.grid(row=3, column=1, sticky="ns")
            snapshot_tree.configure(yscrollcommand=snapshot_scroll.set)
            ttk.Label(body, text="信用卡流水", style="ManagementTitle.TLabel").grid(
                row=4, column=0, sticky="w", pady=(12, 4)
            )
            transaction_tree = ttk.Treeview(
                body, columns=("date", "kind", "amount", "description"),
                show="headings", height=6,
            )
            transaction_headers = {
                "date": ("日期", 100), "kind": ("类型", 100),
                "amount": ("金额", 125), "description": ("说明", 560),
            }
            for column, (heading, width) in transaction_headers.items():
                transaction_tree.heading(column, text=heading)
                transaction_tree.column(column, width=width, minwidth=75, stretch=column == "description")
            transaction_tree.grid(row=5, column=0, sticky="nsew")
            transaction_scroll = ttk.Scrollbar(body, orient="vertical", command=transaction_tree.yview)
            transaction_scroll.grid(row=5, column=1, sticky="ns")
            transaction_tree.configure(yscrollcommand=transaction_scroll.set)
            recovery_status = tk.StringVar(value="选择一条较早快照可回退后续快照记录；选择一笔流水可单独撤销。")
            ttk.Label(body, textvariable=recovery_status, style="Status.TLabel", wraplength=900).grid(
                row=6, column=0, sticky="ew", pady=(8, 4)
            )
            recovery_actions = ttk.Frame(body, style="App.TFrame")
            recovery_actions.grid(row=7, column=0, sticky="ew", pady=(8, 0))
            snapshot_cache: list[dict[str, Any]] = []

            def refresh_recovery_history() -> None:
                nonlocal snapshot_cache
                database = Database(self.database_path)
                try:
                    database.initialize()
                    account = database.account(card_name)
                    currency_row = database.currency(account["currency"])
                    digits = int(currency_row["minor_digits"])
                    currency_code = str(account["currency"])
                    snapshot_cache = database.credit_snapshot_history(account_id)
                    transactions = database.credit_transaction_history(account_id)
                finally:
                    database.close()
                snapshot_tree.delete(*snapshot_tree.get_children())
                for item in snapshot_cache:
                    if item["snapshot_type"] == "automatic":
                        kind_text = (
                            "流水后自动快照" if item["available_minor"] is not None
                            else "流水后自动记录"
                        )
                    else:
                        kind_text = "手工额度快照"
                    details = item["description"] or item["note"] or "—"
                    snapshot_tree.insert(
                        "", "end", iid=f"{item['snapshot_type']}:{item['id']}",
                        values=(
                            item["snapshot_date"], kind_text,
                            minor_to_text(item["limit_minor"], digits, currency_code)
                            if item["limit_minor"] is not None else "未录入",
                            minor_to_text(item["available_minor"], digits, currency_code)
                            if item["available_minor"] is not None else "未录入",
                            details,
                        ),
                    )
                transaction_tree.delete(*transaction_tree.get_children())
                for item in transactions:
                    if item["kind"] == "expense":
                        kind_text = "消费"
                    elif item["kind"] == "income":
                        kind_text = "退款/收入"
                    else:
                        kind_text = "还款/转账" if item["direction"] == "in" else "转出"
                    transaction_tree.insert(
                        "", "end", iid=str(item["id"]),
                        values=(
                            item["occurred_on"], kind_text,
                            minor_to_text(item["card_amount_minor"], digits, currency_code),
                            item["description"],
                        ),
                    )

            def restore_selected_snapshot() -> None:
                selected = snapshot_tree.selection()
                if not selected:
                    messagebox.showinfo("请选择快照", "请先选中要恢复到的额度快照。", parent=recovery_dialog)
                    return
                snapshot_type, snapshot_id_text = selected[0].split(":", 1)
                selected_index = next(
                    (index for index, item in enumerate(snapshot_cache)
                     if item["snapshot_type"] == snapshot_type and str(item["id"]) == snapshot_id_text),
                    None,
                )
                if selected_index is None:
                    messagebox.showerror("快照已更新", "请刷新后重新选择额度快照。", parent=recovery_dialog)
                    return
                if snapshot_cache[selected_index]["available_minor"] is None:
                    messagebox.showinfo(
                        "没有额度基准",
                        "这笔流水发生时还没有额度快照，无法作为额度恢复基准；可以在下方流水列表中撤销这笔记录。",
                        parent=recovery_dialog,
                    )
                    return
                newer_count = selected_index
                if newer_count <= 0:
                    messagebox.showinfo("无需恢复", "所选快照已经是最新快照。", parent=recovery_dialog)
                    return
                if not messagebox.askyesno(
                    "确认回退额度快照",
                    f"将保留“{snapshot_cache[selected_index]['snapshot_date']}”这条快照和全部账目，移除其后的 {newer_count} 条额度快照记录。继续吗？",
                    parent=recovery_dialog,
                ):
                    return
                database = Database(self.database_path)
                try:
                    database.initialize()
                    backup_path, manual_count, automatic_count = database.restore_credit_snapshot_history(
                        account_id, snapshot_type, int(snapshot_id_text)
                    )
                except LedgerError as exc:
                    messagebox.showerror("无法恢复快照", str(exc), parent=recovery_dialog)
                    return
                finally:
                    database.close()
                self._queue_github_auto_sync()
                refresh_cards()
                refresh_recovery_history()
                status_text = f"额度快照已回退，移除手工快照 {manual_count} 条、自动恢复点 {automatic_count} 条；账目流水保留。"
                recovery_status.set(status_text)
                set_status(f"{card_name}：{status_text} 操作前备份已保存。")

            def undo_selected_transaction() -> None:
                selected = transaction_tree.selection()
                if not selected:
                    messagebox.showinfo("请选择流水", "请先选中要撤销的信用卡流水。", parent=recovery_dialog)
                    return
                transaction_values = transaction_tree.item(selected[0], "values")
                if not messagebox.askyesno(
                    "确认撤销信用卡流水",
                    f"将撤销 {transaction_values[0]} 的“{transaction_values[1]} {transaction_values[2]}｜{transaction_values[3]}”。操作前会自动备份账本。继续吗？",
                    parent=recovery_dialog,
                ):
                    return
                database = Database(self.database_path)
                try:
                    database.initialize()
                    backup_path = database.delete_transaction_with_backup(int(selected[0]))
                except LedgerError as exc:
                    messagebox.showerror("无法撤销流水", str(exc), parent=recovery_dialog)
                    return
                finally:
                    database.close()
                self._queue_github_auto_sync()
                refresh_cards()
                refresh_recovery_history()
                recovery_status.set(f"流水已撤销；相关后续自动额度恢复点已重新计算。账本备份：{backup_path.name}")
                set_status(f"{card_name} 的信用卡流水已撤销；操作前备份为 {backup_path.name}。")

            ttk.Button(
                recovery_actions, text="恢复到所选快照", command=restore_selected_snapshot
            ).pack(side="left")
            ttk.Button(
                recovery_actions, text="撤销所选流水", command=undo_selected_transaction
            ).pack(side="left", padx=(8, 0))
            ttk.Button(
                recovery_actions, text="关闭", command=recovery_dialog.destroy
            ).pack(side="right")
            refresh_recovery_history()

        def open_add_card() -> None:
            add_dialog = tk.Toplevel(dialog)
            add_dialog.title("新增信用卡")
            add_dialog.geometry("560x470")
            add_dialog.minsize(520, 440)
            add_dialog.transient(dialog)
            add_dialog.grab_set()
            form = ttk.Frame(add_dialog, style="App.TFrame", padding=12)
            form.pack(fill="both", expand=True)
            form.columnconfigure(1, weight=1)
            ttk.Label(form, text="新增信用卡", style="ManagementTitle.TLabel").grid(
                row=0, column=0, columnspan=2, sticky="w", pady=(0, 8)
            )
            ttk.Label(
                form,
                text="这里只登记信用卡账户。额度与可用额度需另录快照；未知历史卡债不要猜，期初可填0并标为记录不完整。",
                style="Hint.TLabel", wraplength=460,
            ).grid(row=1, column=0, columnspan=2, sticky="ew", pady=(0, 12))
            name_var = tk.StringVar()
            currency_var = tk.StringVar(value="JPY")
            balance_var = tk.StringVar(value="0")
            date_var = tk.StringVar(value=_today_japan())
            completeness_var = tk.StringVar(value="记录不完整")
            note_var = tk.StringVar(value="真实历史卡债未核实；期初值仅为本账本记录起点")
            fields = (
                ("信用卡名称", ttk.Entry(form, textvariable=name_var)),
                ("币种", ttk.Combobox(form, textvariable=currency_var, values=("JPY", "CNY"), state="readonly")),
                ("期初账面卡债", ttk.Entry(form, textvariable=balance_var)),
                ("期初日期", ttk.Entry(form, textvariable=date_var)),
                ("债务记录状态", ttk.Combobox(form, textvariable=completeness_var, values=("已确认", "记录不完整"), state="readonly")),
                ("备注", ttk.Entry(form, textvariable=note_var)),
            )
            widgets: dict[str, Any] = {}
            for index, (label, widget) in enumerate(fields, start=2):
                ttk.Label(form, text=label, style="Hint.TLabel").grid(
                    row=index, column=0, sticky="w", padx=(0, 12), pady=5
                )
                widget.grid(row=index, column=1, sticky="ew", pady=5)
                widgets[label] = widget

            def save_card() -> None:
                name = name_var.get().strip()
                if not name:
                    messagebox.showwarning("缺少信用卡名称", "请填写信用卡名称。", parent=add_dialog)
                    return
                database = Database(self.database_path)
                try:
                    database.initialize()
                    database.add_account(
                        name=name, account_type="credit", currency=currency_var.get(),
                        opening_balance=balance_var.get().strip(),
                        opening_date=date_var.get().strip(),
                        completeness="known" if completeness_var.get() == "已确认" else "partial",
                        note=note_var.get().strip(),
                    )
                except LedgerError as exc:
                    messagebox.showerror("无法新增信用卡", str(exc), parent=add_dialog)
                    return
                finally:
                    database.close()
                add_dialog.destroy()
                refresh_cards()
                set_status(f"信用卡“{name}”已登记；额度仍需单独录入快照。")

            actions = ttk.Frame(form, style="App.TFrame")
            actions.grid(row=8, column=0, columnspan=2, sticky="ew", pady=(16, 0))
            ttk.Button(actions, text="取消", command=add_dialog.destroy).pack(side="right", padx=(8, 0))
            ttk.Button(actions, text="保存信用卡", style="Send.TButton", command=save_card).pack(side="right")
            widgets["信用卡名称"].focus_set()

        def open_limit_snapshot() -> None:
            add_dialog = tk.Toplevel(dialog)
            add_dialog.title("录入信用卡额度")
            add_dialog.geometry("560x440")
            add_dialog.minsize(520, 420)
            add_dialog.transient(dialog)
            add_dialog.grab_set()
            form = ttk.Frame(add_dialog, style="App.TFrame", padding=12)
            form.pack(fill="both", expand=True)
            form.columnconfigure(1, weight=1)
            ttk.Label(form, text="录入额度快照", style="ManagementTitle.TLabel").grid(
                row=0, column=0, columnspan=2, sticky="w", pady=(0, 8)
            )
            ttk.Label(
                form,
                text="按信用卡应用当前显示值录入。每张卡每天只保存一条快照；当前欠款估算将按总额度减可用额度计算，不等于当月账单。",
                style="Hint.TLabel", wraplength=460,
            ).grid(row=1, column=0, columnspan=2, sticky="ew", pady=(0, 12))
            database = Database(self.database_path)
            try:
                database.initialize()
                card_rows = database.connection.execute(
                    "SELECT name,currency FROM accounts WHERE account_type='credit' ORDER BY name"
                ).fetchall()
            finally:
                database.close()
            names = [row["name"] for row in card_rows]
            currency_by_name = {row["name"]: row["currency"] for row in card_rows}
            card_var = tk.StringVar()
            date_var = tk.StringVar(value=_today_japan())
            limit_var = tk.StringVar()
            available_var = tk.StringVar()
            note_var = tk.StringVar()
            fields = (
                ("信用卡", ttk.Combobox(form, textvariable=card_var, values=names, state="readonly")),
                ("快照日期", ttk.Entry(form, textvariable=date_var)),
                ("总额度", ttk.Entry(form, textvariable=limit_var)),
                ("当前可用额度", ttk.Entry(form, textvariable=available_var)),
                ("备注", ttk.Entry(form, textvariable=note_var)),
            )
            widgets: dict[str, Any] = {}
            for index, (label, widget) in enumerate(fields, start=2):
                ttk.Label(form, text=label, style="Hint.TLabel").grid(
                    row=index, column=0, sticky="w", padx=(0, 12), pady=5
                )
                widget.grid(row=index, column=1, sticky="ew", pady=5)
                widgets[label] = widget
            unit_var = tk.StringVar(value="金额单位：请选择信用卡")
            ttk.Label(form, textvariable=unit_var, style="Hint.TLabel").grid(
                row=7, column=1, sticky="w", pady=(0, 4)
            )
            card_box = widgets["信用卡"]

            def update_snapshot_unit(*_args: Any) -> None:
                code = currency_by_name.get(card_var.get())
                unit_var.set(f"金额单位：{code}" if code else "金额单位：请选择信用卡")

            card_var.trace_add("write", update_snapshot_unit)

            def save_snapshot() -> None:
                name = card_var.get()
                if not name:
                    messagebox.showwarning("请选择信用卡", "请先选择要记录额度的信用卡。", parent=add_dialog)
                    return
                database = Database(self.database_path)
                try:
                    database.initialize()
                    database.add_credit_limit_snapshot(
                        account_name=name,
                        snapshot_date=date_var.get().strip(),
                        limit=limit_var.get().strip(),
                        available=available_var.get().strip(),
                        note=note_var.get().strip(),
                    )
                except LedgerError as exc:
                    messagebox.showerror("无法保存额度", str(exc), parent=add_dialog)
                    return
                finally:
                    database.close()
                add_dialog.destroy()
                refresh_cards()
                set_status(f"“{name}”的额度快照已保存；消费、退款和还款会调整可用额度，并更新当前欠款估算。")
                self._queue_github_auto_sync()

            actions = ttk.Frame(form, style="App.TFrame")
            actions.grid(row=8, column=0, columnspan=2, sticky="ew", pady=(16, 0))
            ttk.Button(actions, text="取消", command=add_dialog.destroy).pack(side="right", padx=(8, 0))
            ttk.Button(actions, text="保存快照", style="Send.TButton", command=save_snapshot).pack(side="right")
            if names:
                card_box.current(0)
            else:
                set_status("没有信用卡账户；请先点击“新增信用卡”。")
                card_box.configure(state="disabled")

        def open_repayment_schedule_dialog() -> None:
            add_dialog = tk.Toplevel(dialog)
            add_dialog.title("每月应还计划")
            add_dialog.geometry("650x540")
            add_dialog.minsize(590, 500)
            add_dialog.transient(dialog)
            add_dialog.grab_set()
            form = ttk.Frame(add_dialog, style="App.TFrame", padding=12)
            form.pack(fill="both", expand=True)
            form.columnconfigure(1, weight=1)
            ttk.Label(form, text="设置每月应还计划", style="ManagementTitle.TLabel").grid(
                row=0, column=0, columnspan=2, sticky="w", pady=(0, 8)
            )
            ttk.Label(
                form,
                text="信用卡、扣款账户和还款日按月固定；本期金额需要每个月重新填写，留空就不会自动记账，也不会沿用上个月金额。到期日当天程序运行且余额足够时，只在本地账本记转账，不会从银行实际扣款。错过日期或已有部分还款时不会自动补记。",
                style="Hint.TLabel", wraplength=540,
            ).grid(row=1, column=0, columnspan=2, sticky="ew", pady=(0, 12))
            database = Database(self.database_path)
            try:
                database.initialize()
                card_rows = database.connection.execute(
                    "SELECT name,currency FROM accounts WHERE account_type='credit' ORDER BY name"
                ).fetchall()
                source_rows = database.connection.execute(
                    "SELECT name,currency FROM accounts WHERE account_type IN ('bank','wallet','prepaid','transit') ORDER BY name"
                ).fetchall()
                schedule_rows = database.connection.execute(
                    "SELECT r.*,card.name AS card_name,source.name AS source_name, "
                    "CASE WHEN p.status='pending' THEN p.amount_minor END AS amount_minor "
                    "FROM credit_repayment_rules r JOIN accounts card ON card.id=r.card_account_id "
                    "JOIN accounts source ON source.id=r.source_account_id "
                    "LEFT JOIN credit_repayment_periods p ON p.rule_id=r.id AND p.due_date=r.next_due_date"
                ).fetchall()
            finally:
                database.close()
            card_currency = {row["name"]: row["currency"] for row in card_rows}
            source_currency = {row["name"]: row["currency"] for row in source_rows}
            schedules_by_card = {row["card_name"]: dict(row) for row in schedule_rows}
            card_var = tk.StringVar()
            source_var = tk.StringVar()
            amount_var = tk.StringVar()
            amount_month_var = tk.StringVar()
            due_var = tk.StringVar(value=next_month_due_date(_today_japan()))
            updating_schedule_fields = False
            card_box = ttk.Combobox(form, textvariable=card_var, values=tuple(card_currency), state="readonly")
            source_box = ttk.Combobox(form, textvariable=source_var, values=(), state="readonly")
            fields = (
                ("信用卡", card_box),
                ("扣款账户", source_box),
                ("本期应还金额（每月重新填写）", ttk.Entry(form, textvariable=amount_var)),
                ("下次还款日（以后每月同日）", ttk.Entry(form, textvariable=due_var)),
            )
            for index, (label, widget) in enumerate(fields, start=2):
                ttk.Label(form, text=label, style="Hint.TLabel").grid(
                    row=index, column=0, sticky="w", padx=(0, 12), pady=6
                )
                widget.grid(row=index, column=1, sticky="ew", pady=6)
            unit_var = tk.StringVar(value="请先选择信用卡与扣款账户")
            ttk.Label(form, textvariable=unit_var, style="Hint.TLabel").grid(
                row=6, column=1, sticky="w", pady=(2, 4)
            )

            def update_schedule_fields(*_args: Any) -> None:
                nonlocal updating_schedule_fields
                updating_schedule_fields = True
                card_name = card_var.get()
                code = card_currency.get(card_name)
                compatible = [name for name, source_code in source_currency.items() if source_code == code]
                source_box.configure(values=compatible)
                schedule = schedules_by_card.get(card_name)
                if schedule:
                    source_var.set(schedule["source_name"] if schedule["source_name"] in compatible else "")
                    if schedule["amount_minor"] is not None:
                        amount_text = minor_to_text(schedule["amount_minor"], 2 if code == "CNY" else 0, code)
                        amount_var.set(amount_text.removesuffix(f" {code}").replace(",", ""))
                    else:
                        amount_var.set("")
                    saved_due_date = schedule["next_due_date"]
                    due_var.set(
                        saved_due_date if saved_due_date >= _today_japan()
                        else next_month_due_date(_today_japan(), int(schedule["due_day"]))
                    )
                else:
                    source_var.set("")
                    amount_var.set("")
                    due_var.set(next_month_due_date(_today_japan()))
                unit_var.set(
                    f"金额单位：{code}。本期金额只用于当前显示的下次还款日，不会复制到下个月。"
                    if code else "请先选择信用卡与扣款账户"
                )
                try:
                    amount_month_var.set(parse_date(due_var.get().strip()).strftime("%Y-%m"))
                except (LedgerError, ValueError):
                    amount_month_var.set("")
                updating_schedule_fields = False

            def clear_amount_when_due_month_changes(*_args: Any) -> None:
                try:
                    due_month = parse_date(due_var.get().strip()).strftime("%Y-%m")
                except (LedgerError, ValueError):
                    return
                if (
                    not updating_schedule_fields
                    and amount_month_var.get()
                    and due_month != amount_month_var.get()
                ):
                    amount_var.set("")
                    amount_month_var.set(due_month)

            card_var.trace_add("write", update_schedule_fields)
            due_var.trace_add("write", clear_amount_when_due_month_changes)

            def save_schedule() -> None:
                if not card_var.get() or not source_var.get():
                    messagebox.showwarning("账户不完整", "请选择信用卡与扣款账户。", parent=add_dialog)
                    return
                database = Database(self.database_path)
                try:
                    database.initialize()
                    save_credit_repayment_schedule(
                        database,
                        card_name=card_var.get(),
                        source_account_name=source_var.get(),
                        first_due_date=due_var.get().strip(),
                        amount=amount_var.get().strip() or None,
                    )
                except LedgerError as exc:
                    messagebox.showerror("无法保存每月应还计划", str(exc), parent=add_dialog)
                    return
                finally:
                    database.close()
                add_dialog.destroy()
                refresh_cards()
                set_status(
                    f"已保存“{card_var.get()}”的扣款账户和还款日；本期金额按本月填写，未填写就不会自动记账。"
                )

            def toggle_schedule() -> None:
                card_name = card_var.get()
                schedule = schedules_by_card.get(card_name)
                if not schedule:
                    messagebox.showinfo("尚无还款计划", "该卡尚未保存每月应还计划。", parent=add_dialog)
                    return
                enabled = not bool(schedule["enabled"])
                database = Database(self.database_path)
                try:
                    database.initialize()
                    set_credit_repayment_schedule_enabled(database, card_name=card_name, enabled=enabled)
                except LedgerError as exc:
                    messagebox.showerror("无法更新计划", str(exc), parent=add_dialog)
                    return
                finally:
                    database.close()
                add_dialog.destroy()
                refresh_cards()
                set_status(f"“{card_name}”每月应还计划已{'恢复' if enabled else '暂停'}。")

            actions = ttk.Frame(form, style="App.TFrame")
            actions.grid(row=7, column=0, columnspan=2, sticky="ew", pady=(18, 0))
            ttk.Button(actions, text="取消", command=add_dialog.destroy).pack(side="right", padx=(8, 0))
            ttk.Button(actions, text="暂停/恢复计划", command=toggle_schedule).pack(side="right", padx=(8, 0))
            ttk.Button(actions, text="保存计划", style="Send.TButton", command=save_schedule).pack(side="right")
            selected = card_tree.selection()
            selected_name = card_names_by_id.get(int(selected[0]), "") if selected else ""
            if selected_name in card_currency:
                card_var.set(selected_name)
            elif card_currency:
                card_box.current(0)
            else:
                card_box.configure(state="disabled")
                set_status("没有信用卡账户；请先点击“新增信用卡”。")

        def open_repayment_dialog() -> None:
            add_dialog = tk.Toplevel(dialog)
            add_dialog.title("记录信用卡还款")
            add_dialog.geometry("600x470")
            add_dialog.minsize(540, 440)
            add_dialog.transient(dialog)
            add_dialog.grab_set()
            form = ttk.Frame(add_dialog, style="App.TFrame", padding=12)
            form.pack(fill="both", expand=True)
            form.columnconfigure(1, weight=1)
            ttk.Label(form, text="记录信用卡还款", style="ManagementTitle.TLabel").grid(
                row=0, column=0, columnspan=2, sticky="w", pady=(0, 8)
            )
            ttk.Label(
                form,
                text="还款需要明确选择转出账户和信用卡。提交后只记账户间转账，不增加消费；额度快照仍以你重新录入的卡片应用数值为准。",
                style="Hint.TLabel", wraplength=500,
            ).grid(row=1, column=0, columnspan=2, sticky="ew", pady=(0, 12))
            database = Database(self.database_path)
            try:
                database.initialize()
                card_rows = database.connection.execute(
                    "SELECT name,currency FROM accounts WHERE account_type='credit' ORDER BY name"
                ).fetchall()
                source_rows = database.connection.execute(
                    "SELECT name,currency,account_type FROM accounts "
                    "WHERE account_type IN ('bank','wallet','prepaid','transit') ORDER BY name"
                ).fetchall()
            finally:
                database.close()
            card_currency = {row["name"]: row["currency"] for row in card_rows}
            source_currency = {row["name"]: row["currency"] for row in source_rows}
            card_var = tk.StringVar()
            source_var = tk.StringVar()
            date_var = tk.StringVar(value=_today_japan())
            amount_var = tk.StringVar()
            description_var = tk.StringVar(value="信用卡还款")
            card_box = ttk.Combobox(
                form, textvariable=card_var, values=tuple(card_currency), state="readonly"
            )
            source_box = ttk.Combobox(form, textvariable=source_var, values=(), state="readonly")
            fields = (
                ("信用卡", card_box),
                ("转出账户", source_box),
                ("还款日期", ttk.Entry(form, textvariable=date_var)),
                ("还款金额", ttk.Entry(form, textvariable=amount_var)),
                ("备注", ttk.Entry(form, textvariable=description_var)),
            )
            widgets: dict[str, Any] = {}
            for index, (label, widget) in enumerate(fields, start=2):
                ttk.Label(form, text=label, style="Hint.TLabel").grid(
                    row=index, column=0, sticky="w", padx=(0, 12), pady=5
                )
                widget.grid(row=index, column=1, sticky="ew", pady=5)
                widgets[label] = widget
            unit_var = tk.StringVar(value="请先选择信用卡与转出账户")
            ttk.Label(form, textvariable=unit_var, style="Hint.TLabel").grid(
                row=7, column=1, sticky="w", pady=(0, 4)
            )

            def update_repayment_sources(*_args: Any) -> None:
                code = card_currency.get(card_var.get())
                compatible = [name for name, source_code in source_currency.items() if source_code == code]
                source_box.configure(values=compatible)
                if source_var.get() not in compatible:
                    source_var.set("")
                unit_var.set(f"还款金额单位：{code}；转出账户需同币种" if code else "请先选择信用卡与转出账户")

            card_var.trace_add("write", update_repayment_sources)

            def save_repayment() -> None:
                card_name = card_var.get()
                source_name = source_var.get()
                if not card_name or not source_name:
                    messagebox.showwarning("账户不完整", "请选择信用卡和转出账户。", parent=add_dialog)
                    return
                database = Database(self.database_path)
                try:
                    database.initialize()
                    transaction_id = record_credit_card_repayment(
                        database,
                        card_name=card_name,
                        source_account_name=source_name,
                        amount=amount_var.get().strip(),
                        occurred_on=date_var.get().strip(),
                        description=description_var.get().strip(),
                    )
                except LedgerError as exc:
                    messagebox.showerror("无法记录还款", str(exc), parent=add_dialog)
                    return
                finally:
                    database.close()
                add_dialog.destroy()
                refresh_cards()
                set_status(
                    f"还款 #{transaction_id} 已记为 {source_name} → {card_name} 转账；"
                    "可用额度已按记录更新，未另记消费。若还没有额度快照，仍需先录入快照。"
                )
                self._queue_github_auto_sync()

            actions = ttk.Frame(form, style="App.TFrame")
            actions.grid(row=8, column=0, columnspan=2, sticky="ew", pady=(16, 0))
            ttk.Button(actions, text="取消", command=add_dialog.destroy).pack(side="right", padx=(8, 0))
            ttk.Button(actions, text="保存还款", style="Send.TButton", command=save_repayment).pack(side="right")
            if card_currency:
                card_box.current(0)
            else:
                card_box.configure(state="disabled")
                set_status("没有信用卡账户；请先点击“新增信用卡”。")

        ttk.Button(controls, text="＋ 新增信用卡", command=open_add_card).pack(side="left")
        ttk.Button(controls, text="录入额度快照", command=open_limit_snapshot).pack(side="left", padx=(8, 0))
        ttk.Button(controls, text="恢复额度快照", command=open_credit_recovery_dialog).pack(side="left", padx=(8, 0))
        ttk.Button(controls, text="记录还款", command=open_repayment_dialog).pack(side="left", padx=(8, 0))
        ttk.Button(controls, text="每月应还计划", command=open_repayment_schedule_dialog).pack(side="left", padx=(8, 0))
        number_visibility_button = ttk.Button(
            controls, text="显示数字" if numbers_hidden.get() else "隐藏数字", command=lambda: toggle_number_visibility()
        )
        number_visibility_button.pack(side="right")

        def toggle_number_visibility() -> None:
            numbers_hidden.set(not numbers_hidden.get())
            number_visibility_button.configure(
                text="显示数字" if numbers_hidden.get() else "隐藏数字"
            )
            set_status(status_message)
            refresh_cards()

        if container is None:
            ttk.Button(buttons, text="关闭", command=dialog.destroy).pack(side="right")
        wrap_management_toolbar(controls)
        refresh_cards()

    def _append_message(
        self, speaker: str, body: str, *, agent_mode: str | None = None
    ) -> None:
        target_mode = agent_mode or self.agent_mode
        self.agent_states[target_mode]["messages"].append((speaker, body))
        if target_mode != self.agent_mode:
            return
        tag = "user" if speaker == "你" else "assistant"
        display_speaker = translate(speaker)
        display_body = translate(body) if body in {
            "你好，直接告诉我一笔收入、消费、转账或还款。信息不够时我会先追问，确认后才写入本地账本。",
            "我会先检索本地近期饮食记录，再交给饮食健康 Agent 单独配置的模型和 Skill 给出均衡饮食建议。记录不足时会说明限制；此模式不会修改记录。",
        } else body
        separator = ": " if current_language() == "en-US" else "："
        self.transcript.configure(state="normal")
        self.transcript.insert("end", f"{display_speaker}{separator}", tag)
        self.transcript.insert("end", f"{display_body}\n\n", tag+"_body")
        self.transcript.see("end")
        self.transcript.configure(state="disabled")

    def choose_images(self) -> None:
        paths = filedialog.askopenfilenames(
            parent=self.root,
            title="选择食物或收据图片",
            filetypes=[
                ("支持的图片", "*.jpg *.jpeg *.png *.webp"),
                ("JPEG 图片", "*.jpg *.jpeg"),
                ("PNG 图片", "*.png"),
                ("WebP 图片", "*.webp"),
            ],
        )
        if paths:
            self._add_image_files(paths)

    def _archive_receipt_attachments(
        self,
        attachments: list[ImageAttachment],
    ) -> list[Path]:
        if not attachments:
            return []
        file_paths: list[Path] = []
        try:
            archive_directory = self.database_path.parent / "receipt_images"
            for attachment in attachments:
                file_paths.append(archive_receipt_image(attachment, archive_directory))
            return file_paths
        except Exception:
            for path in file_paths:
                try:
                    path.unlink(missing_ok=True)
                except OSError:
                    pass
            raise

    def _discard_receipt_image_archive(
        self,
        file_paths: list[Path],
    ) -> None:
        for path in file_paths:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass

    def _handle_image_drop(self, event: Any) -> str:
        try:
            paths = self.root.tk.splitlist(event.data)
        except tk.TclError:
            messagebox.showwarning("无法读取拖入文件", "请把 JPG、PNG 或 WebP 图片拖入输入框。", parent=self.root)
            return "break"
        self._add_image_files(paths)
        return "copy"

    def _add_image_files(self, paths: Any) -> None:
        errors: list[str] = []
        for path in paths:
            if len(self.image_attachments) >= MAX_IMAGE_ATTACHMENTS:
                errors.append(f"最多可附加{MAX_IMAGE_ATTACHMENTS}张图片。")
                break
            try:
                attachment = load_image_attachment(path)
                if any(existing.data == attachment.data for existing in self.image_attachments):
                    continue
                total_size = sum(len(existing.data) for existing in self.image_attachments)
                if total_size + len(attachment.data) > MAX_TOTAL_IMAGE_BYTES:
                    errors.append("图片总大小超过24 MB，请减少图片数量或压缩图片。")
                    break
                self.image_attachments.append(attachment)
            except NaturalLanguageError as exc:
                errors.append(str(exc))
        self._refresh_image_attachments()
        if errors:
            messagebox.showwarning("部分图片未添加", "\n".join(errors), parent=self.root)
        elif self.image_attachments:
            if Image is None:
                self.status.configure(
                    text=f"已附加{len(self.image_attachments)}张图片；当前未安装 Pillow，图片将按原样发送。"
                )
            else:
                self.status.configure(
                    text=f"已附加{len(self.image_attachments)}张图片；方向已校正并保留文字细节，原图不变。"
                )

    def _remove_image_attachment(self, index: int) -> None:
        if 0 <= index < len(self.image_attachments):
            del self.image_attachments[index]
            self._refresh_image_attachments()

    def _refresh_image_attachments(self) -> None:
        for child in self.attachments_frame.winfo_children():
            child.destroy()
        self._image_preview_refs.clear()
        if not self.image_attachments:
            if self.drag_drop_enabled:
                hint = "可拖入 JPG/PNG/WebP 图片到输入框或附件栏"
            elif DND_FILES is None:
                hint = "拖放依赖未安装；请点击添加图片"
            else:
                hint = "拖放初始化失败；请点击添加图片"
            self.attachment_hint.configure(text=hint)
            return
        self.attachment_hint.configure(text=f"已附加 {len(self.image_attachments)} 张：")
        for index, attachment in enumerate(self.image_attachments):
            chip = ttk.Frame(self.attachments_frame, style="App.TFrame", relief="solid", borderwidth=1)
            chip.pack(side="left", padx=(0, 6))
            if Image is not None and ImageTk is not None:
                try:
                    with Image.open(BytesIO(attachment.data)) as source_image:
                        preview = source_image.copy()
                    preview.thumbnail((44, 44))
                    preview_photo = ImageTk.PhotoImage(preview)
                    self._image_preview_refs.append(preview_photo)
                    ttk.Label(chip, image=preview_photo).pack(side="left", padx=(4, 2), pady=3)
                except Exception:
                    pass
            display_name = attachment.name
            if len(display_name) > 24:
                display_name = display_name[:11] + "…" + display_name[-10:]
            ttk.Label(chip, text=display_name).pack(side="left", padx=(4, 2), pady=3)
            ttk.Button(
                chip,
                text="×",
                width=2,
                command=lambda item_index=index: self._remove_image_attachment(item_index),
            ).pack(side="left", padx=(0, 3), pady=2)

    def _get_client(self, *, has_images: bool = False) -> OpenAICompatibleClient | None:
        profile = self._agent_api_profile(has_images=has_images)
        cache_key = (self.agent_mode, has_images, str(profile.get("id", "")))
        cached_client = self.clients.get(cache_key)
        if cached_client is not None:
            return cached_client
        api_url = profile["api_url"].strip()
        model = profile["model"].strip()
        api_key = profile["api_key"].strip()
        if not api_url or not model:
            self.status.configure(text="当前 API 服务的接口地址或模型名未填写，请先完成设置。")
            self.active_api_profile_id = profile["id"]
            self.open_settings()
            profile = self._agent_api_profile(has_images=has_images)
            api_url = profile["api_url"].strip()
            model = profile["model"].strip()
            api_key = profile["api_key"].strip()
        if not api_url or not model:
            self.status.configure(text="API 服务未配置完整；请填写接口地址和模型名后再试。")
            return None
        if not api_key.strip() and not is_local_http_api(api_url):
            self.status.configure(text="当前服务需要 API Key；请先填写并保存。")
            self.active_api_profile_id = profile["id"]
            self.open_settings()
            profile = self._agent_api_profile(has_images=has_images)
            api_url = profile["api_url"].strip()
            model = profile["model"].strip()
            api_key = profile["api_key"].strip()
        if not api_key.strip() and not is_local_http_api(api_url):
            self.status.configure(text="尚未配置 API Key；本次没有发送请求。")
            return None
        profile = self._agent_api_profile(has_images=has_images)
        cache_key = (self.agent_mode, has_images, str(profile.get("id", "")))
        try:
            client = OpenAICompatibleClient(
                api_key,
                api_url=api_url,
                model=model,
                thinking_enabled=profile.get("thinking_enabled", False),
                reasoning_effort=profile.get("reasoning_effort", "low"),
                timeout=(
                    LOCAL_OLLAMA_REQUEST_TIMEOUT_SECONDS
                    if is_local_http_api(api_url)
                    else REQUEST_TIMEOUT_SECONDS
                ),
            )
        except NaturalLanguageError as exc:
            messagebox.showerror("API 配置错误", str(exc), parent=self.root)
            return None
        self.clients[cache_key] = client
        return client

    def _active_api_profile(self) -> dict[str, Any]:
        for profile in self.api_profiles:
            if profile["id"] == self.active_api_profile_id:
                return profile
        self.active_api_profile_id = self.api_profiles[0]["id"]
        return self.api_profiles[0]

    def _agent_api_profile(
        self,
        mode: str | None = None,
        *,
        has_images: bool = False,
    ) -> dict[str, Any]:
        agent = mode or self.agent_mode
        workflow_profile_id = self.agent_states.get(agent, {}).get("workflow_profile_id")
        if workflow_profile_id:
            for profile in self.api_profiles:
                if profile["id"] == workflow_profile_id:
                    return profile
        profile_id = (
            self.agent_vision_profile_ids.get(agent, self.agent_profile_ids.get(agent, ""))
            if has_images
            else self.agent_profile_ids.get(agent, "")
        )
        for profile in self.api_profiles:
            if profile["id"] == profile_id:
                return profile
        return self._active_api_profile()

    def _pending_workflow_message(self) -> str:
        profile_id = self.agent_states.get(self.agent_mode, {}).get("workflow_profile_id")
        profile = next(
            (item for item in self.api_profiles if item.get("id") == profile_id),
            self._agent_api_profile(),
        )
        return translate(
            "当前记账尚未完成，后续消息继续使用 {service}（{model}）。确认或取消后才能切换 Agent 或 API 服务。",
            self.language,
        ).format(service=profile.get("name", "API"), model=profile.get("model", ""))

    def _clear_agent_clients(self, mode: str | None = None) -> None:
        if mode is None:
            self.clients.clear()
            return
        for cache_key in tuple(self.clients):
            if cache_key[0] == mode:
                del self.clients[cache_key]

    def open_settings(self, initial_page: str = "API 服务") -> None:
        if self.busy:
            messagebox.showinfo("正在等待 API", "当前请求完成后再切换 API 服务。", parent=self.root)
            return
        if self.pending_state is not None:
            messagebox.showinfo(
                translate("记账尚未完成", self.language),
                self._pending_workflow_message(),
                parent=self.root,
            )
            return
        dialog = tk.Toplevel(self.root)
        dialog.title("设置")
        settings_width = min(920, max(760, dialog.winfo_screenwidth() - 80))
        settings_height = min(640, max(520, dialog.winfo_screenheight() - 80))
        dialog.geometry(f"{settings_width}x{settings_height}")
        dialog.minsize(min(840, settings_width), min(560, settings_height))
        dialog.resizable(True, True)
        dialog.transient(self.root)
        dialog.configure(bg=color("#f2f4f7"))

        style = ttk.Style(dialog)
        style.configure("SettingsPanel.TFrame", background=color("#ffffff"))
        style.configure("SettingsTitle.TLabel", background=color("#ffffff"), foreground=color("#101828"), font=(self.ui_font_family, 17, "bold"))
        style.configure("SettingsSection.TLabel", background=color("#ffffff"), foreground=color("#344054"), font=(self.ui_font_family, 11, "bold"))
        style.configure("SettingsPath.TLabel", background=color("#ffffff"), foreground=color("#475467"), font=(self.ui_font_family, 10))
        style.configure("SettingsHint.TLabel", background=color("#ffffff"), foreground=color("#667085"), font=(self.ui_font_family, 10))
        style.configure("SettingsStatus.TLabel", background=color("#ffffff"), foreground=color("#175cd3"), font=(self.ui_font_family, 10, "bold"))

        shell = tk.Frame(dialog, bg=color("#f2f4f7"))
        shell.pack(fill="both", expand=True)
        sidebar = tk.Frame(shell, bg=color("#ffffff"), width=210, highlightbackground=color("#e4e7ec"), highlightthickness=1)
        sidebar.pack(side="left", fill="y")
        sidebar.pack_propagate(False)
        content = tk.Frame(shell, bg=color("#f2f4f7"))
        content.pack(side="left", fill="both", expand=True)
        content.columnconfigure(0, weight=1)
        content.rowconfigure(0, weight=1)
        page_canvas = tk.Canvas(content, bg=color("#f2f4f7"), highlightthickness=0, borderwidth=0)
        page_scrollbar = ttk.Scrollbar(content, orient="vertical", command=page_canvas.yview)
        page_canvas.configure(yscrollcommand=page_scrollbar.set)
        page_canvas.grid(row=0, column=0, sticky="nsew")
        page_scrollbar.grid(row=0, column=1, sticky="ns")
        footer = tk.Frame(content, bg=color("#f2f4f7"))
        footer.grid(row=1, column=0, columnspan=2, sticky="ew", padx=14, pady=(0, 14))
        pages_host = tk.Frame(page_canvas, bg=color("#f2f4f7"))
        pages_window = page_canvas.create_window((0, 0), window=pages_host, anchor="nw")

        def refresh_page_scrollregion(_event: Any = None) -> None:
            callback = lambda: page_canvas.configure(scrollregion=page_canvas.bbox("all"))
            if defer_during_interactive_resize(
                    page_canvas, (page_canvas, "scrollregion"), callback):
                return
            callback()

        def resize_pages_host(event: Any) -> None:
            def apply_resize(width):
                if not page_canvas.winfo_exists():
                    return
                page_canvas.itemconfigure(pages_window, width=width)
                # Keep descriptive text inside the narrower content panel rather
                # than allowing fixed wrap widths to push fields off screen.
                available = max(220, width - 68)
                def wrap_descriptions(widget: Any) -> None:
                    for child in widget.winfo_children():
                        if isinstance(child, (tk.Label, ttk.Label)):
                            try:
                                if float(child.cget("wraplength") or 0) > 0:
                                    child.configure(wraplength=available)
                            except (tk.TclError, ValueError):
                                pass
                        wrap_descriptions(child)
                wrap_descriptions(pages_host)
                page_canvas.after_idle(refresh_page_scrollregion)
            callback = lambda width=event.width: apply_resize(width)
            if defer_during_interactive_resize(page_canvas, (page_canvas, "settings-width"), callback):
                return
            callback()

        pages_host.bind("<Configure>", refresh_page_scrollregion)
        page_canvas.bind("<Configure>", resize_pages_host)

        tk.Label(sidebar, text="⚙  设置", bg=color("#ffffff"), fg=color("#101828"), font=(self.ui_font_family, 16, "bold"), anchor="w").pack(fill="x", padx=21, pady=(14, 2))
        tk.Label(sidebar, text="管理服务、解析和数据", bg=color("#ffffff"), fg=color("#667085"), font=(self.ui_font_family, 10), anchor="w").pack(fill="x", padx=22, pady=(0, 12))
        tk.Label(sidebar, text="服务与解析", bg=color("#ffffff"), fg=color("#98a2b3"), font=(self.ui_font_family, 9, "bold"), anchor="w").pack(fill="x", padx=17, pady=(0, 5))

        api_page = tk.Frame(pages_host, bg=color("#f2f4f7"))
        agent_skill_page = tk.Frame(pages_host, bg=color("#f2f4f7"))
        appearance_page = tk.Frame(pages_host, bg=color("#f2f4f7"))
        language_page = tk.Frame(pages_host, bg=color("#f2f4f7"))
        category_page = tk.Frame(pages_host, bg=color("#f2f4f7"))
        data_page = tk.Frame(pages_host, bg=color("#f2f4f7"))
        pages = {
            "API 服务": api_page,
            "Agent 配置与 Skill": agent_skill_page,
            "外观": appearance_page,
            "语言": language_page,
            "记账类别": category_page,
            "账本与备份": data_page,
        }
        nav_buttons: dict[str, tuple[tk.Frame, tk.Label, tk.Label]] = {}
        page_descriptions = {
            "API 服务": "管理可供两个 Agent 选择的模型连接",
            "Agent 配置与 Skill": "统一管理 Agent 模型与 Skill",
            "外观": "浅色、深色或跟随系统",
            "语言": "选择软件界面显示语言",
            "记账类别": "管理记账 Agent 可使用的收入和支出类别",
            "账本与备份": "查看数据位置并创建备份",
        }

        def show_settings_page(name: str) -> None:
            for page in pages.values():
                page.pack_forget()
            pages[name].pack(fill="both", expand=True, padx=14, pady=14)
            page_canvas.yview_moveto(0)
            for key, (button, title_label, description_label) in nav_buttons.items():
                selected = key == name
                background = color("#eff4ff") if selected else color("#ffffff")
                button.configure(bg=background)
                title_label.configure(bg=background, fg=color("#1849a9") if selected else color("#344054"))
                description_label.configure(bg=background, fg=color("#475467") if selected else color("#667085"))
            if name == "Agent 配置与 Skill":
                refresh_agent_settings_page()
            if name == "记账类别":
                refresh_category_table()

        for name, description in page_descriptions.items():
            if name == "外观":
                tk.Label(
                    sidebar,
                    text="显示设置",
                    bg=color("#ffffff"),
                    fg=color("#98a2b3"),
                    font=(self.ui_font_family, 9, "bold"),
                    anchor="w",
                ).pack(fill="x", padx=17, pady=(10, 5))
            if name == "账本与备份":
                tk.Label(
                    sidebar,
                    text="数据管理",
                    bg=color("#ffffff"),
                    fg=color("#98a2b3"),
                    font=(self.ui_font_family, 9, "bold"),
                    anchor="w",
                ).pack(fill="x", padx=17, pady=(10, 5))
            if name == "记账类别":
                tk.Label(
                    sidebar,
                    text="记账设置",
                    bg=color("#ffffff"),
                    fg=color("#98a2b3"),
                    font=(self.ui_font_family, 9, "bold"),
                    anchor="w",
                ).pack(fill="x", padx=17, pady=(10, 5))
            nav = tk.Frame(sidebar, bg=color("#ffffff"), cursor="hand2")
            nav.pack(fill="x", padx=10, pady=2)
            nav_title = tk.Label(
                nav,
                text=f"{name}   ›",
                bg=color("#ffffff"),
                fg=color("#344054"),
                font=(self.ui_font_family, 10, "bold"),
                anchor="w",
                cursor="hand2",
            )
            nav_title.pack(fill="x", padx=12, pady=(6, 0))
            nav_description = tk.Label(
                nav,
                text=description,
                wraplength=176,
                justify="left",
                bg=color("#ffffff"),
                fg=color("#667085"),
                font=(self.ui_font_family, 9),
                anchor="w",
                cursor="hand2",
            )
            nav_description.pack(fill="x", padx=12, pady=(1, 6))
            for widget in (nav, nav_title, nav_description):
                widget.bind("<Button-1>", lambda _event, selected=name: show_settings_page(selected))
            nav_buttons[name] = (nav, nav_title, nav_description)

        panel = ttk.Frame(api_page, style="SettingsPanel.TFrame", padding=18)
        panel.pack(fill="both", expand=True)
        panel.columnconfigure(0, weight=1)
        ttk.Label(panel, text="API 服务", style="SettingsTitle.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(
            panel,
            text="管理可复用的本机 Ollama 或 OpenAI 兼容服务。每个 Agent 在“Agent 配置与 Skill”页分别选择纯文字服务和含图片服务；修改服务会清除使用它的 Agent 的对话上下文。",
            style="SettingsHint.TLabel",
            wraplength=680,
        ).grid(row=1, column=0, sticky="w", pady=(5, 18))

        profile_row = ttk.Frame(panel, style="SettingsPanel.TFrame")
        profile_row.grid(row=2, column=0, sticky="ew", pady=(0, 16))
        profile_row.columnconfigure(0, weight=1)
        profile_combo = ttk.Combobox(profile_row, state="readonly", font=(self.ui_font_family, 11))
        profile_combo.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        add_button = ttk.Button(profile_row, text="＋ 新建服务")
        add_button.grid(row=0, column=1, padx=(0, 6))
        delete_button = ttk.Button(profile_row, text="删除当前")
        delete_button.grid(row=0, column=2)

        name_var = tk.StringVar()
        url_var = tk.StringVar()
        model_var = tk.StringVar()
        key_var = tk.StringVar()
        thinking_enabled_var = tk.BooleanVar(value=False)
        reasoning_effort_var = tk.StringVar(value="低（low）")

        def add_labeled_entry(row: int, label: str, variable: tk.StringVar, *, key: bool = False) -> ttk.Entry:
            ttk.Label(panel, text=label, style="SettingsHint.TLabel").grid(row=row, column=0, sticky="w", pady=(2, 2))
            entry = ttk.Entry(panel, textvariable=variable, font=("Consolas", 10) if key else (self.ui_font_family, 11))
            entry.grid(row=row + 1, column=0, sticky="ew", pady=(0, 8))
            return entry

        name_entry = add_labeled_entry(3, "配置名称", name_var)
        url_entry = add_labeled_entry(5, "Chat Completions 接口完整地址", url_var)
        model_entry = add_labeled_entry(7, "模型名称", model_var)
        key_entry = add_labeled_entry(9, "API Key（明文显示；本机服务可留空）", key_var, key=True)
        thinking_check = ttk.Checkbutton(
            panel,
            text="启用思考模式（仅 DeepSeek 官方接口）",
            variable=thinking_enabled_var,
        )
        thinking_check.grid(row=11, column=0, sticky="w", pady=(2, 4))
        effort_label = ttk.Label(panel, text="思考强度", style="SettingsHint.TLabel")
        effort_label.grid(row=12, column=0, sticky="w", pady=(2, 2))
        effort_labels = {"低（low）": "low", "高（high）": "high", "最高（max）": "max"}
        effort_combo = ttk.Combobox(
            panel,
            textvariable=reasoning_effort_var,
            values=tuple(effort_labels),
            state="readonly",
            width=22,
        )
        effort_combo.grid(row=13, column=0, sticky="w", pady=(0, 6))
        ttk.Label(
            panel,
            text="此选项只会发送到 https://api.deepseek.com。为节省 Token，默认关闭；开启会产生额外推理用量。关闭时强度设置无效，支持的强度取决于所选模型。",
            style="SettingsHint.TLabel",
            wraplength=680,
        ).grid(row=14, column=0, sticky="w", pady=(0, 8))
        ttk.Label(
            panel,
            text="本机 Ollama 可留空 Key；其他服务请填写对应地址、模型和 Key。远程 API 必须使用 HTTPS。Key 在本机加密保存。",
            style="SettingsHint.TLabel",
            wraplength=680,
        ).grid(row=15, column=0, sticky="w", pady=(0, 4))
        status_label = ttk.Label(panel, text="", style="SettingsStatus.TLabel", wraplength=680)
        status_label.grid(row=16, column=0, sticky="ew")
        if self.api_profile_settings_error:
            status_label.configure(text=self.api_profile_settings_error)

        agent_skill_stores = {
            "bookkeeping": self.skill_store,
            "food_health": self.food_health_skill_store,
        }
        agent_labels = {"bookkeeping": "记账 Agent", "food_health": "饮食健康 Agent"}
        agent_skill_drafts: dict[str, dict[str, str] | None] = {
            "bookkeeping": deepcopy(self.loaded_skill),
            "food_health": deepcopy(self.loaded_food_health_skill),
        }
        agent_assignment_widgets: dict[str, dict[str, Any]] = {}

        def loaded_skill_for(mode: str) -> dict[str, str] | None:
            return agent_skill_drafts[mode]

        def set_loaded_skill_for(mode: str, value: dict[str, str] | None) -> None:
            agent_skill_drafts[mode] = value
            if mode == "bookkeeping":
                self.skill_settings_error = ""
            else:
                self.food_health_skill_settings_error = ""

        def refresh_agent_model_choices() -> None:
            values = [
                f"{profile['name'] or '未命名服务'} — {profile['model'] or '未填写模型'}"
                for profile in self.api_profiles
            ]
            known_ids = {profile["id"] for profile in self.api_profiles}
            if not agent_assignment_widgets:
                return
            mode = selected_skill_agent_mode()
            widgets = agent_assignment_widgets[mode]
            for route, combo_key, assignments in (
                ("text", "text_combo", self.agent_profile_ids),
                ("image", "image_combo", self.agent_vision_profile_ids),
            ):
                combo = widgets[combo_key]
                combo.configure(values=values)
                selected_id = assignments.get(mode, "")
                selected_index = next(
                    (index for index, profile in enumerate(self.api_profiles) if profile["id"] == selected_id),
                    -1,
                )
                if selected_id not in known_ids and self.api_profiles:
                    selected_index = next(
                        (index for index, profile in enumerate(self.api_profiles)
                         if profile["id"] == self.agent_profile_ids.get(mode)),
                        0,
                    ) if route == "image" else 0
                    assignments[mode] = self.api_profiles[selected_index]["id"]
                combo.current(selected_index)

        def save_agent_model_assignment(mode: str, route: str, _event: Any = None) -> None:
            widgets = agent_assignment_widgets[mode]
            assignments = self.agent_profile_ids if route == "text" else self.agent_vision_profile_ids
            combo_key = "text_combo" if route == "text" else "image_combo"
            selected_index = widgets[combo_key].current()
            if selected_index < 0 or selected_index >= len(self.api_profiles):
                return
            next_id = self.api_profiles[selected_index]["id"]
            if next_id == assignments.get(mode):
                return
            assignments[mode] = next_id
            status_key = "纯文字服务已更改，点击应用或确认后保存。" if route == "text" else "含图片服务已更改，点击应用或确认后保存。"
            widgets["status"].configure(text=translate(status_key, self.language))

        skill_panel = ttk.Frame(agent_skill_page, style="SettingsPanel.TFrame", padding=18)
        skill_panel.pack(fill="both", expand=True)
        skill_panel.columnconfigure(0, weight=1)
        skill_panel.columnconfigure(1, weight=0)
        skill_panel.rowconfigure(10, weight=1)
        ttk.Label(skill_panel, text="Agent 配置与 Skill", style="SettingsTitle.TLabel").grid(
            row=0, column=0, columnspan=2, sticky="w"
        )
        ttk.Label(
            skill_panel,
            text="为每个 Agent 分别选择纯文字服务和含图片服务。发送时程序会按当前消息是否附图自动路由；含图片服务必须支持视觉输入。两个 Agent 的设置和 Skill 仍彼此独立。",
            style="SettingsHint.TLabel",
            wraplength=680,
        ).grid(row=1, column=0, columnspan=2, sticky="ew", pady=(5, 14))
        ttk.Label(skill_panel, text="选择 Agent", style="SettingsSection.TLabel").grid(
            row=2, column=0, columnspan=2, sticky="w"
        )
        skill_agent_mode_var = tk.StringVar(value=agent_labels["bookkeeping"])
        skill_agent_combo = ttk.Combobox(
            skill_panel,
            state="readonly",
            textvariable=skill_agent_mode_var,
            values=[agent_labels["bookkeeping"], agent_labels["food_health"]],
            font=(self.ui_font_family, 11),
        )
        skill_agent_combo.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(5, 12))
        ttk.Label(skill_panel, text="纯文字 API 服务", style="SettingsSection.TLabel").grid(
            row=4, column=0, columnspan=2, sticky="w"
        )
        model_combo = ttk.Combobox(skill_panel, state="readonly", font=(self.ui_font_family, 10))
        model_combo.grid(row=5, column=0, columnspan=2, sticky="ew", pady=(5, 8))
        ttk.Label(skill_panel, text="含图片 API 服务", style="SettingsSection.TLabel").grid(
            row=6, column=0, columnspan=2, sticky="w"
        )
        image_model_combo = ttk.Combobox(skill_panel, state="readonly", font=(self.ui_font_family, 10))
        image_model_combo.grid(row=7, column=0, columnspan=2, sticky="ew", pady=(5, 8))
        model_status = ttk.Label(skill_panel, text="", style="SettingsStatus.TLabel", wraplength=680)
        model_status.grid(row=8, column=0, columnspan=2, sticky="ew", pady=(0, 12))
        model_combo.bind(
            "<<ComboboxSelected>>",
            lambda event: save_agent_model_assignment(selected_skill_agent_mode(), "text", event),
        )
        image_model_combo.bind(
            "<<ComboboxSelected>>",
            lambda event: save_agent_model_assignment(selected_skill_agent_mode(), "image", event),
        )
        agent_assignment_widgets.update(
            {
                mode: {
                    "text_combo": model_combo,
                    "image_combo": image_model_combo,
                    "status": model_status,
                }
                for mode in agent_labels
            }
        )
        skill_path_label = ttk.Label(skill_panel, text="", style="SettingsHint.TLabel", wraplength=680)
        skill_path_label.grid(row=9, column=0, columnspan=2, sticky="ew", pady=(0, 7))
        skill_preview_frame = ttk.Frame(skill_panel, style="SettingsPanel.TFrame")
        skill_preview_frame.grid(row=10, column=0, columnspan=2, sticky="nsew")
        skill_preview_frame.columnconfigure(0, weight=1)
        skill_preview_frame.rowconfigure(0, weight=1)
        skill_preview = tk.Text(
            skill_preview_frame,
            wrap="word",
            state="disabled",
            relief="solid",
            borderwidth=1,
            padx=12,
            pady=10,
            background=color("#f9fafb"),
            foreground=color("#344054"),
            font=(self.ui_font_family, 10),
        )
        skill_preview_scroll = ttk.Scrollbar(skill_preview_frame, orient="vertical", command=skill_preview.yview)
        skill_preview.configure(yscrollcommand=skill_preview_scroll.set)
        skill_preview.grid(row=0, column=0, sticky="nsew")
        skill_preview_scroll.grid(row=0, column=1, sticky="ns")
        skill_status = ttk.Label(skill_panel, text="", style="SettingsStatus.TLabel", wraplength=680)
        skill_status.grid(row=11, column=0, columnspan=2, sticky="ew", pady=(6, 0))
        skill_buttons = ttk.Frame(skill_panel, style="SettingsPanel.TFrame")
        skill_buttons.grid(row=12, column=0, columnspan=2, sticky="ew", pady=(12, 0))
        def selected_skill_agent_mode() -> str:
            return "food_health" if skill_agent_mode_var.get() == agent_labels["food_health"] else "bookkeeping"

        def refresh_agent_skill_page(_event: Any = None) -> None:
            mode = selected_skill_agent_mode()
            store = agent_skill_stores[mode]
            title = agent_labels[mode]
            refresh_agent_model_choices()
            text_profile = next(
                (profile for profile in self.api_profiles if profile["id"] == self.agent_profile_ids.get(mode)),
                None,
            )
            image_profile = next(
                (profile for profile in self.api_profiles
                 if profile["id"] == self.agent_vision_profile_ids.get(mode)),
                None,
            )
            if text_profile and image_profile:
                model_status.configure(
                    text=(
                        f"{title} 纯文字：{text_profile['name'] or '未命名服务'} — "
                        f"{text_profile['model'] or '未填写模型'}；含图片："
                        f"{image_profile['name'] or '未命名服务'} — {image_profile['model'] or '未填写模型'}。"
                    )
                )
            else:
                model_status.configure(text="尚未配置可用的模型服务。请先在“API 服务”页添加服务。")
            try:
                loaded = agent_skill_drafts[mode]
                if loaded:
                    loaded = store.read_path(loaded["path"])
                    agent_skill_drafts[mode] = loaded
            except BookkeepingSkillError as exc:
                loaded = None
                if mode == "bookkeeping":
                    self.skill_settings_error = str(exc)
                else:
                    self.food_health_skill_settings_error = str(exc)
            else:
                set_loaded_skill_for(mode, loaded)
            if mode == self.agent_mode:
                self._update_skill_summary()
            if loaded:
                skill_path_label.configure(text=f"当前 {title} Skill：{loaded['path']}")
                preview_text = loaded["content"]
                if len(preview_text) > 20000:
                    preview_text = preview_text[:20000] + "\n\n……预览已截断；发送时会使用完整文件。"
                skill_status.configure(text=f"已加载 {loaded['name']}；仅在使用{title}时发送。")
            else:
                error = self.skill_settings_error if mode == "bookkeeping" else self.food_health_skill_settings_error
                skill_path_label.configure(text=error or f"当前 {title} 未加载 Skill。")
                preview_text = ""
                skill_status.configure(text=error or "当前未加载 Skill。")
            skill_preview.configure(state="normal")
            skill_preview.delete("1.0", "end")
            skill_preview.insert("1.0", preview_text)
            skill_preview.configure(state="disabled")

        def choose_agent_skill() -> None:
            mode = selected_skill_agent_mode()
            title = agent_labels[mode]
            store = agent_skill_stores[mode]
            loaded = loaded_skill_for(mode)
            current_path = loaded.get("path") if loaded else ""
            initial_dir = str(Path(current_path).parent) if current_path else str(store.default_path.parent)
            selected = filedialog.askopenfilename(
                parent=dialog,
                title=f"选择{title} Skill 文件",
                initialdir=initial_dir,
                filetypes=(("Skill 文件 (SKILL.md)", "SKILL.md"), ("Markdown 文件", "*.md")),
            )
            if not selected:
                return
            try:
                set_loaded_skill_for(mode, store.read_path(selected))
            except BookkeepingSkillError as exc:
                messagebox.showerror("无法加载 Skill", str(exc), parent=dialog)
                return
            refresh_agent_skill_page()
            skill_status.configure(
                text=translate(
                    "{agent} Skill 已更改，点击应用或确认后保存。", self.language
                ).format(agent=translate(title, self.language))
            )

        def unload_agent_skill() -> None:
            mode = selected_skill_agent_mode()
            title = agent_labels[mode]
            set_loaded_skill_for(mode, None)
            refresh_agent_skill_page()
            skill_status.configure(
                text=translate(
                    "{agent} Skill 将在应用或确认后卸载。", self.language
                ).format(agent=translate(title, self.language))
            )

        ttk.Button(skill_buttons, text="选择并加载文件", command=choose_agent_skill).pack(side="left")
        ttk.Button(skill_buttons, text="重新读取", command=refresh_agent_skill_page).pack(side="left", padx=(8, 0))
        ttk.Button(skill_buttons, text="卸载 Skill", command=unload_agent_skill).pack(side="left", padx=(8, 0))
        skill_agent_combo.bind("<<ComboboxSelected>>", refresh_agent_skill_page)

        def refresh_agent_settings_page() -> None:
            refresh_agent_skill_page()

        category_panel = ttk.Frame(category_page, style="SettingsPanel.TFrame", padding=18)
        category_panel.pack(fill="both", expand=True)
        category_panel.columnconfigure(0, weight=1)
        category_panel.rowconfigure(4, weight=1)
        ttk.Label(category_panel, text="记账类别", style="SettingsTitle.TLabel").grid(
            row=0, column=0, sticky="w"
        )
        ttk.Label(
            category_panel,
            text=translate(
                "新增收入或支出类别，并按所选语言维护类别名称。保存后记账 Agent 会在下次请求时读取新类别；已有账目不会改变。",
                self.language,
            ),
            style="SettingsHint.TLabel",
            wraplength=700,
        ).grid(row=1, column=0, sticky="ew", pady=(5, 16))

        category_form = ttk.LabelFrame(category_panel, text="新增类别", padding=14)
        category_form.grid(row=2, column=0, sticky="ew", pady=(0, 14))
        category_form.columnconfigure(1, weight=1)
        category_name_var = tk.StringVar()
        category_kind_var = tk.StringVar(value="支出")
        ttk.Label(category_form, text="类别名称", style="SettingsHint.TLabel").grid(
            row=0, column=0, sticky="w", padx=(0, 12), pady=5
        )
        category_name_entry = ttk.Entry(category_form, textvariable=category_name_var)
        category_name_entry.grid(row=0, column=1, sticky="ew", pady=5)
        ttk.Label(category_form, text="类别类型", style="SettingsHint.TLabel").grid(
            row=1, column=0, sticky="w", padx=(0, 12), pady=5
        )
        category_kind_combo = ttk.Combobox(
            category_form,
            textvariable=category_kind_var,
            values=("支出", "收入"),
            state="readonly",
            width=16,
        )
        category_kind_combo.grid(row=1, column=1, sticky="w", pady=5)

        category_name_language_labels = {
            "zh-CN": translate("简体中文", self.language),
            "ja-JP": translate("日语", self.language),
            "en-US": translate("英语", self.language),
        }
        preferred_category_name_language = (
            self.language if self.language in category_name_language_labels else "zh-CN"
        )
        category_name_language_var = tk.StringVar(
            value=category_name_language_labels[preferred_category_name_language]
        )
        category_name_language_frame = ttk.Frame(category_panel, style="SettingsPanel.TFrame")
        category_name_language_frame.grid(row=3, column=0, sticky="ew", pady=(0, 10))
        ttk.Label(
            category_name_language_frame,
            text=translate("显示语言", self.language),
            style="SettingsHint.TLabel",
        ).pack(side="left", padx=(0, 8))
        category_name_language_combo = ttk.Combobox(
            category_name_language_frame,
            textvariable=category_name_language_var,
            values=tuple(category_name_language_labels.values()),
            state="readonly",
            width=18,
        )
        category_name_language_combo.pack(side="left", padx=(0, 12))
        category_edit_button = ttk.Button(
            category_name_language_frame,
            text=translate("编辑所选类别", self.language),
            style="Settings.TButton",
        )
        category_edit_button.pack(side="left")
        category_name_save_button = ttk.Button(
            category_name_language_frame,
            text=translate("保存修改", self.language),
            style="Settings.TButton",
            state="disabled",
        )
        category_name_save_button.pack(side="left", padx=(8, 0))
        category_name_cancel_button = ttk.Button(
            category_name_language_frame,
            text=translate("取消编辑", self.language),
            style="Settings.TButton",
            state="disabled",
        )
        category_name_cancel_button.pack(side="left", padx=(8, 0))

        category_tree_frame = ttk.Frame(category_panel, style="SettingsPanel.TFrame")
        category_tree_frame.grid(row=4, column=0, sticky="nsew")
        category_tree_frame.columnconfigure(0, weight=1)
        category_tree_frame.rowconfigure(0, weight=1)
        category_tree = ttk.Treeview(
            category_tree_frame,
            columns=("kind", "name"),
            show="headings",
            height=12,
            selectmode="browse",
        )
        category_tree._bk_i18n_manual_headings = True
        category_tree.heading("kind", text=translate("类别类型", self.language))
        category_tree.heading("name", text=translate("记账类别", self.language))
        category_tree.column("kind", width=130, minwidth=100, anchor="w", stretch=False)
        category_tree.column("name", width=420, minwidth=180, anchor="w", stretch=True)
        category_tree.tag_configure("stripe_even", background=color("#ffffff"))
        category_tree.tag_configure("stripe_odd", background=color("#edf5ff"))
        category_tree.grid(row=0, column=0, sticky="nsew")
        category_tree_scroll = ttk.Scrollbar(
            category_tree_frame, orient="vertical", command=category_tree.yview
        )
        category_tree_scroll.grid(row=0, column=1, sticky="ns")
        category_tree.configure(yscrollcommand=category_tree_scroll.set)
        category_tree._bk_i18n_item_values = {}
        category_tree._bk_i18n_row_translatable = {}
        category_name_edit: dict[str, Any] = {"item_id": None, "entry": None}

        category_status_var = tk.StringVar(value="")
        ttk.Label(
            category_panel,
            textvariable=category_status_var,
            style="SettingsStatus.TLabel",
            wraplength=700,
        ).grid(row=5, column=0, sticky="w", pady=(10, 0))

        def selected_category_name_language() -> str:
            selected_label = category_name_language_var.get()
            return next(
                (
                    code
                    for code, label in category_name_language_labels.items()
                    if label == selected_label
                ),
                "zh-CN",
            )

        def finish_category_name_edit() -> None:
            editor = category_name_edit.get("entry")
            category_name_edit["entry"] = None
            category_name_edit["item_id"] = None
            if editor is not None:
                editor.destroy()
            category_edit_button.configure(state="normal")
            category_name_save_button.configure(state="disabled")
            category_name_cancel_button.configure(state="disabled")

        def refresh_category_table(_event: Any = None) -> None:
            finish_category_name_edit()
            display_language = selected_category_name_language()
            category_tree.heading(
                "kind", text=translate("类别类型", display_language)
            )
            category_tree.heading(
                "name", text=translate("记账类别", display_language)
            )
            selected_ids = category_tree.selection()
            selected_id = selected_ids[0] if selected_ids else None
            category_tree.delete(*category_tree.get_children())
            category_tree._bk_i18n_item_values = {}
            category_tree._bk_i18n_row_translatable = {}
            database = Database(self.database_path)
            try:
                database.initialize()
                rows = database.connection.execute(
                    "SELECT id,name,kind FROM categories WHERE is_active=1 ORDER BY kind,name COLLATE NOCASE"
                ).fetchall()
                translations = database.category_translations()
            except (LedgerError, sqlite3.Error) as exc:
                category_status_var.set(f"无法读取类别：{exc}")
                return
            finally:
                database.close()
            for index, row in enumerate(rows):
                source_values = ("收入" if row["kind"] == "income" else "支出", str(row["name"]))
                category_display_name = translations.get(int(row["id"]), {}).get(
                    display_language, ""
                )
                if not category_display_name:
                    category_display_name = source_values[1]
                display_kind = translate(source_values[0], display_language)
                item_id = category_tree.insert(
                    "", "end", iid=str(row["id"]),
                    values=(
                        display_kind,
                        category_display_name,
                    ),
                    tags=("stripe_even" if index % 2 == 0 else "stripe_odd",),
                )
                category_tree._bk_i18n_item_values[item_id] = (
                    display_kind, category_display_name
                )
                category_tree._bk_i18n_row_translatable[item_id] = set()
            if selected_id and category_tree.exists(selected_id):
                category_tree.selection_set(selected_id)
                category_tree.focus(selected_id)

        def start_category_name_edit() -> None:
            selection = category_tree.selection()
            if not selection:
                messagebox.showinfo(
                    translate("未选择类别", self.language),
                    translate("请先选择要编辑的记账类别。", self.language),
                    parent=dialog,
                )
                return
            item_id = selection[0]
            cell_box = category_tree.bbox(item_id, "name")
            if not cell_box:
                return
            category_name_edit["item_id"] = item_id
            category_name_editor = ttk.Entry(category_tree)
            category_name_editor.insert(0, category_tree.set(item_id, "name"))
            category_name_editor.select_range(0, "end")
            category_name_editor.place(
                x=cell_box[0], y=cell_box[1], width=cell_box[2], height=cell_box[3]
            )
            category_name_edit["entry"] = category_name_editor
            category_edit_button.configure(state="disabled")
            category_name_save_button.configure(state="normal")
            category_name_cancel_button.configure(state="normal")
            category_name_editor.bind("<Return>", lambda _event: save_category_name_edit())
            category_name_editor.bind("<Escape>", lambda _event: finish_category_name_edit())
            category_name_editor.focus_set()

        def save_category_name_edit() -> None:
            editor = category_name_edit.get("entry")
            item_id = category_name_edit.get("item_id")
            if editor is None or item_id is None:
                return
            category_name = editor.get().strip()
            if not category_name:
                messagebox.showwarning(
                    translate("缺少类别名称", self.language),
                    translate("请填写类别名称。", self.language),
                    parent=dialog,
                )
                editor.focus_set()
                return
            database = Database(self.database_path)
            try:
                database.initialize()
                language = selected_category_name_language()
                database.set_category_translation(int(item_id), language, category_name)
            except (LedgerError, sqlite3.Error, ValueError) as exc:
                messagebox.showerror(
                    translate("无法保存", self.language), str(exc), parent=dialog
                )
                return
            finally:
                database.close()
            category_status_var.set(translate("类别名称已保存。", self.language))
            finish_category_name_edit()
            refresh_category_table()

        category_edit_button.configure(command=start_category_name_edit)
        category_name_save_button.configure(command=save_category_name_edit)
        category_name_cancel_button.configure(command=finish_category_name_edit)
        category_tree.bind("<Double-1>", lambda _event: start_category_name_edit())

        def cancel_category_name_edit_on_selection(_event: Any = None) -> None:
            editing_id = category_name_edit.get("item_id")
            selection = category_tree.selection()
            if editing_id is not None and selection and selection[0] != editing_id:
                finish_category_name_edit()

        category_tree.bind("<<TreeviewSelect>>", cancel_category_name_edit_on_selection)
        for scroll_event in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            category_tree.bind(scroll_event, lambda _event: finish_category_name_edit())
        category_tree_scroll.bind("<ButtonPress-1>", lambda _event: finish_category_name_edit())
        category_name_language_combo.bind(
            "<<ComboboxSelected>>", refresh_category_table
        )

        def add_ledger_category() -> None:
            category_name = category_name_var.get().strip()
            category_kind = {"支出": "expense", "收入": "income"}.get(category_kind_var.get())
            if not category_name:
                messagebox.showwarning("缺少类别名称", "请填写类别名称。", parent=dialog)
                category_name_entry.focus_set()
                return
            if category_kind is None:
                messagebox.showwarning("缺少类别类型", "请选择收入或支出类别。", parent=dialog)
                return
            database = Database(self.database_path)
            try:
                database.initialize()
                database.add_category(category_name, category_kind)
            except (LedgerError, sqlite3.Error) as exc:
                messagebox.showerror("无法添加类别", str(exc), parent=dialog)
                return
            finally:
                database.close()
            category_name_var.set("")
            category_status_var.set("类别已添加；记账 Agent 下次请求会读取新类别。")
            refresh_category_table()

        ttk.Button(
            category_form,
            text="添加类别",
            style="Settings.TButton",
            command=add_ledger_category,
        ).grid(row=2, column=1, sticky="w", pady=(8, 0))

        data_panel = ttk.Frame(data_page, style="SettingsPanel.TFrame", padding=18)
        data_panel.pack(fill="both", expand=True)
        data_panel.columnconfigure(0, weight=1)
        ttk.Label(data_panel, text="账本与备份", style="SettingsTitle.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(
            data_panel,
            text="账本保存在这台电脑上。你可以打开所在文件夹，或创建一份可恢复的 SQLite 备份。",
            style="SettingsHint.TLabel",
            wraplength=680,
        ).grid(row=1, column=0, sticky="w", pady=(5, 20))
        database_card = ttk.Frame(data_panel, style="SettingsPanel.TFrame", padding=(16, 14))
        database_card.grid(row=2, column=0, sticky="ew", pady=(0, 12))
        database_card.columnconfigure(0, weight=1)
        ttk.Label(database_card, text="当前账本文件", style="SettingsSection.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(
            database_card,
            text=str(self.database_path.resolve()),
            style="SettingsPath.TLabel",
            wraplength=650,
            justify="left",
        ).grid(row=1, column=0, sticky="w", pady=(5, 12))
        ttk.Button(database_card, text="打开账本文件夹", command=lambda: self.open_database_folder(parent=dialog)).grid(row=2, column=0, sticky="w")
        receipt_image_card = ttk.Frame(data_panel, style="SettingsPanel.TFrame", padding=(16, 14))
        receipt_image_card.grid(row=3, column=0, sticky="ew", pady=(0, 12))
        receipt_image_card.columnconfigure(0, weight=1)
        ttk.Label(
            receipt_image_card,
            text=translate("小票图片", self.language),
            style="SettingsSection.TLabel",
        ).grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 8)
        )
        receipt_image_enabled_var = tk.BooleanVar(value=self.save_receipt_images_locally)
        receipt_image_status = ttk.Label(
            receipt_image_card,
            text=(
                translate("保存设置无法读取；已默认关闭。", self.language)
                if self.receipt_image_settings_error
                else ""
            ),
            style="SettingsStatus.TLabel",
        )

        def mark_receipt_image_setting_pending() -> None:
            receipt_image_status.configure(
                text=translate(
                    "更改将在点击应用或确认后保存。",
                    self.language,
                )
            )

        ttk.Checkbutton(
            receipt_image_card,
            text=translate("保存发送给记账 Agent 的图片到本地", self.language),
            variable=receipt_image_enabled_var,
            command=mark_receipt_image_setting_pending,
        ).grid(row=1, column=0, sticky="w")
        ttk.Button(
            receipt_image_card,
            text=translate("打开图片文件夹", self.language),
            command=lambda: self.open_receipt_image_folder(parent=dialog),
        ).grid(row=1, column=1, sticky="e", padx=(12, 0))
        ttk.Label(
            receipt_image_card,
            text=translate(
                "开启后，记账 Agent 发送的图片会压缩后保存在本地文件夹；饮食健康 Agent 图片不会保存。关闭后只影响新发送的图片。",
                self.language,
            ),
            style="SettingsHint.TLabel",
            wraplength=650,
            justify="left",
        ).grid(row=2, column=0, columnspan=2, sticky="w", pady=(8, 6))
        ttk.Label(
            receipt_image_card,
            text=translate("需要 Pillow 压缩；未安装时图片会按原格式保存。", self.language),
            style="SettingsHint.TLabel",
        ).grid(row=3, column=0, columnspan=2, sticky="w", pady=(0, 6))
        ttk.Label(
            receipt_image_card,
            text=translate("图片文件夹位置", self.language),
            style="SettingsHint.TLabel",
        ).grid(
            row=4, column=0, columnspan=2, sticky="w"
        )
        ttk.Label(
            receipt_image_card,
            text=str((self.database_path.parent / "receipt_images").resolve()),
            style="SettingsPath.TLabel",
            wraplength=650,
            justify="left",
        ).grid(row=5, column=0, columnspan=2, sticky="w", pady=(4, 6))
        receipt_image_status.grid(row=6, column=0, columnspan=2, sticky="w")

        backup_scope_store = BackupScopeStore()
        backup_scope_load_error = ""
        try:
            backup_scope = backup_scope_store.load()
        except BackupScopeError as exc:
            backup_scope = dict(DEFAULT_BACKUP_SCOPE)
            backup_scope_load_error = str(exc)
        backup_scope_card = ttk.Frame(data_panel, style="SettingsPanel.TFrame", padding=(16, 14))
        backup_scope_card.grid(row=4, column=0, sticky="ew", pady=(0, 12))
        for column in range(4):
            backup_scope_card.columnconfigure(column, weight=1)
        ttk.Label(
            backup_scope_card,
            text=translate("云备份范围", self.language),
            style="SettingsSection.TLabel",
        ).grid(row=0, column=0, columnspan=4, sticky="w", pady=(0, 6))
        ttk.Label(
            backup_scope_card,
            text=translate(
                "选择放入 GitHub/Gitee 云备份的数据。默认全部选中；取消勾选的内容不会上传。首次连接、手动上传和自动同步都使用这里的选择。",
                self.language,
            ),
            style="SettingsHint.TLabel",
            wraplength=760,
            justify="left",
        ).grid(row=1, column=0, columnspan=4, sticky="w", pady=(0, 8))
        backup_scope_variables = {
            key: tk.BooleanVar(value=backup_scope[key]) for key in BACKUP_SCOPE_KEYS
        }
        backup_scope_status = ttk.Label(
            backup_scope_card,
            text=(
                translate("云备份范围设置无法读取：{error}", self.language).format(
                    error=translate(backup_scope_load_error, self.language)
                )
                if backup_scope_load_error
                else ""
            ),
            style="SettingsStatus.TLabel",
            wraplength=760,
            justify="left",
        )

        backup_scope_labels = {
            "settings": "设置内容（预算、类别与自定义 Skill）",
            "bills": "账单（流水与小票）",
            "payment_methods": "付款方式",
            "recurring_payments": "定期付款",
            "bank_accounts": "银行及资金账户",
            "credit_cards": "信用卡",
            "assets": "资产管理",
        }

        def backup_scope_selection() -> dict[str, bool]:
            return {
                key: bool(variable.get())
                for key, variable in backup_scope_variables.items()
            }

        def refresh_backup_scope_toggle_label() -> None:
            all_selected = all(backup_scope_selection().values())
            backup_scope_toggle_button.configure(
                text=translate("取消全选" if all_selected else "全选", self.language)
            )

        def update_backup_scope_draft() -> None:
            backup_scope_status.configure(
                text=translate("更改将在点击应用或确认后保存。", self.language)
            )
            refresh_backup_scope_toggle_label()

        def select_all_backup_scope() -> None:
            select_all = not all(backup_scope_selection().values())
            for variable in backup_scope_variables.values():
                variable.set(select_all)
            update_backup_scope_draft()

        for index, key in enumerate(BACKUP_SCOPE_KEYS):
            ttk.Checkbutton(
                backup_scope_card,
                text=translate(backup_scope_labels[key], self.language),
                variable=backup_scope_variables[key],
                command=update_backup_scope_draft,
            ).grid(row=2 + index // 4, column=index % 4, sticky="w", padx=(0, 10), pady=3)
        backup_scope_toggle_button = ttk.Button(
            backup_scope_card,
            text=translate("全选", self.language),
            command=select_all_backup_scope,
        )
        backup_scope_toggle_button.grid(row=4, column=3, sticky="e", pady=(5, 0))
        refresh_backup_scope_toggle_label()
        backup_scope_status.grid(row=5, column=0, columnspan=4, sticky="w", pady=(4, 0))
        ttk.Label(
            backup_scope_card,
            text=translate(
                "API 密钥、GitHub/Gitee 令牌、界面语言和本机偏好始终只保存在本机。账户未勾选但账单或计划需要关联时，会保留匿名账户名，不含原账户名和余额；设置未勾选但账单或计划需要类别时，会保留类别占位名，不含原类别名和翻译。恢复云端快照会替换本机账本；快照未包含的账本内容不会出现在恢复结果中。",
                self.language,
            ),
            style="SettingsHint.TLabel",
            wraplength=760,
            justify="left",
        ).grid(row=6, column=0, columnspan=4, sticky="w", pady=(5, 0))

        github_card = ttk.Frame(data_panel, style="SettingsPanel.TFrame", padding=(16, 14))
        github_card.grid(row=5, column=0, sticky="ew", pady=(0, 12))
        github_card.columnconfigure(1, weight=1)
        ttk.Label(
            github_card,
            text=translate("GitHub 同步", self.language),
            style="SettingsSection.TLabel",
        ).grid(row=0, column=0, columnspan=4, sticky="w", pady=(0, 6))
        ttk.Label(
            github_card,
            text=translate(
                "点击后在浏览器登录 GitHub 并授权。软件会在你的账号下使用独立私有仓库备份上方选中的数据；密码只在 GitHub 页面输入。",
                self.language,
            ),
            style="SettingsHint.TLabel",
            wraplength=700,
            justify="left",
        ).grid(row=1, column=0, columnspan=4, sticky="w", pady=(0, 8))
        github_auto_sync_var = tk.BooleanVar(value=self.github_auto_sync_enabled)
        github_auto_sync_status = ttk.Label(
            github_card,
            text=(
                translate(self.github_auto_sync_settings_error, self.language)
                if self.github_auto_sync_settings_error
                else translate(
                    "GitHub 自动同步已开启。" if self.github_auto_sync_enabled else "GitHub 自动同步已关闭。",
                    self.language,
                )
            ),
            style="SettingsStatus.TLabel",
            wraplength=700,
            justify="left",
        )

        def mark_github_auto_sync_pending() -> None:
            github_auto_sync_status.configure(
                text=translate("更改将在点击应用或确认后保存。", self.language)
            )

        ttk.Checkbutton(
            github_card,
            text=translate("每笔记账后自动同步到 GitHub", self.language),
            variable=github_auto_sync_var,
            command=mark_github_auto_sync_pending,
        ).grid(row=2, column=0, columnspan=4, sticky="w", pady=(2, 0))
        ttk.Label(
            github_card,
            text=translate(
                "记账成功后在后台上传账本、支付规则、自定义 Skill 和已保存的小票图片。需要先连接 GitHub；多台设备的修改不会自动合并。",
                self.language,
            ),
            style="SettingsHint.TLabel",
            wraplength=700,
            justify="left",
        ).grid(row=3, column=0, columnspan=4, sticky="w", pady=(3, 2))
        github_auto_sync_status.grid(row=4, column=0, columnspan=4, sticky="w", pady=(2, 4))
        github_settings_store = GitHubSyncSettingsStore()
        github_token_store = GitHubTokenStore()
        try:
            github_saved_settings = github_settings_store.load()
            github_saved_token = github_token_store.load()
            github_settings_error = ""
        except (GitHubSyncError, SecureSettingsError) as exc:
            github_saved_settings = {
                "repository_name": DEFAULT_BACKUP_REPOSITORY_NAME,
                "repository": "",
            }
            github_saved_token = ""
            github_settings_error = str(exc)
        github_saved_token_is_app = is_github_app_user_token(github_saved_token)
        github_saved_token_needs_reauth = bool(github_saved_token and not github_saved_token_is_app)
        github_status = ttk.Label(
            github_card,
            text=(
                translate("GitHub 设置无法读取：{error}", self.language).format(
                    error=translate(github_settings_error, self.language)
                )
                if github_settings_error
                else (
                    translate("已连接 GitHub：{repository}", self.language).format(
                        repository=github_saved_settings["repository"] or github_saved_settings["repository_name"]
                    )
                    if github_saved_token_is_app and github_saved_settings["repository"]
                    else (
                        translate("旧版 GitHub 授权需要更新；点击下方按钮重新连接。", self.language)
                        if github_saved_token_needs_reauth
                        else (
                            translate("GitHub App 尚未完成配置；软件开发者需先配置公开 Client ID。", self.language)
                            if not GITHUB_APP_CLIENT_ID
                            else translate("尚未连接 GitHub。点击下方按钮并在浏览器授权即可。", self.language)
                        )
                    )
                )
            ),
            style="SettingsStatus.TLabel",
            wraplength=700,
            justify="left",
        )
        github_status.grid(row=5, column=0, columnspan=4, sticky="w", pady=(7, 4))
        ttk.Label(
            github_card,
            text=translate(
                "云备份内容由上方勾选项决定。API 密钥、GitHub 授权、界面语言及本机偏好始终只保存在本机；同步包未额外加密。",
                self.language,
            ),
            style="SettingsHint.TLabel",
            wraplength=700,
            justify="left",
        ).grid(row=6, column=0, columnspan=4, sticky="w", pady=(3, 2))
        ttk.Label(
            github_card,
            text=translate(
                "GitHub App 仅申请创建私有仓库及读写同步数据文件所需的权限；授权可在 GitHub 设置中撤销。",
                self.language,
            ),
            style="SettingsHint.TLabel",
            wraplength=700,
            justify="left",
        ).grid(row=7, column=0, columnspan=4, sticky="w", pady=(2, 8))
        ttk.Label(
            github_card,
            text=translate(
                "当前同步整份快照，不会自动合并两台设备各自的修改；一台上传后，另一台应从 GitHub 恢复。",
                self.language,
            ),
            style="SettingsHint.TLabel",
            wraplength=700,
            justify="left",
        ).grid(row=8, column=0, columnspan=4, sticky="w", pady=(0, 8))

        github_sync_busy = {"value": False}

        def start_github_authorization() -> None:
            if not GITHUB_APP_CLIENT_ID.strip():
                messagebox.showwarning(
                    translate("GitHub App 尚未配置", self.language),
                    translate("GitHub App 尚未配置公开 Client ID；请由软件开发者完成应用配置。", self.language),
                    parent=dialog,
                )
                return
            if github_sync_busy["value"]:
                return

            install_dialog = tk.Toplevel(dialog)
            install_dialog.title(translate("安装 GitHub App", self.language))
            install_dialog.transient(dialog)
            install_dialog.resizable(False, False)
            install_panel = ttk.Frame(install_dialog, style="SettingsPanel.TFrame", padding=22)
            install_panel.pack(fill="both", expand=True)
            ttk.Label(
                install_panel,
                text=translate(
                    "先把 Household Bookkeeping Sync Test 安装到你准备用来同步的 GitHub 账号。安装和设备授权是两步；如果已经安装，可直接继续。",
                    self.language,
                ),
                style="SettingsHint.TLabel",
                wraplength=520,
                justify="left",
            ).pack(fill="x", pady=(0, 10))
            ttk.Label(
                install_panel,
                text=translate(
                    "安装时请核对 Contents 读写和 Repository creation 写入权限。安装完成后回到这里继续授权；软件只会在该账号的私有仓库中保存同步数据。",
                    self.language,
                ),
                style="SettingsHint.TLabel",
                wraplength=520,
                justify="left",
            ).pack(fill="x", pady=(0, 16))
            install_actions = ttk.Frame(install_panel, style="SettingsPanel.TFrame")
            install_actions.pack(fill="x")

            def open_install_page() -> None:
                try:
                    webbrowser.open(GITHUB_APP_INSTALL_URL)
                except Exception as exc:
                    messagebox.showerror(
                        translate("无法打开 GitHub 安装页面", self.language),
                        translate("无法打开 GitHub 安装页面：{error}", self.language).format(error=exc),
                        parent=install_dialog,
                    )

            ttk.Button(
                install_actions,
                text=translate("打开 GitHub App 安装页", self.language),
                command=open_install_page,
            ).pack(side="left")
            ttk.Button(
                install_actions,
                text=translate("取消", self.language),
                command=install_dialog.destroy,
            ).pack(side="right")
            ttk.Button(
                install_actions,
                text=translate("已安装，继续授权", self.language),
                style="Send.TButton",
                command=lambda: (install_dialog.destroy(), start_github_device_authorization()),
            ).pack(side="right", padx=(0, 8))
            install_dialog.update_idletasks()
            install_width = max(560, install_dialog.winfo_reqwidth())
            install_height = install_dialog.winfo_reqheight()
            install_x = max(0, install_dialog.winfo_screenwidth() // 2 - install_width // 2)
            install_y = max(0, install_dialog.winfo_screenheight() // 2 - install_height // 2)
            install_dialog.geometry(f"{install_width}x{install_height}+{install_x}+{install_y}")
            install_dialog.grab_set()

        def start_github_device_authorization() -> None:
            client_id = GITHUB_APP_CLIENT_ID.strip()
            repository_name = (
                github_saved_settings.get("repository_name") or DEFAULT_BACKUP_REPOSITORY_NAME
            ).strip()
            if not client_id:
                messagebox.showwarning(
                    translate("GitHub App 尚未配置", self.language),
                    translate("GitHub App 尚未配置公开 Client ID；请由软件开发者完成应用配置。", self.language),
                    parent=dialog,
                )
                return
            if github_sync_busy["value"]:
                return
            # Reauthorization grants access, not permission to replace this ledger.
            self._pull_state().pause_downloads()
            github_sync_busy["value"] = True
            auth_dialog = tk.Toplevel(dialog)
            auth_dialog.title(translate("连接 GitHub", self.language))
            auth_dialog.transient(dialog)
            auth_dialog.resizable(False, False)
            auth_dialog.configure(bg=color("#ffffff"))
            auth_cancelled = threading.Event()
            auth_dialog.protocol("WM_DELETE_WINDOW", lambda: (auth_cancelled.set(), auth_dialog.destroy()))
            auth_panel = ttk.Frame(auth_dialog, style="SettingsPanel.TFrame", padding=22)
            auth_panel.pack(fill="both", expand=True)
            auth_message = ttk.Label(
                auth_panel,
                text=translate("正在请求 GitHub 授权码…", self.language),
                style="SettingsHint.TLabel",
                wraplength=400,
                justify="left",
            )
            auth_message.pack(fill="x", pady=(0, 12))
            auth_code = ttk.Label(
                auth_panel,
                text="",
                style="SettingsTitle.TLabel",
                font=(self.ui_font_family, 22, "bold"),
            )
            auth_code.pack(pady=(0, 12))

            def copy_auth_code() -> None:
                code = str(auth_code.cget("text")).strip()
                if not code:
                    return
                try:
                    self.root.clipboard_clear()
                    self.root.clipboard_append(code)
                    self.root.update_idletasks()
                except tk.TclError:
                    copy_code_button.configure(
                        text=translate("复制失败，请重试", self.language)
                    )
                    return
                copy_code_button.configure(text=translate("已复制", self.language))

            copy_code_button = ttk.Button(
                auth_panel,
                text=translate("复制验证码", self.language),
                command=copy_auth_code,
                state="disabled",
            )
            copy_code_button.pack(pady=(0, 12))
            auth_actions = ttk.Frame(auth_panel, style="SettingsPanel.TFrame")
            auth_actions.pack(fill="x")
            open_auth_button = ttk.Button(
                auth_actions,
                text=translate("打开 GitHub 授权页面", self.language),
                command=lambda: webbrowser.open(DEVICE_VERIFY_URL),
                state="disabled",
            )
            open_auth_button.pack(side="left")
            ttk.Button(
                auth_actions,
                text=translate("取消", self.language),
                command=lambda: (auth_cancelled.set(), auth_dialog.destroy()),
            ).pack(side="right")
            auth_dialog.update_idletasks()
            auth_width = max(440, auth_dialog.winfo_reqwidth())
            auth_height = max(190, auth_dialog.winfo_reqheight())
            auth_x = max(0, (auth_dialog.winfo_screenwidth() - auth_width) // 2)
            auth_y = max(0, (auth_dialog.winfo_screenheight() - auth_height) // 2)
            auth_dialog.geometry(f"{auth_width}x{auth_height}+{auth_x}+{auth_y}")
            auth_dialog.grab_set()

            def auth_done(
                message: str,
                *,
                success: bool = False,
                error: str = "",
                repository: str = "",
                choose_ledger: bool = False,
            ) -> None:
                github_sync_busy["value"] = False
                github_status.configure(text=message)
                if auth_dialog.winfo_exists():
                    auth_dialog.destroy()
                if error:
                    messagebox.showerror(
                        translate("GitHub 连接失败", self.language),
                        translate("GitHub 连接失败：{error}", self.language).format(
                            error=translate(error, self.language)
                        ),
                        parent=dialog,
                    )
                if success:
                    github_saved_settings["repository_name"] = repository_name
                    github_saved_settings["repository"] = repository
                    upload_button.configure(state="normal")
                    restore_button.configure(state="normal")
                    if choose_ledger and not error:
                        choose_github_ledger()

            def choose_github_ledger() -> None:
                choice_dialog = tk.Toplevel(dialog)
                choice_dialog.title(translate("选择登录后的账本", self.language))
                choice_dialog.transient(dialog)
                choice_dialog.resizable(False, False)
                panel = ttk.Frame(choice_dialog, style="SettingsPanel.TFrame", padding=22)
                panel.pack(fill="both", expand=True)
                ttk.Label(
                    panel,
                    text=translate("GitHub 已连接。请选择下载云端账本，或保留本机账本。下载会替换本机账本，恢复前会完整备份；保留本机后，自动下载将暂停，直到你手动从云端恢复。", self.language),
                    style="SettingsHint.TLabel", wraplength=460, justify="left",
                ).pack(fill="x", pady=(0, 16))

                def keep_local() -> None:
                    self._pull_state().pause_downloads()
                    github_status.configure(text=translate("已保留本机账本，自动下载已暂停。", self.language))
                    choice_dialog.destroy()

                def download_cloud() -> None:
                    choice_dialog.destroy()
                    sync_github("download", confirmed_download=True)

                actions = ttk.Frame(panel, style="SettingsPanel.TFrame")
                actions.pack(fill="x")
                ttk.Button(actions, text=translate("下载云端账本", self.language),
                           command=download_cloud).pack(side="left")
                keep_button = ttk.Button(actions, text=translate("保留本机账本", self.language),
                                         command=keep_local)
                keep_button.pack(side="right", padx=(12, 0))
                choice_dialog.protocol("WM_DELETE_WINDOW", keep_local)
                choice_dialog.grab_set()
                keep_button.focus_set()

            def authorize_worker() -> None:
                connected_repository = ""
                try:
                    device = request_device_code(client_id)

                    def show_device_code() -> None:
                        if not auth_dialog.winfo_exists():
                            return
                        auth_message.configure(
                            text=translate(
                                "请打开 GitHub 授权页面并输入下面的验证码。授权完成后会自动连接私有仓库。",
                                self.language,
                            )
                        )
                        auth_code.configure(text=str(device["user_code"]))
                        copy_code_button.configure(state="normal")
                        open_auth_button.configure(state="normal")

                    dialog.after(0, show_device_code)
                    credentials = poll_device_token(
                        client_id,
                        str(device["device_code"]),
                        int(device["interval"]),
                        int(device["expires_in"]),
                        auth_cancelled.is_set,
                    )
                    token = credentials["access_token"]
                    refresh_token = credentials["refresh_token"]
                    github_token_store.save(token, refresh_token)
                    client = GitHubClient(
                        token,
                        refresh_token=refresh_token,
                        client_id=client_id,
                        token_store=github_token_store,
                    )
                    user = client.current_user()
                    login = str(user.get("login") or "").strip()
                    if not login:
                        raise GitHubSyncError("GitHub 未返回账户名称。")
                    repository, created = client.ensure_private_repository(login, repository_name)
                    connected_repository = repository
                    has_cloud_backup = not created and client.sync_bundle_exists(repository)
                    if not has_cloud_backup:
                        with self._github_upload_lock, github_sync_process_lock():
                            with tempfile.TemporaryDirectory(prefix="household-github-upload-") as temp_name:
                                bundle_path = Path(temp_name) / "sync-bundle.zip"
                                sync_revision = local_revision(self.database_path, **self._cloud_stores())
                                bundle = create_sync_bundle(
                                    self.database_path,
                                    bundle_path,
                                    receipt_image_directory=self.database_path.parent / "receipt_images",
                                )
                                new_sha = client.upload_bundle(repository, bundle, expected_sha=None)
                            github_settings_store.save(
                                repository_name=repository_name,
                                repository=repository,
                                last_sync_sha=new_sha,
                            )
                            self._mark_cloud_checkpoint('github', repository, new_sha, sync_revision)
                        result = translate(
                            "GitHub 已连接，私有仓库已创建并上传本机同步数据。"
                            if created
                            else "GitHub 已连接，同步文件已首次上传。",
                            self.language,
                        )
                    else:
                        github_settings_store.save(
                            repository_name=repository_name,
                            repository=repository,
                        )
                        result = translate(
                            "已连接 GitHub；该私有仓库已有数据，请选择上传或恢复。",
                            self.language,
                        )
                    dialog.after(0, lambda: auth_done(result, success=True, repository=repository,
                                                     choose_ledger=has_cloud_backup))
                except Exception as exc:
                    if auth_cancelled.is_set():
                        dialog.after(0, lambda: auth_done(translate("GitHub 授权已取消。", self.language)))
                    else:
                        error = str(exc)
                        status_text = translate("GitHub 连接失败：{error}", self.language).format(
                            error=translate(error, self.language)
                        )
                        dialog.after(
                            0,
                            lambda: auth_done(
                                status_text,
                                success=bool(connected_repository),
                                repository=connected_repository,
                                error=error,
                            ),
                        )

            threading.Thread(target=authorize_worker, name="github-device-auth", daemon=True).start()

        connect_button = ttk.Button(
            github_card,
            text=translate("连接 GitHub 并备份", self.language),
            style="Send.TButton",
            command=start_github_authorization,
        )
        connect_button.grid(row=9, column=0, sticky="w", pady=(3, 0))

        def sync_github(direction: str, *, confirmed_download: bool = False) -> None:
            if github_sync_busy["value"]:
                return
            if direction == "download" and (self.busy or self._recurring_processing):
                messagebox.showinfo(
                    translate("稍后重试", self.language),
                    translate("记账或定期收支正在处理中，请等处理完成后再从 GitHub 恢复。", self.language),
                    parent=dialog,
                )
                return
            repository = github_saved_settings.get("repository", "")
            try:
                credentials = github_token_store.load_credentials()
            except SecureSettingsError as exc:
                github_status.configure(
                    text=translate("GitHub 连接失败：{error}", self.language).format(
                        error=translate(str(exc), self.language)
                    )
                )
                return
            if not credentials["access_token"] or not repository:
                messagebox.showwarning(
                    translate("尚未连接 GitHub", self.language),
                    translate("请先授权并连接 GitHub。", self.language),
                    parent=dialog,
                )
                return
            if not is_github_app_user_token(credentials["access_token"]):
                message = translate("旧版 GitHub 授权需要更新；点击下方按钮重新连接。", self.language)
                github_status.configure(text=message)
                messagebox.showwarning(
                    translate("需要重新连接 GitHub", self.language),
                    message,
                    parent=dialog,
                )
                return
            if direction == "upload":
                confirmed = messagebox.askyesno(
                    translate("上传本机数据", self.language),
                    translate(
                        "将本机同步范围内的数据写入 GitHub，并覆盖云端当前同步文件。GitHub 会保留每次提交的历史版本。继续吗？",
                        self.language,
                    ),
                    parent=dialog,
                )
            elif confirmed_download:
                confirmed = True
            else:
                confirmed = messagebox.askyesno(
                    translate("从 GitHub 恢复", self.language),
                    translate(
                    "将用 GitHub 云端快照替换本机账本；快照未包含的账本内容恢复后不会出现在本机。备份包中未包含的付款方式、Skill 和小票图片会保留本机现有内容。API 配置、GitHub 授权、界面语言等本机设置保持不变。恢复前会自动备份本机全部账本及可同步数据（不含密钥、令牌和本机偏好），完成后软件将重启。继续吗？",
                        self.language,
                    ),
                    parent=dialog,
                )
            if not confirmed:
                return
            github_sync_busy["value"] = True
            if direction == "download":
                self._github_restore_in_progress = True
                with self._github_auto_sync_state_lock:
                    self._github_auto_sync_pending = False
                self.send_button.configure(state="disabled")
                self.input_box.configure(state="disabled")
            upload_button.configure(state="disabled")
            restore_button.configure(state="disabled")
            github_status.configure(
                text=translate(
                    "正在打包并上传本机数据…" if direction == "upload" else "正在下载并校验云端数据…",
                    self.language,
                )
            )

            def sync_worker() -> None:
                try:
                    client = GitHubClient(
                        credentials["access_token"],
                        refresh_token=credentials["refresh_token"],
                        client_id=GITHUB_APP_CLIENT_ID,
                        token_store=github_token_store,
                    )
                    if direction == "upload":
                        with self._github_upload_lock, github_sync_process_lock():
                            settings_store = GitHubSyncSettingsStore()
                            current_settings = settings_store.load()
                            # Manual upload is an explicit replacement action. Read the
                            # latest revision now, then still use GitHub's SHA precondition
                            # so a concurrent update cannot slip between read and write.
                            expected_sha = client.bundle_sha(repository)
                            with tempfile.TemporaryDirectory(prefix="household-github-upload-") as temp_name:
                                bundle_path = Path(temp_name) / "sync-bundle.zip"
                                sync_revision = local_revision(self.database_path, **self._cloud_stores())
                                bundle = create_sync_bundle(
                                    self.database_path,
                                    bundle_path,
                                    receipt_image_directory=self.database_path.parent / "receipt_images",
                                )
                                new_sha = client.upload_bundle(
                                    repository, bundle, expected_sha=expected_sha
                                )
                            settings_store.save(
                                repository_name=current_settings.get(
                                    "repository_name", DEFAULT_BACKUP_REPOSITORY_NAME
                                ),
                                repository=repository,
                                last_sync_sha=new_sha,
                            )
                            self._mark_cloud_checkpoint('github', repository, new_sha, sync_revision)
                        message = translate("本机同步数据已上传到 GitHub。", self.language)
                        result_backup = ""
                    else:
                        with self._github_upload_lock, github_sync_process_lock():
                            bundle, cloud_sha = client.download_bundle_with_revision(repository)
                            result_backup = str(
                                restore_sync_bundle(
                                    bundle,
                                    self.database_path,
                                    receipt_image_directory=self.database_path.parent / "receipt_images",
                                )
                            )
                            settings_store = GitHubSyncSettingsStore()
                            current_settings = settings_store.load()
                            settings_store.save(
                                repository_name=current_settings.get(
                                    "repository_name", DEFAULT_BACKUP_REPOSITORY_NAME
                                ),
                                repository=repository,
                                last_sync_sha=cloud_sha,
                            )
                            self._mark_cloud_checkpoint('github', repository, cloud_sha, None)
                            self._pull_state().resume_downloads()
                        message = translate(
                            "云端数据已恢复。本机恢复前备份：{path}。软件即将重启。",
                            self.language,
                        ).format(path=result_backup)
                    dialog.after(0, lambda: sync_done(message, error="", restart=(direction == "download")))
                except Exception as exc:
                    error = str(exc)
                    message = translate("GitHub 数据同步失败：{error}", self.language).format(
                        error=translate(error, self.language)
                    )
                    dialog.after(0, lambda: sync_done(message, error=error, restart=False))

            def sync_done(message: str, *, error: str, restart: bool) -> None:
                github_sync_busy["value"] = False
                if direction == "download" and error:
                    self._github_restore_in_progress = False
                    self.send_button.configure(state="normal")
                    self.input_box.configure(state="normal")
                github_status.configure(text=message)
                try:
                    connected = is_github_app_user_token(github_token_store.load()) and bool(
                        github_saved_settings.get("repository")
                    )
                except SecureSettingsError:
                    connected = False
                if connected:
                    upload_button.configure(state="normal")
                    restore_button.configure(state="normal")
                if error:
                    messagebox.showerror(
                        translate("GitHub 同步失败", self.language), message, parent=dialog
                    )
                elif restart:
                    messagebox.showinfo(
                        translate("恢复完成", self.language), message, parent=dialog
                    )
                    # The restore confirmation already included restarting the app.
                    # Asking again can leave this old process open after its database
                    # has been replaced, making the restore appear not to have worked.
                    self.root.after(700, lambda: self.restart_application(require_confirmation=False))
                else:
                    messagebox.showinfo(
                        translate("同步完成", self.language), message, parent=dialog
                    )

            threading.Thread(target=sync_worker, name="github-ledger-sync", daemon=True).start()

        upload_button = ttk.Button(
            github_card,
            text=translate("上传本机数据", self.language),
            command=lambda: sync_github("upload"),
            state="normal" if github_saved_token_is_app and github_saved_settings.get("repository") else "disabled",
        )
        upload_button.grid(row=9, column=1, sticky="w", padx=(8, 0), pady=(3, 0))
        restore_button = ttk.Button(
            github_card,
            text=translate("从 GitHub 恢复并重启", self.language),
            command=lambda: sync_github("download"),
            state="normal" if github_saved_token_is_app and github_saved_settings.get("repository") else "disabled",
        )
        restore_button.grid(row=9, column=2, columnspan=2, sticky="w", padx=(8, 0), pady=(3, 0))

        gitee_card = ttk.Frame(data_panel, style="SettingsPanel.TFrame", padding=(16, 14))
        gitee_card.grid(row=6, column=0, sticky="ew", pady=(0, 12))
        gitee_card.columnconfigure(1, weight=1)
        ttk.Label(
            gitee_card,
            text=translate("Gitee 同步", self.language),
            style="SettingsSection.TLabel",
        ).grid(row=0, column=0, columnspan=4, sticky="w", pady=(0, 6))
        ttk.Label(
            gitee_card,
            text=translate(
                "使用自己的 Gitee 私有仓库备份上方选中的数据。连接时需要在 Gitee 创建个人访问令牌；软件不会读取你的 Gitee 密码。",
                self.language,
            ),
            style="SettingsHint.TLabel",
            wraplength=700,
            justify="left",
        ).grid(row=1, column=0, columnspan=4, sticky="w", pady=(0, 8))
        gitee_auto_sync_var = tk.BooleanVar(value=self.gitee_auto_sync_enabled)
        gitee_auto_sync_status = ttk.Label(
            gitee_card,
            text=(
                translate(self.gitee_auto_sync_settings_error, self.language)
                if self.gitee_auto_sync_settings_error
                else translate(
                    "Gitee 自动同步已开启。" if self.gitee_auto_sync_enabled else "Gitee 自动同步已关闭。",
                    self.language,
                )
            ),
            style="SettingsStatus.TLabel",
            wraplength=700,
            justify="left",
        )

        def mark_gitee_auto_sync_pending() -> None:
            gitee_auto_sync_status.configure(
                text=translate("更改将在点击应用或确认后保存。", self.language)
            )

        ttk.Checkbutton(
            gitee_card,
            text=translate("每笔记账后自动同步到 Gitee", self.language),
            variable=gitee_auto_sync_var,
            command=mark_gitee_auto_sync_pending,
        ).grid(row=2, column=0, columnspan=4, sticky="w", pady=(2, 0))
        ttk.Label(
            gitee_card,
            text=translate(
                "记账成功后在后台上传账本、支付规则、自定义 Skill 和已保存的小票图片。未连接时只保存本机；多台设备的修改不会自动合并。",
                self.language,
            ),
            style="SettingsHint.TLabel",
            wraplength=700,
            justify="left",
        ).grid(row=3, column=0, columnspan=4, sticky="w", pady=(3, 2))
        gitee_auto_sync_status.grid(row=4, column=0, columnspan=4, sticky="w", pady=(2, 4))

        gitee_settings_store = GiteeSyncSettingsStore()
        gitee_token_store = GiteeTokenStore()
        try:
            gitee_saved_settings = gitee_settings_store.load()
            gitee_saved_token = gitee_token_store.load()
            gitee_settings_error = ""
        except (GiteeSyncError, SecureSettingsError) as exc:
            gitee_saved_settings = {
                "repository_name": DEFAULT_GITEE_BACKUP_REPOSITORY_NAME,
                "repository": "",
                "last_sync_sha": "",
            }
            gitee_saved_token = ""
            gitee_settings_error = str(exc)
        gitee_connected = bool(gitee_saved_token and gitee_saved_settings.get("repository"))
        gitee_status = ttk.Label(
            gitee_card,
            text=(
                translate("Gitee 设置无法读取：{error}", self.language).format(
                    error=translate(gitee_settings_error, self.language)
                )
                if gitee_settings_error
                else (
                    translate("已连接 Gitee：{repository}", self.language).format(
                        repository=gitee_saved_settings["repository"]
                    )
                    if gitee_connected
                    else translate("尚未连接 Gitee；点击下方按钮创建令牌并连接。", self.language)
                )
            ),
            style="SettingsStatus.TLabel",
            wraplength=700,
            justify="left",
        )
        gitee_status.grid(row=5, column=0, columnspan=4, sticky="w", pady=(7, 4))
        ttk.Label(
            gitee_card,
            text=translate(
                "云备份内容由上方勾选项决定；API 密钥、本机偏好、历史备份和 Gitee 令牌不上传。同步包未额外加密。Gitee 免费版单文件上限为 50 MB，本软件将同步包限制在 45 MiB。",
                self.language,
            ),
            style="SettingsHint.TLabel",
            wraplength=700,
            justify="left",
        ).grid(row=6, column=0, columnspan=4, sticky="w", pady=(3, 3))
        ttk.Label(
            gitee_card,
            text=translate(
                "Gitee 令牌权限较宽；创建时勾选 user_info 和 projects，仅在自己的设备保存，并可随时在 Gitee 撤销。多台设备不会自动合并；一台上传后，另一台应先恢复。",
                self.language,
            ),
            style="SettingsHint.TLabel",
            wraplength=700,
            justify="left",
        ).grid(row=7, column=0, columnspan=4, sticky="w", pady=(0, 8))

        gitee_sync_busy = {"value": False}

        def start_gitee_connection() -> None:
            if gitee_sync_busy["value"]:
                return
            token_dialog = tk.Toplevel(dialog)
            token_dialog.title(translate("连接 Gitee", self.language))
            token_dialog.transient(dialog)
            token_dialog.resizable(False, False)
            token_dialog.protocol(
                "WM_DELETE_WINDOW",
                lambda: token_dialog.destroy() if not gitee_sync_busy["value"] else None,
            )
            token_panel = ttk.Frame(token_dialog, style="SettingsPanel.TFrame", padding=22)
            token_panel.pack(fill="both", expand=True)
            ttk.Label(
                token_panel,
                text=translate(
                    "先创建 Gitee 个人访问令牌，至少勾选 user_info 和 projects。令牌用于识别账号、创建私有仓库及读写备份文件。",
                    self.language,
                ),
                style="SettingsHint.TLabel",
                wraplength=520,
                justify="left",
            ).pack(fill="x", pady=(0, 8))
            ttk.Button(
                token_panel,
                text=translate("打开 Gitee 令牌设置", self.language),
                command=lambda: webbrowser.open(GITEE_TOKEN_SETTINGS_URL),
            ).pack(anchor="w", pady=(0, 12))
            ttk.Label(token_panel, text=translate("粘贴访问令牌", self.language), style="SettingsHint.TLabel").pack(
                anchor="w", pady=(0, 4)
            )
            token_row = ttk.Frame(token_panel, style="SettingsPanel.TFrame")
            token_row.pack(fill="x", pady=(0, 14))
            token_entry = ttk.Entry(token_row, show="●", width=54)
            token_entry.pack(side="left", fill="x", expand=True)
            token_visible = tk.BooleanVar(value=False)
            ttk.Checkbutton(
                token_row,
                text=translate("显示", self.language),
                variable=token_visible,
                command=lambda: token_entry.configure(show="" if token_visible.get() else "●"),
            ).pack(side="left", padx=(8, 0))
            token_actions = ttk.Frame(token_panel, style="SettingsPanel.TFrame")
            token_actions.pack(fill="x")
            token_status = ttk.Label(token_panel, text="", style="SettingsStatus.TLabel", wraplength=520)
            token_status.pack(fill="x", pady=(10, 0))

            def finish_gitee_connection(
                message: str,
                *,
                success: bool = False,
                error: str = "",
                repository: str = "",
            ) -> None:
                gitee_sync_busy["value"] = False
                gitee_status.configure(text=message)
                if success:
                    gitee_saved_settings["repository_name"] = DEFAULT_GITEE_BACKUP_REPOSITORY_NAME
                    gitee_saved_settings["repository"] = repository
                    gitee_saved_settings["last_sync_sha"] = ""
                    gitee_upload_button.configure(state="normal")
                    gitee_restore_button.configure(state="normal")
                    self.root.after(0, self._start_startup_cloud_pull)
                if token_dialog.winfo_exists():
                    token_dialog.destroy()
                if error:
                    messagebox.showerror(
                        translate("Gitee 连接失败", self.language),
                        translate("Gitee 连接失败：{error}", self.language).format(
                            error=translate(error, self.language)
                        ),
                        parent=dialog,
                    )

            def submit_gitee_token() -> None:
                token = token_entry.get().strip()
                if not token:
                    messagebox.showwarning(
                        translate("缺少 Gitee 令牌", self.language),
                        translate("请先创建并粘贴 Gitee 个人访问令牌。", self.language),
                        parent=token_dialog,
                    )
                    return
                token_entry.delete(0, "end")
                gitee_sync_busy["value"] = True
                token_status.configure(text=translate("正在连接 Gitee 并检查私有仓库…", self.language))
                for button in token_actions.winfo_children():
                    button.configure(state="disabled")

                def connect_worker() -> None:
                    connected_repository = ""
                    try:
                        client = GiteeClient(token)
                        user = client.current_user()
                        login = str(user.get("login") or "").strip()
                        if not login:
                            raise GiteeSyncError("Gitee 未返回账户名称；请确认令牌有 user_info 权限。")
                        repo_name = (
                            gitee_saved_settings.get("repository_name")
                            or DEFAULT_GITEE_BACKUP_REPOSITORY_NAME
                        )
                        repository, created = client.ensure_private_repository(login, repo_name)
                        connected_repository = repository
                        gitee_token_store.save(token)
                        # Keep auto-sync from overwriting a pre-existing snapshot until
                        # the user explicitly chooses restore or manual upload.
                        gitee_settings_store.save(
                            repository_name=repo_name,
                            repository=repository,
                            last_sync_sha="",
                        )
                        remote_sha = client.bundle_sha(repository)
                        if remote_sha:
                            result = translate(
                                "已连接 Gitee；该私有仓库已有备份，请选择上传或恢复。",
                                self.language,
                            )
                        else:
                            with self._github_upload_lock, github_sync_process_lock():
                                with tempfile.TemporaryDirectory(prefix="household-gitee-upload-") as temp_name:
                                    bundle_path = Path(temp_name) / "sync-bundle.zip"
                                    sync_revision = local_revision(self.database_path, **self._cloud_stores())
                                    bundle = create_sync_bundle(
                                        self.database_path,
                                        bundle_path,
                                        receipt_image_directory=self.database_path.parent / "receipt_images",
                                        max_bundle_bytes=MAX_GITEE_SYNC_BUNDLE_BYTES,
                                        max_bundle_error="Gitee 同步包超过 45 MiB；请减少小票图片后重试。",
                                    )
                                    new_sha = client.upload_bundle(repository, bundle, expected_sha=None)
                                gitee_settings_store.save(
                                    repository_name=repo_name,
                                    repository=repository,
                                    last_sync_sha=new_sha,
                                )
                                self._mark_cloud_checkpoint('gitee', repository, new_sha, sync_revision)
                            result = translate(
                                "Gitee 已连接，私有仓库已创建并上传本机同步数据。"
                                if created
                                else "Gitee 已连接，同步文件已首次上传。",
                                self.language,
                            )
                        token_dialog.after(
                            0,
                            lambda: finish_gitee_connection(
                                result, success=True, repository=repository
                            ),
                        )
                    except Exception as exc:
                        error = str(exc)
                        message = translate("Gitee 连接失败：{error}", self.language).format(
                            error=translate(error, self.language)
                        )
                        token_dialog.after(
                            0,
                            lambda: finish_gitee_connection(
                                message,
                                success=bool(connected_repository),
                                repository=connected_repository,
                                error=error,
                            ),
                        )

                threading.Thread(target=connect_worker, name="gitee-connect", daemon=True).start()

            ttk.Button(
                token_actions,
                text=translate("连接并备份", self.language),
                style="Send.TButton",
                command=submit_gitee_token,
            ).pack(side="left")
            ttk.Button(
                token_actions,
                text=translate("取消", self.language),
                command=token_dialog.destroy,
            ).pack(side="right")
            token_dialog.update_idletasks()
            width = max(580, token_dialog.winfo_reqwidth())
            height = token_dialog.winfo_reqheight()
            x = max(0, token_dialog.winfo_screenwidth() // 2 - width // 2)
            y = max(0, token_dialog.winfo_screenheight() // 2 - height // 2)
            token_dialog.geometry(f"{width}x{height}+{x}+{y}")
            token_dialog.grab_set()
            token_entry.focus_set()

        def sync_gitee(direction: str) -> None:
            if gitee_sync_busy["value"]:
                return
            if direction == "download" and (self.busy or self._recurring_processing):
                messagebox.showinfo(
                    translate("稍后重试", self.language),
                    translate("记账或定期收支正在处理中，请等处理完成后再从 Gitee 恢复。", self.language),
                    parent=dialog,
                )
                return
            repository = gitee_saved_settings.get("repository", "")
            try:
                token = gitee_token_store.load()
            except SecureSettingsError as exc:
                gitee_status.configure(
                    text=translate("Gitee 连接失败：{error}", self.language).format(
                        error=translate(str(exc), self.language)
                    )
                )
                return
            if not token or not repository:
                messagebox.showwarning(
                    translate("尚未连接 Gitee", self.language),
                    translate("请先创建令牌并连接 Gitee。", self.language),
                    parent=dialog,
                )
                return
            if direction == "upload":
                confirmed = messagebox.askyesno(
                    translate("上传本机数据", self.language),
                    translate(
                        "将本机同步范围内的数据写入 Gitee，并覆盖云端当前同步文件。Gitee 会保留仓库提交历史。继续吗？",
                        self.language,
                    ),
                    parent=dialog,
                )
            else:
                confirmed = messagebox.askyesno(
                    translate("从 Gitee 恢复", self.language),
                    translate(
                        "将用 Gitee 云端快照替换本机账本；快照未包含的账本内容恢复后不会出现在本机。备份包中未包含的付款方式、Skill 和小票图片会保留本机现有内容。API 配置、Gitee 令牌、界面语言等本机设置保持不变。恢复前会自动备份本机全部账本及可同步数据（不含密钥、令牌和本机偏好），完成后软件将重启。继续吗？",
                        self.language,
                    ),
                    parent=dialog,
                )
            if not confirmed:
                return
            gitee_sync_busy["value"] = True
            if direction == "download":
                self._github_restore_in_progress = True
                with self._github_auto_sync_state_lock:
                    self._github_auto_sync_pending = False
                with self._gitee_auto_sync_state_lock:
                    self._gitee_auto_sync_pending = False
                self.send_button.configure(state="disabled")
                self.input_box.configure(state="disabled")
            gitee_connect_button.configure(state="disabled")
            gitee_upload_button.configure(state="disabled")
            gitee_restore_button.configure(state="disabled")
            gitee_status.configure(
                text=translate(
                    "正在打包并上传本机数据…" if direction == "upload" else "正在下载并校验云端数据…",
                    self.language,
                )
            )

            def sync_worker() -> None:
                try:
                    client = GiteeClient(token)
                    if direction == "upload":
                        with self._github_upload_lock, github_sync_process_lock():
                            current_settings = gitee_settings_store.load()
                            expected_sha = client.bundle_sha(repository)
                            with tempfile.TemporaryDirectory(prefix="household-gitee-upload-") as temp_name:
                                bundle_path = Path(temp_name) / "sync-bundle.zip"
                                sync_revision = local_revision(self.database_path, **self._cloud_stores())
                                bundle = create_sync_bundle(
                                    self.database_path,
                                    bundle_path,
                                    receipt_image_directory=self.database_path.parent / "receipt_images",
                                    max_bundle_bytes=MAX_GITEE_SYNC_BUNDLE_BYTES,
                                    max_bundle_error="Gitee 同步包超过 45 MiB；请减少小票图片后重试。",
                                )
                                new_sha = client.upload_bundle(repository, bundle, expected_sha=expected_sha)
                            gitee_settings_store.save(
                                repository_name=current_settings.get(
                                    "repository_name", DEFAULT_GITEE_BACKUP_REPOSITORY_NAME
                                ),
                                repository=repository,
                                last_sync_sha=new_sha,
                            )
                            self._mark_cloud_checkpoint('gitee', repository, new_sha, sync_revision)
                        message = translate("本机同步数据已上传到 Gitee。", self.language)
                        result_backup = ""
                    else:
                        with self._github_upload_lock, github_sync_process_lock():
                            bundle, cloud_sha = client.download_bundle_with_revision(repository)
                            result_backup = str(
                                restore_sync_bundle(
                                    bundle,
                                    self.database_path,
                                    receipt_image_directory=self.database_path.parent / "receipt_images",
                                    backup_provider="gitee",
                                )
                            )
                            current_settings = gitee_settings_store.load()
                            gitee_settings_store.save(
                                repository_name=current_settings.get(
                                    "repository_name", DEFAULT_GITEE_BACKUP_REPOSITORY_NAME
                                ),
                                repository=repository,
                                last_sync_sha=cloud_sha,
                            )
                            self._mark_cloud_checkpoint('gitee', repository, cloud_sha, None)
                        message = translate(
                            "云端数据已恢复。本机恢复前备份：{path}。软件即将重启。",
                            self.language,
                        ).format(path=result_backup)
                    dialog.after(0, lambda: sync_done(message, error="", restart=(direction == "download")))
                except Exception as exc:
                    error = str(exc)
                    message = translate("Gitee 数据同步失败：{error}", self.language).format(
                        error=translate(error, self.language)
                    )
                    dialog.after(0, lambda: sync_done(message, error=error, restart=False))

            def sync_done(message: str, *, error: str, restart: bool) -> None:
                gitee_sync_busy["value"] = False
                if direction == "download" and error:
                    self._github_restore_in_progress = False
                    self.send_button.configure(state="normal")
                    self.input_box.configure(state="normal")
                gitee_status.configure(text=message)
                try:
                    connected_now = bool(
                        gitee_token_store.load()
                        and gitee_settings_store.load().get("repository")
                    )
                except (GiteeSyncError, SecureSettingsError):
                    connected_now = False
                if connected_now:
                    gitee_connect_button.configure(state="normal")
                    gitee_upload_button.configure(state="normal")
                    gitee_restore_button.configure(state="normal")
                if error:
                    messagebox.showerror(translate("Gitee 同步失败", self.language), message, parent=dialog)
                elif restart:
                    messagebox.showinfo(translate("恢复完成", self.language), message, parent=dialog)
                    self.root.after(700, lambda: self.restart_application(require_confirmation=False))
                else:
                    messagebox.showinfo(translate("同步完成", self.language), message, parent=dialog)

            threading.Thread(target=sync_worker, name="gitee-ledger-sync", daemon=True).start()

        gitee_connect_button = ttk.Button(
            gitee_card,
            text=translate("连接 Gitee 并备份", self.language),
            style="Send.TButton",
            command=start_gitee_connection,
        )
        gitee_connect_button.grid(row=8, column=0, sticky="w", pady=(4, 0))
        gitee_upload_button = ttk.Button(
            gitee_card,
            text=translate("上传本机数据到 Gitee", self.language),
            command=lambda: sync_gitee("upload"),
            state="normal" if gitee_connected else "disabled",
        )
        gitee_upload_button.grid(row=8, column=1, sticky="w", padx=(8, 0), pady=(4, 0))
        gitee_restore_button = ttk.Button(
            gitee_card,
            text=translate("从 Gitee 恢复并重启", self.language),
            command=lambda: sync_gitee("download"),
            state="normal" if gitee_connected else "disabled",
        )
        gitee_restore_button.grid(row=8, column=2, columnspan=2, sticky="w", padx=(8, 0), pady=(4, 0))

        backup_card = ttk.Frame(data_panel, style="SettingsPanel.TFrame", padding=(16, 14))
        backup_card.grid(row=7, column=0, sticky="ew", pady=(0, 12))
        backup_card.columnconfigure(0, weight=1)
        ttk.Label(backup_card, text="数据库备份", style="SettingsSection.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(
            backup_card,
            text=f"备份保存在：{self.database_path.parent.parent / 'backups'}",
            style="SettingsHint.TLabel",
            wraplength=650,
            justify="left",
        ).grid(row=1, column=0, sticky="w", pady=(4, 10))
        ttk.Button(
            backup_card,
            text="创建账本备份",
            style="Send.TButton",
            command=lambda: self.create_database_backup(parent=dialog),
        ).grid(row=2, column=0, sticky="w")

        appearance_card = RoundedPanel(appearance_page, padding=26)
        appearance_card.pack(fill="both", expand=True)
        appearance_panel = appearance_card.body
        ttk.Label(appearance_panel, text="外观", style="SettingsTitle.TLabel").pack(anchor="w", pady=(0, 12))
        ttk.Label(appearance_panel, text="选择你喜欢的明暗外观。跟随系统会自动适应电脑的外观设置。",
                  style="SettingsHint.TLabel", wraplength=640).pack(anchor="w", pady=(0, 12))
        appearance_combo = ttk.Combobox(appearance_panel, state="readonly", width=26,
                                       values=tuple(label for _mode, label in APPEARANCE_CHOICES))
        appearance_combo.pack(anchor="w")
        appearance_combo.current(next(index for index, item in enumerate(APPEARANCE_CHOICES)
                                      if item[0] == self.appearance_mode))
        ttk.Label(appearance_panel, text="点击应用或确认后生效；取消不会改变当前外观。",
                  style="SettingsHint.TLabel", wraplength=640).pack(anchor="w", pady=(18, 0))

        language_panel = ttk.Frame(language_page, style="SettingsPanel.TFrame", padding=18)
        language_panel.pack(fill="both", expand=True)
        language_panel.columnconfigure(0, weight=1)
        ttk.Label(language_panel, text="语言", style="SettingsTitle.TLabel").grid(
            row=0, column=0, sticky="w"
        )
        ttk.Label(
            language_panel,
            text="选择软件界面显示语言。选择后点击应用或确认才会保存；语言切换会清空两个 Agent 的对话历史和待确认草稿。",
            style="SettingsHint.TLabel",
            wraplength=760,
        ).grid(row=1, column=0, sticky="w", pady=(5, 12))
        ttk.Label(
            language_panel,
            text="更改只影响软件界面；账户名、类别和账本记录保留原文。",
            style="SettingsHint.TLabel",
            wraplength=760,
        ).grid(row=2, column=0, sticky="w", pady=(0, 20))
        ttk.Label(language_panel, text="显示语言", style="SettingsSection.TLabel").grid(
            row=3, column=0, sticky="w", pady=(0, 6)
        )
        language_name_by_code = dict(LANGUAGE_CHOICES)
        language_var = tk.StringVar(value=language_name_by_code.get(self.language, "简体中文"))
        language_combo = ttk.Combobox(
            language_panel,
            textvariable=language_var,
            values=tuple(label for _code, label in LANGUAGE_CHOICES),
            state="readonly",
            width=24,
        )
        language_combo.grid(row=4, column=0, sticky="w")
        language_combo.current(next(
            (index for index, (code, _label) in enumerate(LANGUAGE_CHOICES) if code == self.language),
            0,
        ))
        language_status = ttk.Label(language_panel, text="", style="SettingsStatus.TLabel")
        language_status.grid(row=5, column=0, sticky="w", pady=(12, 0))

        def change_language(_event: Any = None) -> None:
            selected_index = language_combo.current()
            if selected_index < 0 or selected_index >= len(LANGUAGE_CHOICES):
                return
            selected_language = LANGUAGE_CHOICES[selected_index][0]
            language_status.configure(
                text=(
                    translate("更改将在点击应用或确认后保存。", self.language)
                    if selected_language != self.language
                    else ""
                )
            )

        language_combo.bind("<<ComboboxSelected>>", change_language)

        loading_form = False

        def profile_index(profile_id: str) -> int:
            for index, profile in enumerate(self.api_profiles):
                if profile["id"] == profile_id:
                    return index
            return 0

        def refresh_profile_list() -> None:
            values = [profile["name"] or "未命名服务" for profile in self.api_profiles]
            profile_combo.configure(values=values)
            profile_combo.current(profile_index(self.active_api_profile_id))
            refresh_agent_model_choices()

        def load_active_profile() -> None:
            nonlocal loading_form
            profile = self._active_api_profile()
            loading_form = True
            name_var.set(profile["name"])
            url_var.set(profile["api_url"])
            model_var.set(profile["model"])
            key_var.set(profile["api_key"])
            thinking_enabled_var.set(profile.get("thinking_enabled", False))
            stored_effort = profile.get("reasoning_effort", "low")
            reasoning_effort_var.set(
                next((label for label, value in effort_labels.items() if value == stored_effort), "低（low）")
            )
            loading_form = False
            refresh_thinking_controls()
            refresh_profile_list()

        def refresh_thinking_controls(*_args: Any) -> None:
            deepseek_enabled = is_deepseek_api(url_var.get().strip())
            thinking_check.configure(state="normal" if deepseek_enabled else "disabled")
            effort_combo.configure(
                state="readonly" if deepseek_enabled and thinking_enabled_var.get() else "disabled"
            )

        def collect_active_profile_draft() -> bool:
            profile = self._active_api_profile()
            profile["name"] = name_var.get().strip() or "未命名服务"
            profile["api_url"] = url_var.get().strip()
            profile["model"] = model_var.get().strip()
            profile["api_key"] = key_var.get().strip()
            profile["thinking_enabled"] = thinking_enabled_var.get()
            profile["reasoning_effort"] = effort_labels.get(reasoning_effort_var.get(), "low")
            status_label.configure(text=translate("API 服务更改尚未保存；点击应用或确认后生效。", self.language))
            refresh_profile_list()
            return True

        def mark_profile_pending(_event: Any = None) -> None:
            if loading_form:
                return
            status_label.configure(text=translate("有未保存的 API 服务更改；点击应用或确认后保存。", self.language))

        def flush_profile_draft() -> bool:
            return collect_active_profile_draft()

        def selected_profile_changed(_event: Any = None) -> None:
            selected_index = profile_combo.current()
            if selected_index < 0 or selected_index >= len(self.api_profiles):
                return
            next_id = self.api_profiles[selected_index]["id"]
            if next_id == self.active_api_profile_id:
                return
            if not flush_profile_draft():
                refresh_profile_list()
                return
            self.active_api_profile_id = next_id
            load_active_profile()
            status_label.configure(
                text=translate("已切换 API 服务草稿；点击应用或确认后保存。", self.language)
            )

        def add_profile() -> None:
            if not flush_profile_draft():
                return
            profile = {
                "id": uuid.uuid4().hex,
                "name": f"新服务 {len(self.api_profiles)}",
                "api_url": "",
                "model": "",
                "api_key": "",
                "thinking_enabled": False,
                "reasoning_effort": "low",
            }
            updated_profiles = [*self.api_profiles, profile]
            self.api_profiles = updated_profiles
            self.active_api_profile_id = profile["id"]
            load_active_profile()
            refresh_agent_model_choices()
            name_entry.focus_set()
            status_label.configure(text=translate("新服务已创建为草稿；点击应用或确认后保存。", self.language))

        def delete_profile() -> None:
            if len(self.api_profiles) <= 1:
                messagebox.showinfo("无法删除", "至少保留一个 API 服务配置。", parent=dialog)
                return
            profile = self._active_api_profile()
            if not confirm_delete_once(
                dialog,
                title="删除 API 服务",
                target=f"API 服务“{profile['name']}”及其已保存密钥",
                impact="使用此服务的 Agent 会改用其他服务，并清除对应的模型对话上下文。",
            ):
                return
            if not flush_profile_draft():
                return
            remaining_profiles = [item for item in self.api_profiles if item["id"] != profile["id"]]
            next_active_id = remaining_profiles[0]["id"]
            for mode in ("bookkeeping", "food_health"):
                if self.agent_profile_ids.get(mode) == profile["id"]:
                    self.agent_profile_ids[mode] = next_active_id
                if self.agent_vision_profile_ids.get(mode) == profile["id"]:
                    self.agent_vision_profile_ids[mode] = next_active_id
            self.api_profiles = remaining_profiles
            self.active_api_profile_id = next_active_id
            load_active_profile()
            refresh_agent_model_choices()
            status_label.configure(text=translate("API 服务已从草稿移除；点击应用或确认后保存。", self.language))

        def capture_settings_baseline() -> dict[str, Any]:
            return {
                "api_profiles": deepcopy(self.api_profiles),
                "active_api_profile_id": self.active_api_profile_id,
                "agent_profile_ids": dict(self.agent_profile_ids),
                "agent_vision_profile_ids": dict(self.agent_vision_profile_ids),
                "loaded_skill": deepcopy(self.loaded_skill),
                "loaded_food_health_skill": deepcopy(self.loaded_food_health_skill),
                "api_profile_settings_error": self.api_profile_settings_error,
                "skill_settings_error": self.skill_settings_error,
                "food_health_skill_settings_error": self.food_health_skill_settings_error,
                "receipt_images": bool(self.save_receipt_images_locally),
                "receipt_image_settings_error": self.receipt_image_settings_error,
                "backup_scope": backup_scope_selection(),
                "github_auto_sync": bool(self.github_auto_sync_enabled),
                "github_auto_sync_settings_error": self.github_auto_sync_settings_error,
                "gitee_auto_sync": bool(self.gitee_auto_sync_enabled),
                "gitee_auto_sync_settings_error": self.gitee_auto_sync_settings_error,
                "language": self.language,
                "appearance": self.appearance_mode,
            }

        settings_baseline = capture_settings_baseline()

        def set_profile_from_baseline(value: dict[str, Any]) -> None:
            self.api_profiles = deepcopy(value["api_profiles"])
            self.active_api_profile_id = str(value["active_api_profile_id"])
            self.agent_profile_ids = dict(value["agent_profile_ids"])
            self.agent_vision_profile_ids = dict(value["agent_vision_profile_ids"])

        def skill_path(skill: dict[str, str] | None) -> str | None:
            return str(skill["path"]) if skill and skill.get("path") else None

        def rollback_persisted_settings(value: dict[str, Any]) -> list[str]:
            rollback_errors: list[str] = []
            operations = (
                (
                    "API 服务",
                    lambda: self.api_profile_store.save(
                        value["api_profiles"],
                        value["active_api_profile_id"],
                        value["agent_profile_ids"],
                        value["agent_vision_profile_ids"],
                    ),
                ),
                ("云备份范围", lambda: backup_scope_store.save(value["backup_scope"])),
                ("小票图片", lambda: self.receipt_image_settings_store.save_enabled(value["receipt_images"])),
                ("GitHub 自动同步", lambda: self.github_auto_sync_settings_store.save_enabled(value["github_auto_sync"])),
                ("Gitee 自动同步", lambda: self.gitee_auto_sync_settings_store.save_enabled(value["gitee_auto_sync"])),
                ("语言", lambda: save_language(value["language"])),
                ("外观", lambda: save_appearance(value["appearance"])),
            )
            for label, operation in operations:
                try:
                    operation()
                except Exception as exc:
                    rollback_errors.append(f"{label}：{exc}")
            for mode, key in (
                ("bookkeeping", "loaded_skill"),
                ("food_health", "loaded_food_health_skill"),
            ):
                try:
                    skill = value[key]
                    store = agent_skill_stores[mode]
                    current_skill = agent_skill_drafts[mode]
                    if skill_path(current_skill) == skill_path(skill):
                        continue
                    if skill and skill.get("path"):
                        store.save_path(skill["path"])
                    else:
                        store.clear()
                except Exception as exc:
                    rollback_errors.append(f"{agent_labels[mode]} Skill：{exc}")
            return rollback_errors

        def cancel_settings() -> None:
            set_profile_from_baseline(settings_baseline)
            agent_skill_drafts["bookkeeping"] = deepcopy(settings_baseline["loaded_skill"])
            agent_skill_drafts["food_health"] = deepcopy(settings_baseline["loaded_food_health_skill"])
            self.loaded_skill = deepcopy(settings_baseline["loaded_skill"])
            self.loaded_food_health_skill = deepcopy(settings_baseline["loaded_food_health_skill"])
            self.api_profile_settings_error = settings_baseline["api_profile_settings_error"]
            self.skill_settings_error = settings_baseline["skill_settings_error"]
            self.food_health_skill_settings_error = settings_baseline["food_health_skill_settings_error"]
            self.save_receipt_images_locally = settings_baseline["receipt_images"]
            self.receipt_image_settings_error = settings_baseline["receipt_image_settings_error"]
            self.github_auto_sync_enabled = settings_baseline["github_auto_sync"]
            self.github_auto_sync_settings_error = settings_baseline["github_auto_sync_settings_error"]
            self.gitee_auto_sync_enabled = settings_baseline["gitee_auto_sync"]
            self.gitee_auto_sync_settings_error = settings_baseline["gitee_auto_sync_settings_error"]
            self.language = settings_baseline["language"]
            set_language(self.language)
            self.status.configure(text=translate("未应用的设置更改已取消。", self.language))
            dialog.destroy()

        def apply_current_settings(*, close_after_apply: bool) -> None:
            nonlocal settings_baseline
            if not flush_profile_draft():
                messagebox.showerror(
                    "保存失败",
                    status_label.cget("text") or "设置保存失败，请检查本机配置目录权限后重试。",
                    parent=dialog,
                )
                return
            selected_language = next(
                (
                    code
                    for code, label in LANGUAGE_CHOICES
                    if label == language_var.get()
                ),
                settings_baseline["language"],
            )
            if selected_language != settings_baseline["language"]:
                if self.busy:
                    messagebox.showinfo(
                        translate("无法切换语言", self.language),
                        translate("当前任务正在运行；请等任务完成后再切换语言。", self.language),
                        parent=dialog,
                    )
                    return
                if not messagebox.askyesno(
                    translate("确认切换语言", self.language),
                    translate(
                        "切换语言会清空记账和饮食健康 Agent 的对话历史、待确认草稿，以及尚未发送的文字和图片。是否继续？",
                        self.language,
                    ),
                    parent=dialog,
                ):
                    return

            selected_appearance = APPEARANCE_CHOICES[max(0, appearance_combo.current())][0]
            old_state = settings_baseline
            selected_scope = backup_scope_selection()
            selected_receipt_images = bool(receipt_image_enabled_var.get())
            selected_github_auto_sync = bool(github_auto_sync_var.get())
            selected_gitee_auto_sync = bool(gitee_auto_sync_var.get())
            if not any(selected_scope.values()):
                backup_scope_status.configure(
                    text=translate("至少选择一项云备份内容。", self.language)
                )
                messagebox.showwarning(
                    translate("云备份范围", self.language),
                    translate("至少选择一项云备份内容。", self.language),
                    parent=dialog,
                )
                return
            try:
                self.api_profile_store.save(
                    self.api_profiles,
                    self.active_api_profile_id,
                    self.agent_profile_ids,
                    self.agent_vision_profile_ids,
                )
                backup_scope_store.save(selected_scope)
                self.receipt_image_settings_store.save_enabled(selected_receipt_images)
                self.github_auto_sync_settings_store.save_enabled(selected_github_auto_sync)
                self.gitee_auto_sync_settings_store.save_enabled(selected_gitee_auto_sync)
                for mode in ("bookkeeping", "food_health"):
                    skill = agent_skill_drafts[mode]
                    store = agent_skill_stores[mode]
                    old_skill = old_state[
                        "loaded_skill" if mode == "bookkeeping" else "loaded_food_health_skill"
                    ]
                    if skill_path(skill) == skill_path(old_skill):
                        continue
                    if skill and skill.get("path"):
                        store.save_path(skill["path"])
                    else:
                        store.clear()
                save_language(selected_language)
                save_appearance(selected_appearance)
            except Exception as exc:
                rollback_errors = rollback_persisted_settings(old_state)
                detail = f"设置没有全部保存：{exc}"
                if rollback_errors:
                    detail += "\n回退时也有问题：" + "；".join(rollback_errors)
                messagebox.showerror("保存失败", detail, parent=dialog)
                footer_status.configure(text=translate("设置未应用；草稿仍保留，可修正后重试或取消。", self.language))
                return

            old_profiles = {item["id"]: item for item in old_state["api_profiles"]}
            new_profiles = {item["id"]: item for item in self.api_profiles}
            affected_modes: set[str] = set()
            for mode in ("bookkeeping", "food_health"):
                old_assigned = (
                    old_state["agent_profile_ids"].get(mode),
                    old_state["agent_vision_profile_ids"].get(mode),
                )
                new_assigned = (
                    self.agent_profile_ids.get(mode),
                    self.agent_vision_profile_ids.get(mode),
                )
                if old_assigned != new_assigned or any(
                    old_profiles.get(profile_id) != new_profiles.get(profile_id)
                    for profile_id in set(old_assigned + new_assigned) - {None}
                ):
                    affected_modes.add(mode)
                old_skill = old_state["loaded_skill" if mode == "bookkeeping" else "loaded_food_health_skill"]
                new_skill = agent_skill_drafts[mode]
                if (old_skill or {}).get("path") != (new_skill or {}).get("path"):
                    affected_modes.add(mode)
            self.save_receipt_images_locally = selected_receipt_images
            self.receipt_image_settings_error = ""
            self.api_profile_settings_error = ""
            self.github_auto_sync_enabled = selected_github_auto_sync
            self.github_auto_sync_settings_error = ""
            self.gitee_auto_sync_enabled = selected_gitee_auto_sync
            self.gitee_auto_sync_settings_error = ""
            self.loaded_skill = deepcopy(agent_skill_drafts["bookkeeping"])
            self.loaded_food_health_skill = deepcopy(agent_skill_drafts["food_health"])
            self.skill_settings_error = ""
            self.food_health_skill_settings_error = ""
            for mode in affected_modes:
                self._clear_agent_context(mode)
                self._clear_agent_clients(mode)
            if self.agent_mode in affected_modes:
                self._update_skill_summary()
                self._refresh_agent_view()
            if selected_language != self.language:
                self.language = selected_language
                set_language(selected_language)
                self._reset_all_conversations()
            self.appearance_mode = selected_appearance
            apply_appearance(self.root, self.ui_font_family, selected_appearance)
            apply_language(self.root)
            refresh_backup_scope_toggle_label()
            backup_scope_status.configure(text=translate("云备份范围已保存。", self.language))
            receipt_image_status.configure(text=translate("设置已保存。", self.language))
            github_auto_sync_status.configure(
                text=translate("GitHub 自动同步已开启。" if selected_github_auto_sync else "GitHub 自动同步已关闭。", self.language)
            )
            gitee_auto_sync_status.configure(
                text=translate("Gitee 自动同步已开启。" if selected_gitee_auto_sync else "Gitee 自动同步已关闭。", self.language)
            )
            language_status.configure(text=translate("设置已保存。", self.language))
            status_message = translate("设置已保存并应用。", self.language)
            footer_status.configure(text=status_message)
            self.status.configure(text=status_message)
            settings_baseline = capture_settings_baseline()
            if close_after_apply:
                dialog.destroy()

        def confirm_settings() -> None:
            apply_current_settings(close_after_apply=True)

        def apply_settings() -> None:
            apply_current_settings(close_after_apply=False)

        def discard_settings() -> None:
            cancel_settings()

        footer_status = tk.Label(
            footer,
            text=translate("更改将在点击应用或确认后保存。", self.language),
            wraplength=220,
            bg=color("#f2f4f7"),
            fg=color("#175cd3"),
            font=(self.ui_font_family, 9),
            anchor="w",
        )
        footer_status.pack(side="left", fill="x", expand=True)
        ttk.Button(footer, text="应用", style="Settings.TButton", command=apply_settings).pack(side="right", padx=(8, 0))
        ttk.Button(footer, text="取消", style="Settings.TButton", command=discard_settings).pack(side="right", padx=(8, 0))
        ttk.Button(footer, text="确认", style="HeaderPrimary.TButton", command=confirm_settings).pack(side="right")

        profile_combo.bind("<<ComboboxSelected>>", selected_profile_changed)
        add_button.configure(command=add_profile)
        delete_button.configure(command=delete_profile)
        for entry in (name_entry, url_entry, model_entry, key_entry):
            entry.bind("<KeyRelease>", mark_profile_pending)
            entry.bind("<<Paste>>", mark_profile_pending, add="+")
            entry.bind("<<Cut>>", mark_profile_pending, add="+")
        thinking_check.configure(command=mark_profile_pending)
        effort_combo.bind("<<ComboboxSelected>>", mark_profile_pending)
        url_var.trace_add("write", refresh_thinking_controls)
        thinking_enabled_var.trace_add("write", refresh_thinking_controls)
        dialog.bind("<Escape>", lambda _event: discard_settings())
        dialog.protocol("WM_DELETE_WINDOW", discard_settings)
        show_settings_page(initial_page if initial_page in pages else "API 服务")
        load_active_profile()
        center_window(dialog, self.root)
        # This dialog is built after the main window, and several pages stay
        # unmapped until selected. Register all of its widgets explicitly so
        # touchpad scrolling works on the settings canvas and every page.
        self._attach_mousewheel_bindtag_tree(dialog)
        dialog.lift()
        dialog.grab_set()
        name_entry.focus_set()

    def _update_skill_summary(self) -> None:
        if self.agent_mode == "food_health":
            skill = self.loaded_food_health_skill
            error = self.food_health_skill_settings_error
            label = "饮食健康 Skill"
        else:
            skill = self.loaded_skill
            error = self.skill_settings_error
            label = "记账 Skill"
        if error:
            text = f"{label}：设置有问题（{error}）"
        elif skill:
            text = f"{label}：已加载 {skill['name']}；发送时读取最新内容。"
        else:
            text = f"{label}：未加载"
        self.skill_summary.configure(text=text)

    def open_skill_settings(self) -> None:
        if self.pending_state is not None:
            messagebox.showinfo(
                translate("记账尚未完成", self.language),
                self._pending_workflow_message(),
                parent=self.root,
            )
            return
        dialog = tk.Toplevel(self.root)
        dialog.title("记账 Skill")
        dialog.geometry("880x650")
        dialog.minsize(760, 520)
        dialog.transient(self.root)
        dialog.configure(bg=color("#f3f5f8"))

        panel = ttk.Frame(dialog, style="App.TFrame", padding=20)
        panel.pack(fill="both", expand=True)
        panel.columnconfigure(0, weight=1)
        panel.rowconfigure(3, weight=1)
        ttk.Label(panel, text="记账 Skill", style="Title.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(
            panel,
            text="选择一个 Markdown Skill 文件。软件会在每次记账前重新读取，并把正文作为补充规则发送给当前 API。只加载所选文件本身，不会自动读取它引用的其他文件或运行其中的命令；程序内置的账务确认和校验规则优先。",
            style="Hint.TLabel",
            wraplength=760,
            justify="left",
        ).grid(row=1, column=0, sticky="ew", pady=(6, 12))

        path_label = ttk.Label(panel, text="", style="Hint.TLabel", wraplength=760)
        path_label.grid(row=2, column=0, sticky="ew", pady=(0, 8))
        preview_frame = ttk.Frame(panel, style="App.TFrame")
        preview_frame.grid(row=3, column=0, sticky="nsew")
        preview_frame.columnconfigure(0, weight=1)
        preview_frame.rowconfigure(0, weight=1)
        preview = tk.Text(
            preview_frame,
            wrap="word",
            state="disabled",
            relief="solid",
            borderwidth=1,
            padx=10,
            pady=8,
            background=color("#ffffff"),
            foreground=color("#344054"),
            font=(self.ui_font_family, 10),
        )
        preview_scroll = ttk.Scrollbar(preview_frame, orient="vertical", command=preview.yview)
        preview.configure(yscrollcommand=preview_scroll.set)
        preview.grid(row=0, column=0, sticky="nsew")
        preview_scroll.grid(row=0, column=1, sticky="ns")

        def show_loaded_skill() -> None:
            try:
                loaded = self.skill_store.load()
            except BookkeepingSkillError as exc:
                self.skill_settings_error = str(exc)
                loaded = None
            else:
                self.skill_settings_error = ""
            self.loaded_skill = loaded
            self._update_skill_summary()
            if loaded:
                path_label.configure(text=f"已加载：{loaded['path']}（{len(loaded['content'])} 字符）")
                body = loaded["content"]
                if len(body) > 20000:
                    body = body[:20000] + "\n\n……预览已截断；发送时会使用完整文件。"
            else:
                path_label.configure(text=self.skill_settings_error or "当前未加载 Skill。")
                body = ""
            preview.configure(state="normal")
            preview.delete("1.0", "end")
            preview.insert("1.0", body)
            preview.configure(state="disabled")

        def choose_skill() -> None:
            current_path = self.loaded_skill.get("path") if self.loaded_skill else ""
            initial_dir = str(Path(current_path).parent) if current_path else str(self.skill_store.default_path.parent)
            selected = filedialog.askopenfilename(
                parent=dialog,
                title="选择记账 Skill 文件",
                initialdir=initial_dir,
                filetypes=(("Skill 文件 (SKILL.md)", "SKILL.md"), ("Markdown 文件", "*.md")),
            )
            if not selected:
                return
            try:
                self.loaded_skill = self.skill_store.save_path(selected)
            except BookkeepingSkillError as exc:
                messagebox.showerror("无法加载 Skill", str(exc), parent=dialog)
                return
            self.skill_settings_error = ""
            self._clear_conversation_context()
            self._update_skill_summary()
            self.status.configure(text="记账 Skill 已加载；后续请求会读取最新内容。")
            show_loaded_skill()

        def unload_skill() -> None:
            try:
                self.skill_store.clear()
            except BookkeepingSkillError as exc:
                messagebox.showerror("卸载失败", str(exc), parent=dialog)
                return
            self.loaded_skill = None
            self.skill_settings_error = ""
            self._clear_conversation_context()
            self._update_skill_summary()
            self.status.configure(text="记账 Skill 已卸载。")
            show_loaded_skill()

        buttons = ttk.Frame(panel, style="App.TFrame")
        buttons.grid(row=4, column=0, sticky="ew", pady=(12, 0))
        ttk.Button(buttons, text="选择并加载文件", command=choose_skill).pack(side="left")
        ttk.Button(buttons, text="重新读取", command=show_loaded_skill).pack(side="left", padx=(8, 0))
        ttk.Button(buttons, text="卸载 Skill", command=unload_skill).pack(side="left", padx=(8, 0))
        ttk.Button(buttons, text="关闭", command=dialog.destroy).pack(side="right")
        dialog.bind("<Escape>", lambda _event: dialog.destroy())
        show_loaded_skill()
        dialog.grab_set()

    def _payment_hints(self) -> list[dict[str, Any]]:
        return [dict(profile) for profile in self.payment_profiles]

    def _reload_payment_profiles(self) -> bool:
        """Keep the editor and each bookkeeping request aligned with saved rules."""
        try:
            settings, revision = self.payment_prompt_store.load_snapshot()
        except PaymentPromptSettingsError as exc:
            self.payment_settings_load_error = str(exc)
            self._update_payment_hint_summary()
            return False
        self.payment_profiles = settings["profiles"]
        self.payment_settings_revision = revision
        self.payment_settings_load_error = ""
        self._update_payment_hint_summary()
        return True

    def _update_payment_hint_summary(self) -> None:
        if self.payment_settings_load_error:
            self.payment_hint_summary.configure(text="支付场景规则：设置文件无法读取，请打开“支付方式与用途”重新保存。")
            return
        count = len(self.payment_profiles)
        text = f"支付场景规则：已设置 {count} 项；记账时按用途和币种匹配。" if count else "支付场景规则：未设置"
        self.payment_hint_summary.configure(text=text)

    def open_payment_settings(self, container: tk.Misc | None = None) -> None:
        self._reload_payment_profiles()
        expected_revision = self.payment_settings_revision
        database = Database(self.database_path)
        try:
            account_rows = [dict(row) for row in database.connection.execute(
                "SELECT name,account_type,currency FROM accounts ORDER BY name"
            ).fetchall()]
        finally:
            database.close()
        selectable_rows = [
            row for row in account_rows
            if row["account_type"] in {"bank", "wallet", "prepaid", "transit", "credit"}
        ]
        selectable_names = [str(row["name"]) for row in selectable_rows]
        account_by_name = {str(row["name"]): row for row in account_rows}
        route_names = [str(row["name"]) for row in account_rows]

        def resolve_saved_account(label: str) -> str | None:
            key = _normalize_account_label(label)
            if not key:
                return None
            exact_names = {
                str(row["name"])
                for row in account_rows
                if _normalize_account_label(str(row["name"])) == key
            }
            if len(exact_names) == 1:
                return next(iter(exact_names))
            matches = {
                str(row["name"])
                for row in account_rows
                if any(key == _normalize_account_label(alias) for alias in _account_mention_aliases(str(row["name"])))
            }
            return next(iter(matches)) if len(matches) == 1 else None

        def legacy_profile_values(profile: dict[str, Any]) -> tuple[str, list[str]]:
            order = profile.get("account_order")
            if isinstance(order, (list, tuple)) and order:
                resolved_order = [str(name).strip() for name in order if isinstance(name, str) and name.strip()]
            else:
                terms = _payment_priority_terms(str(profile.get("purpose", ""))) or []
                resolved_order = [
                    (resolve_saved_account(term) or term)
                    for term in terms
                ]
            resolved_order = list(dict.fromkeys(resolved_order))
            method = resolve_saved_account(str(profile.get("payment_method", "")))
            if method not in selectable_names:
                # For platform chains, the wallet is usually the ordinary
                # account represented by the service name; coupons/points are
                # explicit earlier sources in the route, not the main choice.
                method = next(
                    (
                        name for preferred_type in ("wallet", "bank", "transit", "prepaid", "credit")
                        for name in resolved_order
                        if name in selectable_names and account_by_name[name]["account_type"] == preferred_type
                    ),
                    None,
                )
            if method and not resolved_order:
                resolved_order = [method]
            elif method and method not in resolved_order:
                resolved_order.append(method)
            return method or "", resolved_order

        if container is None:
            dialog = tk.Toplevel(self.root)
            dialog.title("支付方式与用途")
            screen_width = dialog.winfo_screenwidth()
            screen_height = dialog.winfo_screenheight()
            window_width = min(1080, max(900, screen_width - 60))
            window_height = min(660, max(500, screen_height - 80))
            window_x = max(0, (screen_width - window_width) // 2)
            window_y = max(0, (screen_height - window_height) // 2)
            dialog.geometry(
                f"{window_width}x{window_height}+{window_x}+{window_y}"
            )
            dialog.minsize(min(960, window_width), min(500, window_height))
            dialog.transient(self.root)
            dialog.configure(bg=color("#f3f5f8"))
            content_parent: tk.Misc = dialog
        else:
            dialog = container.winfo_toplevel()
            content_parent = container

        panel = ttk.Frame(content_parent, style="App.TFrame", padding=12)
        panel.pack(fill="both", expand=True)
        fit_management_text(panel)
        panel.columnconfigure(0, weight=1)
        panel.rowconfigure(2, weight=1)
        ttk.Label(panel, text="支付方式与用途", style="ManagementTitle.TLabel").grid(
            row=0, column=0, sticky="w"
        )
        ttk.Label(
            panel,
            text=translate(
                "每行是一条场景规则。支付账户从已登记的银行、钱包、预付卡、交通卡或信用卡中选择；积分账户不能作为普通支付账户。点击“扣款顺序”可按实际优先级添加钱包、券、积分和信用卡，积分只在这里作为明确配置的扣款来源。保存后规则会随记账请求提供给 Agent；唯一命中场景时，程序严格按这里的账户顺序和同币种余额/额度分摊，不从用途文字猜顺序，也不跨币种换算。旧规则中无法对应到账户的顺序项会标为“账户未登记”，保存前需添加对应账户或移除该项。",
                self.language,
            ),
            style="Hint.TLabel",
            wraplength=830,
        ).grid(row=1, column=0, sticky="ew", pady=(4, 8))

        rows_frame = ttk.Frame(panel, style="App.TFrame")
        rows_frame.grid(row=2, column=0, sticky="ew")

        rows_frame.columnconfigure(0, weight=2)
        rows_frame.columnconfigure(1, weight=1)
        rows_frame.columnconfigure(2, weight=4)
        ttk.Label(rows_frame, text=translate("支付账户", self.language), style="Hint.TLabel").grid(row=0, column=0, sticky="w", padx=(0, 8))
        ttk.Label(rows_frame, text="适用币种", style="Hint.TLabel").grid(row=0, column=1, sticky="w", padx=(0, 8))
        ttk.Label(rows_frame, text="用途提示", style="Hint.TLabel").grid(row=0, column=2, sticky="w", padx=(0, 8))
        ttk.Label(rows_frame, text=translate("扣款顺序", self.language), style="Hint.TLabel").grid(row=0, column=3, sticky="w", padx=(0, 8))
        ttk.Label(rows_frame, text="", style="Hint.TLabel").grid(row=0, column=4)

        rows: list[dict[str, Any]] = []
        next_row_id = 1

        def refresh_row_positions() -> None:
            for position, row in enumerate(rows, start=1):
                row["frame"].grid_configure(row=position)

        def remove_row(row_id: int) -> None:
            for row in rows:
                if row["id"] == row_id:
                    payment_method = row["method"].get().strip() or "（未填写支付方式）"
                    purpose = row["purpose"].get().strip() or "（未填写用途）"
                    if not confirm_delete_once(
                        dialog,
                        title="删除支付规则行",
                        target=f"支付方式“{payment_method}”，用途“{purpose}”",
                        impact="该规则行会从当前编辑列表移除；点击保存后才会从支付设置中删除。",
                    ):
                        return
                    row["frame"].destroy()
                    rows.remove(row)
                    break
            refresh_row_positions()

        def add_row(
            payment_method: str = "",
            purpose: str = "",
            currency: str = "",
            account_order: list[str] | None = None,
        ) -> None:
            nonlocal next_row_id
            row_id = next_row_id
            next_row_id += 1
            row_number = len(rows) + 1
            row_frame = ttk.Frame(rows_frame, style="App.TFrame")
            row_frame.grid(row=row_number, column=0, columnspan=5, sticky="ew", pady=4)
            row_frame.columnconfigure(0, weight=2)
            row_frame.columnconfigure(1, weight=1)
            row_frame.columnconfigure(2, weight=4)
            method_var = tk.StringVar(value=payment_method)
            currency_var = tk.StringVar(value=currency if currency in {"JPY", "CNY"} else "不限")
            purpose_var = tk.StringVar(value=purpose)
            order_var: list[str] = []
            method_box = ttk.Combobox(
                row_frame,
                textvariable=method_var,
                values=selectable_names,
                state="readonly" if selectable_names else "disabled",
            )
            method_box.grid(row=0, column=0, sticky="ew", padx=(0, 8))
            ttk.Combobox(
                row_frame,
                textvariable=currency_var,
                values=("不限", "JPY", "CNY"),
                width=8,
                state="readonly",
            ).grid(row=0, column=1, sticky="ew", padx=(0, 8))
            ttk.Entry(row_frame, textvariable=purpose_var).grid(row=0, column=2, sticky="ew", padx=(0, 8))
            order_button = ttk.Button(row_frame, text="扣款顺序…")
            order_button.grid(row=0, column=3, padx=(0, 8))
            ttk.Button(row_frame, text="删除", command=lambda: remove_row(row_id)).grid(row=0, column=4)
            route_summary = ttk.Label(row_frame, text="", style="Hint.TLabel", wraplength=830)
            route_summary.grid(row=1, column=0, columnspan=5, sticky="w", pady=(3, 0))
            row_state = {
                "id": row_id,
                "frame": row_frame,
                "method": method_var,
                "method_box": method_box,
                "currency": currency_var,
                "purpose": purpose_var,
                "order": order_var,
                "order_button": order_button,
            }
            rows.append(row_state)

            def update_order_label() -> None:
                label = translate("扣款顺序…", self.language)
                order_button.configure(text=f"{label} ({len(order_var)})" if order_var else label)
                route_summary.configure(text=" → ".join(order_var))

            def method_changed(_event: Any = None) -> None:
                selected = method_var.get().strip()
                if selected:
                    # Changing the primary account deliberately resets the route;
                    # a linked-account chain can then be configured explicitly.
                    order_var[:] = [selected]
                else:
                    order_var.clear()
                update_order_label()

            def edit_order() -> None:
                order_dialog = tk.Toplevel(dialog)
                order_dialog.title(translate("设置扣款顺序", self.language))
                order_dialog.geometry("700x500")
                order_dialog.minsize(600, 380)
                order_dialog.transient(dialog)
                order_panel = ttk.Frame(order_dialog, style="App.TFrame", padding=12)
                order_panel.pack(fill="both", expand=True)
                ttk.Label(
                    order_panel,
                    text=translate(
                        "从上到下依次尝试扣款。可选择积分账户、钱包、预付卡、银行账户或信用卡；一条顺序内必须使用同一币种，积分只能参与JPY顺序。普通支付账户下拉框不显示积分。",
                        self.language,
                    ),
                    style="Hint.TLabel",
                    wraplength=650,
                ).pack(fill="x", pady=(0, 12))
                route_frame = ttk.Frame(order_panel, style="App.TFrame")
                route_frame.pack(fill="both", expand=True)
                selected_order = list(order_var or ([method_var.get()] if method_var.get() else []))

                def redraw_order() -> None:
                    for child in route_frame.winfo_children():
                        child.destroy()
                    for index, account_name in enumerate(selected_order):
                        ttk.Label(route_frame, text=f"{index + 1}.", style="Hint.TLabel").grid(
                            row=index, column=0, sticky="w", padx=(0, 6), pady=4
                        )
                        account_var = tk.StringVar(value=account_name)
                        box = ttk.Combobox(
                            route_frame,
                            textvariable=account_var,
                            values=route_names,
                            state="readonly",
                            width=34,
                        )
                        box.grid(row=index, column=1, sticky="ew", padx=(0, 8), pady=4)
                        account_type = account_by_name.get(account_name, {}).get("account_type", "")
                        type_caption = (
                            "账户未登记" if account_name not in account_by_name
                            else "积分" if account_type == "points"
                            else "普通账户"
                        )
                        type_label = ttk.Label(route_frame, text=translate(type_caption, self.language), style="Hint.TLabel")
                        type_label.grid(
                            row=index, column=2, sticky="w", padx=(0, 8), pady=4
                        )

                        def account_selected(
                            _event: Any,
                            pos: int = index,
                            value: tk.StringVar = account_var,
                            label: ttk.Label = type_label,
                        ) -> None:
                            selected_order[pos] = value.get()
                            selected_name = value.get()
                            selected_type = account_by_name.get(selected_name, {}).get("account_type", "")
                            caption = (
                                "账户未登记" if selected_name not in account_by_name
                                else "积分" if selected_type == "points"
                                else "普通账户"
                            )
                            label.configure(text=translate(caption, self.language))

                        box.bind("<<ComboboxSelected>>", account_selected)
                        ttk.Button(
                            route_frame,
                            text="↑",
                            width=3,
                            state="normal" if index else "disabled",
                            command=lambda pos=index: move_order_item(pos, -1),
                        ).grid(row=index, column=3, padx=2)
                        ttk.Button(
                            route_frame,
                            text="↓",
                            width=3,
                            state="normal" if index < len(selected_order) - 1 else "disabled",
                            command=lambda pos=index: move_order_item(pos, 1),
                        ).grid(row=index, column=4, padx=2)
                        ttk.Button(
                            route_frame,
                            text="删除",
                            state="normal" if len(selected_order) > 1 else "disabled",
                            command=lambda pos=index: remove_order_item(pos),
                        ).grid(row=index, column=5, padx=(6, 0))
                    route_frame.columnconfigure(1, weight=1)

                def move_order_item(index: int, offset: int) -> None:
                    target_index = index + offset
                    if 0 <= target_index < len(selected_order):
                        selected_order[index], selected_order[target_index] = selected_order[target_index], selected_order[index]
                        redraw_order()

                def remove_order_item(index: int) -> None:
                    account_name = selected_order[index]
                    if not confirm_delete_once(
                        order_dialog,
                        title="移除扣款账户",
                        target=f"顺序第{index + 1}位账户“{account_name}”",
                        impact="只从这条支付规则的扣款顺序中移除，不会删除账本账户。",
                    ):
                        return
                    selected_order.pop(index)
                    redraw_order()

                def add_order_item() -> None:
                    if len(selected_order) >= 10:
                        messagebox.showinfo(
                            translate("扣款顺序", self.language),
                            translate("一条扣款顺序最多添加10个账户。", self.language),
                            parent=order_dialog,
                        )
                        return
                    selected_order.append("")
                    redraw_order()

                redraw_order()
                order_buttons = ttk.Frame(order_panel, style="App.TFrame")
                order_buttons.pack(fill="x", pady=(8, 0))
                ttk.Button(order_buttons, text=translate("＋ 添加账户", self.language), command=add_order_item).pack(side="left")

                def save_order() -> None:
                    if not selected_order or any(not name for name in selected_order):
                        messagebox.showwarning(
                            translate("扣款顺序不完整", self.language),
                            translate("请为顺序中的每一项选择一个账户。", self.language),
                            parent=order_dialog,
                        )
                        return
                    if len(set(selected_order)) != len(selected_order):
                        messagebox.showwarning(
                            translate("账户重复", self.language),
                            translate("同一账户不能在一条扣款顺序中重复出现。", self.language),
                            parent=order_dialog,
                        )
                        return
                    method = method_var.get().strip()
                    if method and method not in selected_order:
                        messagebox.showwarning(
                            translate("主支付账户未加入顺序", self.language),
                            translate("扣款顺序必须包含上方选择的支付账户。", self.language),
                            parent=order_dialog,
                        )
                        return
                    if any(name not in account_by_name for name in selected_order):
                        messagebox.showwarning(
                            translate("扣款顺序不完整", self.language),
                            translate("扣款顺序中包含已不存在的账户，请重新选择。", self.language),
                            parent=order_dialog,
                        )
                        return
                    currencies = {str(account_by_name[name]["currency"]).upper() for name in selected_order}
                    if len(currencies) != 1:
                        messagebox.showwarning(
                            translate("币种不一致", self.language),
                            translate("同一扣款顺序必须全部使用同一币种；积分账户只能加入JPY顺序。", self.language),
                            parent=order_dialog,
                        )
                        return
                    scope = currency_var.get().strip().upper()
                    route_currency = next(iter(currencies))
                    if scope in {"JPY", "CNY"} and route_currency != scope:
                        messagebox.showwarning(
                            translate("币种不匹配", self.language),
                            translate("扣款账户币种应与规则适用的交易币种一致；普通消费不会自动换汇。", self.language),
                            parent=order_dialog,
                        )
                        return
                    order_var[:] = selected_order
                    update_order_label()
                    order_dialog.destroy()

                ttk.Button(order_buttons, text="取消", command=order_dialog.destroy).pack(side="right", padx=(8, 0))
                ttk.Button(order_buttons, text=translate("保存顺序", self.language), style="Send.TButton", command=save_order).pack(side="right")
                order_dialog.bind("<Escape>", lambda _event: order_dialog.destroy())
                order_dialog.grab_set()

            order_button.configure(command=edit_order)
            method_box.bind("<<ComboboxSelected>>", method_changed)
            initial_method, initial_order = legacy_profile_values({
                "payment_method": payment_method,
                "purpose": purpose,
                "account_order": account_order or [],
            })
            if payment_method:
                # Preserve the caller's pre-resolved account when loading a legacy row.
                method_var.set(initial_method)
            order_var[:] = initial_order or ([initial_method] if initial_method else [])
            update_order_label()

        if self.payment_settings_load_error:
            ttk.Label(
                panel,
                text=self.payment_settings_load_error,
                style="Status.TLabel",
                wraplength=830,
            ).grid(row=3, column=0, sticky="ew", pady=(8, 0))

        for profile in self.payment_profiles:
            method, order = legacy_profile_values(profile)
            add_row(
                method,
                profile["purpose"],
                profile.get("currency", ""),
                order,
            )
        if not rows:
            add_row()

        buttons = ttk.Frame(panel, style="App.TFrame")
        buttons.grid(row=4, column=0, sticky="ew", pady=(8, 0))
        ttk.Button(buttons, text="＋ 添加支付方式", command=add_row).pack(side="left")

        def save_payment_settings() -> None:
            nonlocal expected_revision
            profiles: list[dict[str, Any]] = []
            for row in rows:
                method = row["method"].get().strip()
                purpose = row["purpose"].get().strip()
                if not method:
                    if purpose or row["order"]:
                        messagebox.showwarning("请填写支付方式", "有用途提示的项目还没有填写支付方式。", parent=dialog)
                        return
                    continue
                order = list(row["order"] or [method])
                if method not in selectable_names or method not in order:
                    messagebox.showwarning(
                        translate("扣款顺序不完整", self.language),
                        translate("请选择有效的普通支付账户，并确保扣款顺序包含该账户。", self.language),
                        parent=dialog,
                    )
                    return
                if any(name not in account_by_name for name in order) or len(order) != len(set(order)):
                    messagebox.showwarning(
                        translate("扣款顺序不完整", self.language),
                        translate("扣款顺序中存在无效或重复的账户，请重新设置顺序。", self.language),
                        parent=dialog,
                    )
                    return
                route_currencies = {str(account_by_name[name]["currency"]).upper() for name in order}
                if len(route_currencies) != 1:
                    messagebox.showwarning(
                        translate("币种不一致", self.language),
                        translate("同一扣款顺序必须全部使用同一币种；积分账户只能加入JPY顺序。", self.language),
                        parent=dialog,
                    )
                    return
                scope = "" if row["currency"].get() == "不限" else row["currency"].get().strip().upper()
                if scope in {"JPY", "CNY"} and next(iter(route_currencies)) != scope:
                    messagebox.showwarning(
                        translate("币种不匹配", self.language),
                        translate("扣款账户币种应与规则适用的交易币种一致；普通消费不会自动换汇。", self.language),
                        parent=dialog,
                    )
                    return
                profiles.append({"payment_method": method, "purpose": purpose, "account_order": order})
                profiles[-1]["currency"] = "" if row["currency"].get() == "不限" else row["currency"].get()
            try:
                expected_revision = self.payment_prompt_store.save_profiles(
                    profiles,
                    expected_revision=expected_revision,
                )
            except PaymentPromptSettingsConflict as exc:
                self._reload_payment_profiles()
                messagebox.showwarning(
                    translate("支付规则已在其他窗口更新", self.language),
                    translate(
                        "支付规则已在其他窗口或同步操作中更新。本次没有覆盖最新设置。请关闭此页后重新打开，再确认并保存。",
                        self.language,
                    ),
                    parent=dialog,
                )
                return
            except PaymentPromptSettingsError as exc:
                messagebox.showerror("保存失败", str(exc), parent=dialog)
                return
            self.payment_profiles = profiles
            self.payment_settings_load_error = ""
            self._update_payment_hint_summary()
            self.status.configure(text="支付场景规则已保存；下次发送记账内容时生效。")
            if container is None:
                dialog.destroy()
            else:
                messagebox.showinfo(
                    translate("保存完成", self.language),
                    translate("支付场景规则已保存；下次发送记账内容时生效。", self.language),
                    parent=dialog,
                )

        if container is None:
            ttk.Button(buttons, text="取消", command=dialog.destroy).pack(side="right", padx=(8, 0))
        ttk.Button(buttons, text="保存", style="Send.TButton", command=save_payment_settings).pack(side="right")
        if container is None:
            dialog.bind("<Escape>", lambda _event: dialog.destroy())
            dialog.grab_set()

    def send(self) -> None:
        if self._github_restore_in_progress:
            self.status.configure(text=translate("正在下载并校验云端数据…", self.language))
            return
        if self.busy:
            return
        if self._recurring_processing:
            self.status.configure(text=translate("正在处理到期的定期收支，请稍后再发送。", self.language))
            return
        draft_text = self.input_box.get("1.0", "end-1c").strip()
        if not draft_text and not self.image_attachments:
            return
        user_text = draft_text or (
            "请结合图片中的食物内容和我的近期饮食记录，给出健康饮食建议。"
            if self.agent_mode == "food_health"
            else "请把附件中状态明确为已完成的购买解析成一笔消费，提取可确认的日期、含税实付总额、商品类别和支付账户；状态、账户或金额不确定时先追问，不要猜测。"
        )
        images_snapshot = list(self.image_attachments)
        client = self._get_client(has_images=bool(images_snapshot))
        if client is None:
            return
        skill_content = ""
        payment_hints: list[dict[str, str]] = []
        if self.agent_mode == "bookkeeping":
            try:
                self.loaded_skill = self.skill_store.load()
                self.skill_settings_error = ""
            except BookkeepingSkillError as exc:
                self.skill_settings_error = str(exc)
                self._update_skill_summary()
                self.status.configure(text=f"记账 Skill 无法读取：{exc}")
                return
            self._update_skill_summary()
            skill_content = self.loaded_skill["content"] if self.loaded_skill else ""
            if not self._reload_payment_profiles():
                self.status.configure(
                    text=f"支付场景规则无法读取：{self.payment_settings_load_error}"
                )
                return
            payment_hints = self._payment_hints()
        else:
            try:
                self.loaded_food_health_skill = self.food_health_skill_store.load()
                self.food_health_skill_settings_error = ""
            except BookkeepingSkillError as exc:
                self.food_health_skill_settings_error = str(exc)
                self._update_skill_summary()
                self.status.configure(text=f"饮食健康 Skill 无法读取：{exc}")
                return
            self._update_skill_summary()
            skill_content = (
                self.loaded_food_health_skill["content"]
                if self.loaded_food_health_skill
                else ""
            )

        display_text = user_text
        if images_snapshot:
            filenames = "、".join(attachment.name for attachment in images_snapshot)
            display_text = f"{user_text}\n（附图：{filenames}）"

        history_snapshot = [dict(message) for message in self.history]
        pending_snapshot = deepcopy(self.pending_state)
        agent_mode = self.agent_mode
        profile = self._agent_api_profile(has_images=bool(images_snapshot))
        client_config = {
            "api_key": client.api_key,
            "api_url": client.api_url,
            "model": client.model,
            "thinking_enabled": client.thinking_enabled,
            "reasoning_effort": client.reasoning_effort,
            "timeout": client.timeout,
        }
        workspace: Path | None = None
        parent_connection: Any = None
        child_connection: Any = None
        worker: multiprocessing.Process | None = None
        try:
            # Finish any pending schema migration before snapshotting. The request
            # itself then works only in a disposable copy of the ledger.
            database = Database(self.database_path)
            try:
                database.connection.execute("PRAGMA busy_timeout=500")
                database.initialize()
            finally:
                database.close()
        except Exception as exc:
            self.status.configure(
                text=translate("后台任务无法启动：{error}", self.language).format(error=exc)
            )
            return

        archived_receipt_paths: list[Path] = []
        if (
            agent_mode == "bookkeeping"
            and images_snapshot
            and self.save_receipt_images_locally
        ):
            try:
                archived_receipt_paths = self._archive_receipt_attachments(images_snapshot)
            except (ReceiptImageError, LedgerError, OSError, sqlite3.Error, ValueError) as exc:
                self.status.configure(
                    text=translate("无法保存小票图片：{error}", self.language).format(error=exc)
                )
                return

        try:
            workspace = Path(tempfile.mkdtemp(prefix=".request-", dir=self.database_path.parent))
            baseline_path = workspace / "baseline.sqlite3"
            candidate_path = workspace / "candidate.sqlite3"
            context = multiprocessing.get_context("spawn")
            parent_connection, child_connection = context.Pipe(duplex=False)
            worker = context.Process(
                target=run_isolated_request,
                args=(
                    str(self.database_path),
                    str(baseline_path),
                    str(candidate_path),
                    client_config,
                    user_text,
                    history_snapshot,
                    pending_snapshot,
                    payment_hints,
                    skill_content,
                    images_snapshot,
                    agent_mode,
                    self.language,
                    child_connection,
                ),
                name="bookkeeping-api-request",
                daemon=True,
            )
            worker.start()
            child_connection.close()
            child_connection = None
        except Exception as exc:
            if child_connection is not None:
                child_connection.close()
            if parent_connection is not None:
                parent_connection.close()
            if worker is not None and worker.pid is not None:
                try:
                    if worker.is_alive():
                        worker.terminate()
                        worker.join(timeout=0.2)
                        if worker.is_alive():
                            worker.kill()
                            worker.join(timeout=0.2)
                except (OSError, ValueError):
                    pass
            if workspace is not None:
                shutil.rmtree(workspace, ignore_errors=True)
            self._discard_receipt_image_archive(archived_receipt_paths)
            self.status.configure(
                text=translate("后台任务无法启动：{error}", self.language).format(error=exc)
            )
            return

        self._request_results = queue.Queue()
        self._request_started = time.monotonic()
        self._request_deadline = self._request_started + float(client.timeout) + 60
        self._request_inserted_ids = []
        self._request_process = worker
        self._request_pipe = parent_connection
        self._request_workspace = workspace
        self._request_baseline_path = baseline_path
        self._request_candidate_path = candidate_path
        self._request_cancelled = False
        self._request_worker_message = None
        self._request_history_snapshot = history_snapshot
        self._request_pending_snapshot = pending_snapshot
        self._request_profile_id = str(profile.get("id") or "") or None
        self._pending_image_attachments = images_snapshot
        self._request_agent_mode = agent_mode
        threading.Thread(target=receive_request_result, args=(
            parent_connection, worker, self._request_results,
            ('error', translate("后台任务意外退出，本次结果未写入账本。请重试。", self.language),
             history_snapshot, pending_snapshot, None),
        ), daemon=True, name='ledger-request-reader').start()
        self._append_message("你", display_text)
        self.input_box.delete("1.0", "end")
        self._pending_draft_text = draft_text
        self._pending_had_images = bool(images_snapshot)
        # The isolated worker receives image bytes only for this request. Any
        # optional archive is a separate compressed copy in the local data folder.
        self.image_attachments.clear()
        self._refresh_image_attachments()
        self.busy = True
        self._refresh_agent_view()
        self.send_button.configure(state="disabled")
        self.interrupt_button.configure(state="normal", text=translate("中断任务", self.language))
        self.add_image_button.configure(state="disabled")
        self.input_box.configure(state="disabled")
        self.status.configure(text=translate("正在加载，等待 API 回复……", self.language))
        if images_snapshot:
            self.status.configure(text=translate(
                "正在处理图片，服务：{service}；模型：{model}……", self.language
            ).format(service=profile["name"], model=client.model))
        self.progress.grid()
        self.progress.start(12)

    def _poll_results(self) -> None:
        if not self.busy:
            self.root.after(100, self._poll_results)
            return
        if self._request_cancelled:
            self._finish_cancelled_request()
            return
        try:
            result = self._request_results.get_nowait()
        except queue.Empty:
            if self._request_worker_message is None:
                elapsed = int(time.monotonic() - self._request_started)
                self.status.configure(text=translate("正在等待模型回复（{seconds} 秒），可随时中断。", self.language).format(seconds=elapsed))
                if time.monotonic() > self._request_deadline:
                    self.interrupt_task()
                    return
            self.root.after(100, self._poll_results)
            return
        if result[0] == 'received':
            self._request_worker_message = result[1]
            self._request_committing = True
            self.interrupt_button.configure(state="disabled")
            self.status.configure(text=translate("请求已完成，正在安全保存账本结果……", self.language))
            threading.Thread(target=commit_request_result, args=(
                result[1], self.database_path, self._request_baseline_path,
                self._request_candidate_path, self._request_results,
                ('error', '', self._request_history_snapshot, self._request_pending_snapshot, None),
            ), daemon=True, name='ledger-request-commit').start()
            self.root.after(50, self._poll_results)
            return
        self._request_inserted_ids = result[2]
        try:
            self._finish_request(result[1])
        finally:
            # A callback/render error must never strand the whole window busy.
            if self.busy:
                self.busy = False
                self.progress.stop()
                self.progress.grid_remove()
                self.send_button.configure(state="normal")
                self.input_box.configure(state="normal")
                self.add_image_button.configure(state="normal")
                self.interrupt_button.configure(state="disabled")
                self._restore_pending_request()
                self._cleanup_request_worker()
                self.root.after(100, self._poll_results)

    def _finish_request(self, message: tuple[Any, ...]) -> None:
        status, answer, new_history, new_pending_state, usage = message
        inserted_transaction_ids = self._request_inserted_ids
        self.history = new_history
        self.pending_state = new_pending_state
        request_state = self.agent_states[self._request_agent_mode]
        request_state["history"] = self.history
        request_state["pending_state"] = self.pending_state
        if status == "ok":
            if self.pending_state is None:
                request_state["workflow_profile_id"] = None
            elif not request_state.get("workflow_profile_id"):
                request_state["workflow_profile_id"] = self._request_profile_id
        self._append_message("助手", answer, agent_mode=self._request_agent_mode)
        if status == "error":
            self.input_box.configure(state="normal")
            self._restore_pending_request()
        self._pending_draft_text = ""
        self._pending_had_images = False
        self._pending_image_attachments = []
        self.progress.stop()
        self.progress.grid_remove()
        if usage:
            self.status.configure(
                text=(
                    f"本轮模型用量：输入 {usage.get('prompt_tokens', 0):,} tokens "
                    f"（缓存命中 {usage.get('cache_hit_tokens', 0):,}），输出 "
                    f"{usage.get('completion_tokens', 0):,} tokens "
                    f"（思考 {usage.get('reasoning_tokens', 0):,}）；"
                    f"API 请求 {usage.get('requests', 0)} 次"
                )
            )
        else:
            self.status.configure(text="")
        self.busy = False
        self._refresh_agent_view()
        self.send_button.configure(state="normal")
        self.interrupt_button.configure(state="disabled", text=translate("中断任务", self.language))
        self.add_image_button.configure(state="normal")
        self.input_box.configure(state="normal")
        self.input_box.focus_set()
        self._cleanup_request_worker()
        if status == "ok" and inserted_transaction_ids:
            self._queue_github_auto_sync()
        self.root.after(100, self._poll_results)

    def _restore_pending_request(self) -> None:
        if self._pending_draft_text:
            self.input_box.delete("1.0", "end")
            self.input_box.insert("1.0", self._pending_draft_text)
        if self._pending_image_attachments:
            self.image_attachments = list(self._pending_image_attachments)
            self._refresh_image_attachments()

    def interrupt_task(self) -> None:
        if not self.busy or self._request_cancelled:
            return
        # A completed response is already ready to commit locally; cancellation
        # only applies while the isolated worker is still doing the request.
        if self._request_worker_message is not None:
            self._poll_results()
            return
        self._request_cancelled = True
        self.interrupt_button.configure(
            state="disabled",
            text=translate("正在中断……", self.language),
        )
        self.status.configure(text=translate("正在强制中断任务……", self.language))
        worker = self._request_process
        if worker is not None and worker.is_alive():
            try:
                worker.terminate()
                worker.join(timeout=0.15)
                if worker.is_alive():
                    worker.kill()
                    worker.join(timeout=0.15)
            except (OSError, ValueError):
                pass
        self.root.after(30, self._finish_cancelled_request)

    def _finish_cancelled_request(self) -> None:
        # Both the poller and the interrupt button may schedule this callback.
        # A stale callback must not clean up a newly submitted request.
        if not self._request_cancelled:
            return
        worker = self._request_process
        if worker is not None and worker.is_alive():
            self.root.after(50, self._finish_cancelled_request)
            return
        if worker is not None:
            worker.join()
        self._cleanup_request_worker()
        self.input_box.configure(state="normal")
        self._restore_pending_request()
        self._append_message(
            "助手",
            translate(
                "任务已中断，本次结果未写入本地账本。服务商可能已收到请求并继续处理。",
                self.language,
            ),
            agent_mode=self._request_agent_mode,
        )
        self._pending_draft_text = ""
        self._pending_had_images = False
        self._pending_image_attachments = []
        self.progress.stop()
        self.progress.grid_remove()
        self.status.configure(text=translate("任务已中断，本次结果未写入本地账本。", self.language))
        self.busy = False
        self._request_cancelled = False
        self._refresh_agent_view()
        self.send_button.configure(state="normal")
        self.interrupt_button.configure(state="disabled", text=translate("中断任务", self.language))
        self.add_image_button.configure(state="normal")
        self.input_box.configure(state="normal")
        self.input_box.focus_set()
        self.root.after(100, self._poll_results)

    def _cleanup_request_worker(self) -> None:
        self._request_committing = False
        if self._request_pipe is not None:
            try:
                self._request_pipe.close()
            except OSError:
                pass
        if self._request_process is not None:
            try:
                if not self._request_process.is_alive():
                    self._request_process.close()
            except (OSError, ValueError):
                pass
        if self._request_workspace is not None:
            shutil.rmtree(self._request_workspace, ignore_errors=True)
        self._request_process = None
        self._request_pipe = None
        self._request_workspace = None
        self._request_profile_id = None
        self._request_baseline_path = None
        self._request_candidate_path = None
        self._request_worker_message = None

    def _send_shortcut(self, _event: Any) -> str:
        self.send()
        return "break"

    def _refresh_input_after_change(self, event: Any) -> None:
        # Refresh after Tk receives the committed text, not on Return itself:
        # Windows IMEs may consume Return while composing a word.
        try:
            widget = event.widget
            if widget.edit_modified():
                widget.edit_modified(False)
                widget.after_idle(widget.update_idletasks)
        except tk.TclError:
            pass

    def restart_application(self, *, require_confirmation: bool = True) -> None:
        if self._restart_pending:
            return
        if self.busy or self._recurring_processing:
            messagebox.showinfo(
                "稍后重试",
                "记账或定期收支正在处理中，请等处理完成后再重启。",
                parent=self.root,
            )
            return
        if require_confirmation and not messagebox.askyesno(
            "确认重启",
            "将重新打开软件并关闭当前窗口。当前对话、未发送文字、图片和待确认草稿会丢失；已保存的账本数据不受影响。继续吗？",
            parent=self.root,
        ):
            return

        executable = Path(sys.executable)
        launcher = Path(__file__).resolve().parents[1] / "launch-bookkeeping.vbs"
        if getattr(sys, "frozen", False):
            app_directory = executable.parent
            command = [str(executable), "--restart-instance"]
        elif os.name == "nt" and launcher.is_file():
            # Let the launcher wait for this process to release its single-instance
            # mutex, then start a normal instance. A second Python process waiting
            # forever on the mutex can otherwise make repeated restarts appear dead.
            app_directory = launcher.parent
            command = ["wscript.exe", "//nologo", str(launcher), str(os.getpid())]
        else:
            app_directory = Path(__file__).resolve().parents[1]
            if executable.name.lower() == "python.exe":
                windowed_python = executable.with_name("pythonw.exe")
                if windowed_python.exists():
                    executable = windowed_python
            command = [str(executable), "-m", "bookkeeping.gui", "--restart-instance"]
        creation_flags = (
            getattr(subprocess, "CREATE_NO_WINDOW", 0)
            if os.name == "nt" and executable.name.lower() != "pythonw.exe"
            else 0
        )
        try:
            self._restart_pending = True
            process = subprocess.Popen(
                command,
                cwd=str(app_directory),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=creation_flags,
                close_fds=True,
            )
        except OSError as exc:
            self._restart_pending = False
            if self._github_restore_in_progress:
                self._github_restore_in_progress = False
                self.send_button.configure(state="normal")
                self.input_box.configure(state="normal")
            messagebox.showerror(
                "重启失败",
                translate("无法启动新窗口：{error}", self.language).format(error=exc),
                parent=self.root,
            )
            return
        self.root.after(700, lambda: self._finish_restart(process))

    def _finish_restart(self, process: subprocess.Popen[Any]) -> None:
        if process.poll() is not None:
            self._restart_pending = False
            if self._github_restore_in_progress:
                self._github_restore_in_progress = False
                self.send_button.configure(state="normal")
                self.input_box.configure(state="normal")
            messagebox.showerror(
                "重启失败",
                "新窗口未能保持运行；当前窗口仍然打开。请检查启动环境后重试。",
                parent=self.root,
            )
            return
        self.close()

    def close(self) -> None:
        self._startup_cancelled.set()
        if self._startup_applying or self._request_committing:
            self.root.after(100, self.close)
            return
        worker = self._request_process
        if worker is not None and worker.is_alive():
            try:
                worker.terminate()
                worker.join(timeout=1.0)
                if worker.is_alive():
                    worker.kill()
                    worker.join(timeout=5.0)
            except (OSError, ValueError):
                pass
        # Do not remove the disposable snapshot while its child might still use it.
        if worker is None or not worker.is_alive():
            self._cleanup_request_worker()
        self.progress.stop()
        self.root.destroy()

    def _clear_agent_context(self, mode: str) -> None:
        state = self.agent_states.get(mode)
        if state is None:
            return
        state["history"].clear()
        state["pending_state"] = None
        state["workflow_profile_id"] = None
        if mode == self.agent_mode:
            self.history = state["history"]
            self.pending_state = None

    def _reset_current_conversation(self) -> None:
        if self.busy:
            return
        mode = self.agent_mode
        state = self.agent_states[mode]
        self._clear_agent_context(mode)
        self._clear_agent_clients(mode)
        state["messages"].clear()
        welcome = (
            "我会先检索本地近期饮食记录，再交给饮食健康 Agent 单独配置的模型和 Skill 给出均衡饮食建议。记录不足时会说明限制；此模式不会修改记录。"
            if mode == "food_health"
            else "你好，直接告诉我一笔收入、消费、转账或还款。信息不够时我会先追问，确认后才写入本地账本。"
        )
        state["messages"].append(("助手", welcome))
        self.input_box.delete("1.0", "end")
        self.image_attachments.clear()
        self._refresh_image_attachments()
        self._pending_draft_text = ""
        self._pending_had_images = False
        self._pending_image_attachments = []
        self._refresh_agent_view()
        self.status.configure(text=translate("当前对话已重置，可以开始新的测试。", self.language))
        self.input_box.focus_set()

    def _reset_all_conversations(self) -> None:
        """Clear both Agent conversations when the app-wide response language changes."""
        for mode, state in self.agent_states.items():
            self._clear_agent_context(mode)
            state["messages"].clear()
            welcome = (
                "我会先检索本地近期饮食记录，再交给饮食健康 Agent 单独配置的模型和 Skill 给出均衡饮食建议。记录不足时会说明限制；此模式不会修改记录。"
                if mode == "food_health"
                else "你好，直接告诉我一笔收入、消费、转账或还款。信息不够时我会先追问，确认后才写入本地账本。"
            )
            state["messages"].append(("助手", welcome))
        self.history = self.agent_states[self.agent_mode]["history"]
        self.pending_state = None
        self._clear_agent_clients()
        self.input_box.delete("1.0", "end")
        self.image_attachments.clear()
        self._refresh_image_attachments()
        self._pending_draft_text = ""
        self._pending_had_images = False
        self._pending_image_attachments = []
        self._refresh_agent_view()

    def _clear_conversation_context(self) -> None:
        for mode in self.agent_states:
            self._clear_agent_context(mode)
        self.history = self.agent_states[self.agent_mode]["history"]
        self.pending_state = None


def main() -> None:
    multiprocessing.freeze_support()
    # Must run before creating Tk's first native window. Windows then renders
    # GDI text sharply at monitor DPI while keeping Tk's current layout scale.
    enable_windows_gdi_text_scaling()
    single_instance = SingleInstance(DEFAULT_DB, "家庭记账")
    restart_instance = "--restart-instance" in sys.argv[1:]
    if not single_instance.acquire(wait_for_existing=restart_instance):
        return
    try:
        root = TkinterDnD.Tk() if TkinterDnD is not None else tk.Tk()
        BookkeepingWindow(root)
        root.mainloop()
    finally:
        single_instance.release()


if __name__ == "__main__":
    main()
