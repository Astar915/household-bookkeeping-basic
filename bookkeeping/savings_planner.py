from __future__ import annotations

from .desktop_theme import color, fit_management_text, wrap_management_toolbar
from .desktop_frame import defer_during_interactive_resize

import json
import math
import queue
import re
import threading
from contextlib import nullcontext
import tkinter as tk
import unicodedata
import zlib
from datetime import date
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Any

try:
    from PIL import Image, ImageDraw, ImageTk
except ImportError:
    Image = None
    ImageDraw = None
    ImageTk = None

from .natural_language import _today_japan
from .storage import Database, LedgerError, billing_cycle, minor_to_text, to_minor_allow_zero
from .ui_confirm import confirm_delete_once
from .localization import translate


_PALETTE = (
    color("#3976b8"), color("#e58a3a"), color("#47a477"), color("#d85f62"), color("#8a6cc1"),
    color("#d2aa3c"), color("#4fabb4"), color("#c66c9a"), color("#728096"), color("#9b835f"),
)
_MONTHLY_PLAN_KEY = "savings_plan:monthly_template"


def _jpy_amount(row: Any) -> int | None:
    currency = str(row["currency"]).upper()
    if currency in {"JPY", "PTS"}:
        return int(row["amount_minor"])
    if row["jpy_equiv_minor"] is not None:
        return int(row["jpy_equiv_minor"])
    return None


def _month_starts(today: date, count: int = 12) -> list[date]:
    current = today.year * 12 + today.month - 1
    starts = []
    for offset in range(count - 1, -1, -1):
        serial = current - offset
        year, month_index = divmod(serial, 12)
        starts.append(date(year, month_index + 1, 1))
    return starts


def _read_plan(database: Database, key: str, fallback_key: str = "") -> dict[str, int]:
    raw = database.get_setting(key, "")
    if not raw and fallback_key:
        raw = database.get_setting(fallback_key, "")
    if not raw:
        return {}
    try:
        value = json.loads(raw)
    except (TypeError, ValueError):
        return {}
    items = value.get("items", {}) if isinstance(value, dict) else {}
    if not isinstance(items, dict):
        return {}
    plan: dict[str, int] = {}
    for name, amount in items.items():
        if isinstance(name, str) and name.strip() and isinstance(amount, int) and not isinstance(amount, bool) and amount >= 0:
            plan[name] = amount
    return plan


def _canonical_budget_category(name: str, ledger_categories: set[str]) -> str | None:
    """Map legacy budget labels to the ledger's fixed expense categories."""
    if name in ledger_categories:
        return name

    normalized = unicodedata.normalize("NFKC", name).casefold()
    if re.search(r"自炊|买菜|買菜|食材|牛奶|果蔬|食品|grocery|groceries|ingredients", normalized):
        candidate = "食材"
    elif re.search(
        r"餐饮|外食|午饭|午餐|晚饭|晚餐|早餐|聚餐|lunch|dinner|breakfast|dining|meal|ランチ|昼食|夕食|食事",
        normalized,
    ):
        candidate = "餐饮"
    elif re.search(
        r"水电|燃气|电费|水费|电话|通信|会员|订阅|utilities|electricity|gas|water|phone|subscription|bill",
        normalized,
    ):
        candidate = "通信与账单"
    elif re.search(r"日用品|日用|杂货|household|daily goods", normalized):
        candidate = "日用品"
    else:
        candidate = "其他"

    if candidate in ledger_categories:
        return candidate
    for fallback in ("其他", "日用品", "餐饮", "食材"):
        if fallback in ledger_categories:
            return fallback
    return next(iter(sorted(ledger_categories)), None)


def _normalize_plan_categories(plan: dict[str, int], ledger_categories: set[str]) -> dict[str, int]:
    """Merge old custom budget labels into fixed ledger categories without losing amounts."""
    normalized: dict[str, int] = {}
    for name, amount in plan.items():
        category = _canonical_budget_category(name, ledger_categories)
        if category is not None:
            normalized[category] = normalized.get(category, 0) + amount
    return normalized


def _draw_line_chart(canvas: tk.Canvas, values: list[int], labels: list[str], font_family: str) -> None:
    canvas.delete("all")
    canvas._chart_points = []
    width = max(120, canvas.winfo_width())
    height = max(100, canvas.winfo_height())
    left, right, top, bottom = 74, width - 18, 20, height - 46
    if right <= left or bottom <= top:
        return
    max_value = max(values, default=0)
    if max_value <= 0:
        top_value = 4
    else:
        magnitude = 10 ** max(0, int(math.log10(max_value)) - 1)
        step = max(magnitude, math.ceil(max_value / 4 / magnitude) * magnitude)
        top_value = step * 4

    scale = 3
    image = None
    drawing = None
    if Image is not None and ImageDraw is not None and ImageTk is not None:
        image = Image.new("RGB", (width * scale, height * scale), color("#ffffff"))
        drawing = ImageDraw.Draw(image)

    def draw_line(coords: tuple[float, float, float, float], color: str, thickness: int = 1) -> None:
        if drawing is not None:
            drawing.line(
                tuple(round(value * scale) for value in coords),
                fill=color, width=thickness * scale, joint="curve",
            )
        else:
            canvas.create_line(*coords, fill=color, width=thickness, smooth=True)

    for tick in range(5):
        y = bottom - (bottom - top) * tick / 4
        draw_line((left, y, right, y), color("#e6eaf0"))
    draw_line((left, top, left, bottom), color("#98a2b3"))
    draw_line((left, bottom, right, bottom), color("#98a2b3"))

    if values:
        count = len(values)
        x_span = right - left
        points: list[tuple[float, float]] = []
        for index, value in enumerate(values):
            x = left + (x_span * index / max(1, count - 1))
            y = bottom - ((bottom - top) * value / top_value)
            points.append((x, y))
        canvas._chart_points = [
            (x, y, int(values[index]), labels[index] if index < len(labels) else str(index + 1))
            for index, (x, y) in enumerate(points)
        ]
        if len(points) > 1:
            for start, end in zip(points, points[1:]):
                coords = tuple(round(value * scale) for value in (*start, *end))
                if drawing is not None:
                    drawing.line(coords, fill=color("#3976b8"), width=3 * scale, joint="curve")
                else:
                    canvas.create_line(*start, *end, fill=color("#3976b8"), width=3, smooth=True)
        for x, y in points:
            if drawing is not None:
                drawing.ellipse(
                    (round((x - 4) * scale), round((y - 4) * scale),
                     round((x + 4) * scale), round((y + 4) * scale)),
                    fill=color("#3976b8"), outline=color("#ffffff"), width=2 * scale,
                )
            else:
                canvas.create_oval(x - 4, y - 4, x + 4, y + 4, fill=color("#3976b8"), outline=color("#ffffff"), width=2)

    if image is not None and ImageTk is not None:
        resampling = getattr(Image, "Resampling", Image).LANCZOS
        image = image.resize((width, height), resampling)
        photo = ImageTk.PhotoImage(image, master=canvas)
        canvas._chart_photo = photo
        canvas.create_image(0, 0, anchor="nw", image=photo)

    for tick in range(5):
        value = top_value * tick / 4
        y = bottom - (bottom - top) * tick / 4
        canvas.create_text(
            left - 9, y, text=f"{int(value):,}", fill=color("#667085"),
            anchor="e", font=(font_family, 9),
        )
    label_count = min(6, len(values))
    for tick in range(label_count):
        index = round((len(values) - 1) * tick / max(1, label_count - 1))
        x = left + ((right - left) * index / max(1, len(values) - 1))
        canvas.create_text(
            x, bottom + 20, text=labels[index], fill=color("#667085"),
            anchor="n", font=(font_family, 9),
        )


def _display_entries(entries: list[tuple[str, int]]) -> list[tuple[str, int]]:
    cleaned = [(name, amount) for name, amount in entries if amount > 0]
    cleaned.sort(key=lambda item: item[1], reverse=True)
    if len(cleaned) <= 8:
        return cleaned
    visible = cleaned[:7]
    visible.append((str(translate("其他")), sum(amount for _, amount in cleaned[7:])))
    return visible


def _draw_pie_chart(
    canvas: tk.Canvas,
    entries: list[tuple[str, int]],
    font_family: str,
    category_colors: dict[str, str] | None = None,
) -> None:
    canvas.delete("all")
    width = max(160, canvas.winfo_width())
    height = max(120, canvas.winfo_height())
    visible = _display_entries(entries)
    total = sum(amount for _, amount in visible)
    if total <= 0:
        return

    legend_left = min(width * 0.58, 410)
    radius = max(35, min((height - 24) / 2, legend_left * 0.43))
    center_x = radius + 16
    center_y = height / 2
    box = (center_x - radius, center_y - radius, center_x + radius, center_y + radius)
    start = 90.0
    scale = 3
    image = None
    drawing = None
    if Image is not None and ImageDraw is not None and ImageTk is not None:
        image = Image.new("RGB", (width * scale, height * scale), color("#ffffff"))
        drawing = ImageDraw.Draw(image)
    colors = category_colors or {}

    def color_for(name: str) -> str:
        if name in colors:
            return colors[name]
        return _PALETTE[zlib.crc32(name.encode("utf-8")) % len(_PALETTE)]

    for name, amount in visible:
        extent = amount / total * 360
        slice_color = color_for(name)
        if drawing is not None:
            drawing.pieslice(
                tuple(round(value * scale) for value in box),
                start=start, end=start + extent, fill=slice_color,
                outline=color("#ffffff"), width=2 * scale,
            )
        else:
            canvas.create_arc(
                *box, start=start, extent=extent, style="pieslice",
                fill=slice_color, outline=color("#ffffff"), width=2,
            )
        start += extent

    if image is not None and ImageTk is not None:
        resampling = getattr(Image, "Resampling", Image).LANCZOS
        image = image.resize((width, height), resampling)
        photo = ImageTk.PhotoImage(image, master=canvas)
        canvas._chart_photo = photo
        canvas.create_image(0, 0, anchor="nw", image=photo)

    legend_x = center_x + radius + 16
    available_width = max(40, width - legend_x - 12)
    row_height = min(28, max(19, (height - 8) / max(1, len(visible))))
    for index, (name, amount) in enumerate(visible):
        y = 8 + index * row_height
        slice_color = color_for(name)
        canvas.create_rectangle(legend_x, y + 3, legend_x + 10, y + 13, fill=slice_color, outline=slice_color)
        max_chars = max(4, int((available_width - 100) / 10))
        short_name = name if len(name) <= max_chars else name[: max(2, max_chars - 1)] + "…"
        amount_label = f"{amount / total:.0%}  {minor_to_text(amount, 0, 'JPY')}"
        canvas.create_text(
            legend_x + 17, y + 8, text=short_name, fill=color("#344054"),
            anchor="w", font=(font_family, 10),
        )
        canvas.create_text(
            width - 8, y + 8, text=amount_label, fill=color("#667085"),
            anchor="e", font=(font_family, 9),
        )


def open_savings_plan(
    parent: tk.Misc,
    database_path: Path,
    font_family: str = "Segoe UI",
    *,
    container: tk.Misc | None = None,
    database_lock: Any = None,
) -> None:
    if container is None:
        dialog = tk.Toplevel(parent)
        dialog.title(translate("预算管理"))
        dialog.geometry("1080x660")
        dialog.minsize(960, 560)
        dialog.transient(parent)
        dialog.configure(bg=color("#f3f5f8"))
        dialog.protocol("WM_DELETE_WINDOW", dialog.destroy)
        dialog.bind("<Escape>", lambda _event: dialog.destroy())
        layout_parent: tk.Misc = dialog
    else:
        dialog = container.winfo_toplevel()
        layout_parent = container

    loading = ttk.Label(
        layout_parent, text=translate("正在读取预算数据…"), style="Hint.TLabel",
    )
    loading.grid(row=0, column=0, sticky="w", padx=16, pady=16)
    results: queue.Queue[tuple[dict[str, Any] | None, str | None]] = queue.Queue()

    def load_data() -> None:
        database: Database | None = None
        result = None
        error = None
        try:
            today = date.fromisoformat(_today_japan())
            cycle_start, cycle_end = billing_cycle(today)
            end_day = min(cycle_end, today)
            month_starts = _month_starts(today)
            setting_key = f"savings_plan:{cycle_start.isoformat()}"
            with (database_lock if database_lock is not None else nullcontext()):
                database = Database(database_path)
                categories = [
                    str(row["name"]) for row in database.connection.execute(
                        "SELECT name FROM categories WHERE kind='expense' AND is_active=1 ORDER BY name COLLATE NOCASE"
                    ).fetchall()
                ]
                ledger_categories = set(categories)
                rows = database.report_rows(month_starts[0].isoformat(), today.isoformat())
                plan = _normalize_plan_categories(
                    _read_plan(database, setting_key, _MONTHLY_PLAN_KEY), ledger_categories
                )
                database.close()
                database = None
            categories = sorted(ledger_categories)
            category_colors = {
                name: _PALETTE[index % len(_PALETTE)]
                for index, name in enumerate(categories)
            }
            category_colors[str(translate("其他"))] = category_colors.get("其他", _PALETTE[-1])

            daily = [0] * ((end_day - cycle_start).days + 1)
            monthly_totals = {month: 0 for month in month_starts}
            actual_by_category: dict[str, int] = {}
            missing_fx_count = 0
            for row in rows:
                if row["kind"] != "expense" or row["balance_effect"] != "posted":
                    continue
                amount = _jpy_amount(row)
                if amount is None:
                    missing_fx_count += 1
                    continue
                if amount <= 0:
                    continue
                occurred = date.fromisoformat(str(row["occurred_on"]))
                month_start = date(occurred.year, occurred.month, 1)
                if month_start in monthly_totals:
                    monthly_totals[month_start] += amount
                if cycle_start <= occurred <= end_day:
                    index = (occurred - cycle_start).days
                    if 0 <= index < len(daily):
                        daily[index] += amount
                    category = str(row["category_name"] or "未分类")
                    actual_by_category[category] = actual_by_category.get(category, 0) + amount
            result = {
                "today": today,
                "cycle_start": cycle_start,
                "cycle_end": cycle_end,
                "end_day": end_day,
                "month_starts": month_starts,
                "setting_key": setting_key,
                "categories": categories,
                "ledger_categories": ledger_categories,
                "plan": plan,
                "category_colors": category_colors,
                "daily": daily,
                "daily_labels": [
                    date.fromordinal(cycle_start.toordinal() + index).strftime("%m/%d")
                    for index in range(len(daily))
                ],
                "monthly_values": [monthly_totals[month] for month in month_starts],
                "monthly_labels": [month.strftime("%Y-%m") for month in month_starts],
                "actual_by_category": actual_by_category,
                "missing_fx_count": missing_fx_count,
            }
        except Exception as exc:
            error = str(exc)
        finally:
            if database is not None:
                try:
                    database.close()
                except Exception as exc:
                    if error is None:
                        error = str(exc)
        results.put((result, error))

    try:
        threading.Thread(target=load_data, name="savings-plan-reader", daemon=True).start()
    except RuntimeError as exc:
        loading.destroy()
        messagebox.showerror("无法打开", f"{translate('预算管理无法读取：')}{exc}", parent=parent)
        if container is None:
            dialog.destroy()
        return

    def poll_results() -> None:
        try:
            if not layout_parent.winfo_exists():
                return
            data, error = results.get_nowait()
        except queue.Empty:
            try:
                layout_parent.after(40, poll_results)
            except tk.TclError:
                pass
            return
        except tk.TclError:
            return
        try:
            loading.destroy()
        except tk.TclError:
            pass
        if error:
            messagebox.showerror("无法打开", f"{translate('预算管理无法读取：')}{error}", parent=parent)
            if container is None:
                try:
                    dialog.destroy()
                except tk.TclError:
                    pass
            else:
                ttk.Label(
                    layout_parent, text=translate("预算数据无法加载，请关闭后重试。"), style="Hint.TLabel",
                ).grid(row=0, column=0, sticky="w", padx=16, pady=16)
            return
        _build_savings_plan_loaded(
            parent, database_path, font_family, container=layout_parent,
            database_lock=database_lock, _loaded_data=data,
        )

    try:
        layout_parent.after(40, poll_results)
    except tk.TclError:
        pass


def _build_savings_plan_loaded(
    parent: tk.Misc,
    database_path: Path,
    font_family: str = "Segoe UI",
    *,
    container: tk.Misc | None = None,
    database_lock: Any = None,
    _loaded_data: dict[str, Any],
) -> None:
    today = _loaded_data["today"]
    cycle_start = _loaded_data["cycle_start"]
    cycle_end = _loaded_data["cycle_end"]
    end_day = _loaded_data["end_day"]
    month_starts = _loaded_data["month_starts"]
    setting_key = _loaded_data["setting_key"]
    categories = _loaded_data["categories"]
    ledger_categories = _loaded_data["ledger_categories"]
    plan = _loaded_data["plan"]
    category_colors = _loaded_data["category_colors"]
    daily = _loaded_data["daily"]
    daily_labels = _loaded_data["daily_labels"]
    monthly_values = _loaded_data["monthly_values"]
    monthly_labels = _loaded_data["monthly_labels"]
    actual_by_category = _loaded_data["actual_by_category"]
    missing_fx_count = _loaded_data["missing_fx_count"]

    if container is None:
        dialog = tk.Toplevel(parent)
        dialog.title(translate("预算管理"))
        dialog.geometry("1080x660")
        dialog.minsize(960, 560)
        dialog.transient(parent)
        dialog.configure(bg=color("#f3f5f8"))
        layout_parent: tk.Misc = dialog
    else:
        dialog = container.winfo_toplevel()
        layout_parent = container
    ttk.Style(dialog).configure(
        "BudgetSection.TLabel",
        background=color("#f3f5f8"),
        foreground=color("#344054"),
        font=(font_family, 12, "bold"),
    )
    layout_parent.columnconfigure(0, weight=1)
    layout_parent.rowconfigure(0, weight=1)

    shell = ttk.Frame(layout_parent, style="App.TFrame", padding=12)
    shell.grid(row=0, column=0, sticky="nsew")
    fit_management_text(shell)
    shell.columnconfigure(0, weight=1, uniform="planner-columns")
    shell.columnconfigure(1, weight=1, uniform="planner-columns")
    shell.rowconfigure(1, weight=1)

    ttk.Label(shell, text=translate("预算管理"), style="ManagementTitle.TLabel").grid(
        row=0, column=0, columnspan=2, sticky="w", pady=(0, 10)
    )
    left = ttk.Frame(shell, style="App.TFrame")
    right = ttk.Frame(shell, style="App.TFrame")
    left.grid(row=1, column=0, sticky="nsew", padx=(0, 8))
    right.grid(row=1, column=1, sticky="nsew", padx=(8, 0))
    left.columnconfigure(0, weight=1)
    right.columnconfigure(0, weight=1)
    left.rowconfigure(2, weight=1)
    left.rowconfigure(4, weight=1)
    right.rowconfigure(1, weight=1)
    right.rowconfigure(2, weight=1)

    range_text = f"{cycle_start.isoformat()} {translate('至')} {cycle_end.isoformat()}"
    ttk.Label(left, text=translate("本期花费"), style="BudgetSection.TLabel").grid(row=0, column=0, sticky="w")
    hint = translate("按15日至次月14日账期；人民币使用交易日汇率折算，缺少汇率的流水不计入图表。")
    total_spent = sum(actual_by_category.values())
    spent_label = translate("已入账支出：") + minor_to_text(total_spent, 0, "JPY")
    ttk.Label(left, text=f"{range_text}　{spent_label}\n{hint}", style="Hint.TLabel", wraplength=560).grid(
        row=1, column=0, sticky="ew", pady=(2, 8)
    )
    trend_frame = ttk.LabelFrame(left, text="支出趋势", padding=8)
    trend_frame.grid(row=2, column=0, sticky="nsew", pady=(0, 8))
    trend_frame.columnconfigure(0, weight=1)
    trend_frame.rowconfigure(1, weight=1)
    trend_toolbar = ttk.Frame(trend_frame)
    trend_toolbar.grid(row=0, column=0, sticky="ew", pady=(0, 4))
    ttk.Label(trend_toolbar, text="日度按本期账期；月度看近12个月", style="Hint.TLabel").pack(side="left")
    trend_mode = tk.StringVar(value="daily")
    mode_buttons = ttk.Frame(trend_toolbar)
    mode_buttons.pack(side="right")
    ttk.Radiobutton(
        mode_buttons, text="日度", variable=trend_mode, value="daily",
        style="Toolbutton", command=lambda: redraw(),
    ).pack(side="left")
    ttk.Radiobutton(
        mode_buttons, text="月度", variable=trend_mode, value="monthly",
        style="Toolbutton", command=lambda: redraw(),
    ).pack(side="left", padx=(3, 0))
    plot_area = ttk.Frame(trend_frame)
    plot_area.grid(row=1, column=0, sticky="nsew")
    trend_canvas = tk.Canvas(plot_area, bg=color("#ffffff"), highlightthickness=0, height=180)
    trend_canvas.pack(fill="both", expand=True)
    trend_empty = ttk.Label(plot_area, text="所选期间暂无已入账消费", style="Hint.TLabel")
    category_frame = ttk.LabelFrame(left, text="消费类别", padding=8)
    category_frame.grid(row=4, column=0, sticky="nsew")
    category_frame.columnconfigure(0, weight=1)
    category_frame.rowconfigure(0, weight=1)
    actual_pie_canvas = tk.Canvas(category_frame, bg=color("#ffffff"), highlightthickness=0, height=190)
    actual_pie_canvas.grid(row=0, column=0, sticky="nsew")
    actual_pie_empty = ttk.Label(category_frame, text="本期暂无分类支出", style="Hint.TLabel")

    budget_toolbar = ttk.Frame(right, style="App.TFrame")
    budget_toolbar.grid(row=0, column=0, sticky="ew", pady=(0, 8))
    budget_toolbar.columnconfigure(0, weight=1)
    budget_heading = ttk.Frame(budget_toolbar, style="App.TFrame")
    budget_heading.grid(row=0, column=0, sticky="ew")
    ttk.Label(budget_heading, text=translate("类别预算"), style="BudgetSection.TLabel").pack(side="left")
    total_label = ttk.Label(budget_heading, text="本期预算合计：0 JPY", style="Hint.TLabel")
    total_label.pack(side="right")
    budget_actions = ttk.Frame(budget_toolbar, style="App.TFrame")
    budget_actions.grid(row=1, column=0, sticky="ew", pady=(4, 0))
    edit_button = ttk.Button(budget_actions, text=translate("编辑所选预算"))
    edit_button.pack(side="left")
    add_budget_button = ttk.Button(budget_actions, text=translate("添加类别预算"))
    add_budget_button.pack(side="left", padx=(8, 0))
    remove_button = ttk.Button(budget_actions, text=translate("删除所选预算"))
    remove_button.pack(side="left", padx=(8, 0))
    wrap_management_toolbar(budget_actions)

    tree_frame = ttk.Frame(right, style="App.TFrame")
    tree_frame.grid(row=1, column=0, sticky="nsew", pady=(0, 9))
    tree_frame.columnconfigure(0, weight=1)
    tree_frame.rowconfigure(0, weight=1)
    columns = ("category", "budget", "spent", "remaining")
    column_specs = (
        ("category", "消费类别", 125, "w"),
        ("budget", "预算 JPY", 105, "e"),
        ("spent", "已花费 JPY", 105, "e"),
        ("remaining", "预算余量 JPY", 115, "e"),
    )
    # ttk.Treeview tags color whole rows, so render the remaining amount in a
    # synchronized sibling table to highlight only that cell when over budget.
    tree = ttk.Treeview(
        tree_frame, columns=columns[:3], show="headings", height=7, selectmode="browse"
    )
    remaining_tree = ttk.Treeview(
        tree_frame, columns=("remaining",), show="headings", height=7, selectmode="browse"
    )
    remaining_tree.tag_configure("over_budget", foreground=color("#d92d20"))
    for column, title, width, anchor in column_specs[:3]:
        tree.heading(column, text=title)
        tree.column(column, width=width, minwidth=70, anchor=anchor, stretch=column == "category")
    remaining_tree.heading(column_specs[3][0], text=column_specs[3][1])
    remaining_tree.column(
        column_specs[3][0],
        width=column_specs[3][2],
        minwidth=70,
        anchor=column_specs[3][3],
        stretch=False,
    )
    tree_frame.columnconfigure(1, weight=0)
    tree_frame.columnconfigure(2, weight=0)

    syncing_selection = False

    def sync_budget_selection(source: ttk.Treeview) -> None:
        nonlocal syncing_selection
        if syncing_selection:
            return
        target = remaining_tree if source is tree else tree
        selected = source.selection()
        syncing_selection = True
        try:
            existing = target.selection()
            if existing:
                target.selection_remove(*existing)
            valid = tuple(item_id for item_id in selected if target.exists(item_id))
            if valid:
                target.selection_set(*valid)
        finally:
            syncing_selection = False

    tree.bind("<<TreeviewSelect>>", lambda _event: sync_budget_selection(tree), add="+")
    remaining_tree.bind(
        "<<TreeviewSelect>>", lambda _event: sync_budget_selection(remaining_tree), add="+"
    )

    def scroll_budget_table(*args: Any) -> None:
        tree.yview(*args)

    syncing_scroll = False

    def sync_budget_scroll(source: ttk.Treeview, first: str, last: str) -> None:
        nonlocal syncing_scroll
        if not syncing_scroll:
            syncing_scroll = True
            target = remaining_tree if source is tree else tree
            try:
                target.yview_moveto(float(first))
            finally:
                syncing_scroll = False
        tree_scroll.set(first, last)

    tree_scroll = ttk.Scrollbar(tree_frame, orient="vertical", command=scroll_budget_table)
    tree.configure(
        yscrollcommand=lambda first, last: sync_budget_scroll(tree, first, last)
    )
    remaining_tree.configure(
        yscrollcommand=lambda first, last: sync_budget_scroll(remaining_tree, first, last)
    )
    tree.grid(row=0, column=0, sticky="nsew")
    remaining_tree.grid(row=0, column=1, sticky="nsew")
    tree_scroll.grid(row=0, column=2, sticky="ns")

    plan_frame = ttk.LabelFrame(right, text=translate("本期预算分配"), padding=8)
    plan_frame.grid(row=2, column=0, sticky="nsew")
    plan_frame.columnconfigure(0, weight=1)
    plan_frame.rowconfigure(0, weight=1)
    plan_pie_canvas = tk.Canvas(plan_frame, bg=color("#ffffff"), highlightthickness=0, height=280)
    plan_pie_canvas.grid(row=0, column=0, sticky="nsew")
    plan_pie_empty = ttk.Label(plan_frame, text=translate("添加类别预算后显示预算分配"), style="Hint.TLabel")

    save_results: queue.Queue[tuple[dict[str, int], str | None]] = queue.Queue()
    save_state = {"running": False, "poll_after": None, "previous_plan": None}

    def schedule_save_poll() -> None:
        if save_state["poll_after"] is not None:
            return
        try:
            if dialog.winfo_exists():
                save_state["poll_after"] = dialog.after(50, poll_save_results)
        except tk.TclError:
            save_state["poll_after"] = None

    def poll_save_results() -> None:
        save_state["poll_after"] = None
        try:
            if not dialog.winfo_exists():
                return
            previous_plan, error = save_results.get_nowait()
        except queue.Empty:
            if save_state["running"]:
                schedule_save_poll()
            return
        except tk.TclError:
            return
        save_state["running"] = False
        for button in (edit_button, add_budget_button, remove_button):
            button.configure(state="normal")
        if error:
            plan.clear()
            plan.update(previous_plan)
            refresh_plan()
            messagebox.showerror("无法保存", f"{translate('类别预算保存失败：')}{error}", parent=dialog)

    def persist_plan(previous_plan: dict[str, int]) -> bool:
        if save_state["running"]:
            return False
        save_state["running"] = True
        save_state["previous_plan"] = dict(previous_plan)
        for button in (edit_button, add_budget_button, remove_button):
            button.configure(state="disabled")
        payload = json.dumps({"items": dict(plan)}, ensure_ascii=False)

        def save() -> None:
            database: Database | None = None
            error = None
            try:
                with (database_lock if database_lock is not None else nullcontext()):
                    database = Database(database_path)
                    try:
                        database.set_setting(setting_key, payload, "本期各类别预算（JPY）")
                    finally:
                        database.close()
                        database = None
            except Exception as exc:
                error = str(exc)
            finally:
                if database is not None:
                    try:
                        database.close()
                    except Exception:
                        pass
            save_results.put((dict(previous_plan), error))

        try:
            threading.Thread(target=save, name="savings-plan-writer", daemon=True).start()
        except RuntimeError as exc:
            save_state["running"] = False
            for button in (edit_button, add_budget_button, remove_button):
                button.configure(state="normal")
            messagebox.showerror("无法保存", f"{translate('类别预算保存失败：')}{exc}", parent=dialog)
            return False
        schedule_save_poll()
        return True

    def refresh_plan() -> None:
        tree.delete(*tree.get_children())
        remaining_tree.delete(*remaining_tree.get_children())
        for category in sorted(plan):
            budget = int(plan[category])
            tracked = category in ledger_categories
            spent = actual_by_category.get(category, 0) if tracked else None
            remaining = budget - spent if spent is not None else None
            tree.insert(
                "",
                "end",
                iid=category,
                values=(
                    category,
                    minor_to_text(budget, 0, "JPY"),
                    minor_to_text(spent, 0, "JPY") if spent is not None else "—",
                ),
            )
            remaining_tree.insert(
                "",
                "end",
                iid=category,
                values=(minor_to_text(remaining, 0, "JPY") if remaining is not None else "—",),
                tags=("over_budget",) if remaining is not None and remaining < 0 else (),
            )
        total = sum(plan.values())
        total_label.configure(text=f"{translate('本期预算合计：')}{minor_to_text(total, 0, 'JPY')}")
        _draw_pie_chart(plan_pie_canvas, list(plan.items()), font_family, category_colors)
        if any(plan.values()):
            plan_pie_empty.place_forget()
        else:
            plan_pie_empty.configure(
                text=translate(
                    "类别预算均为0，暂无分配" if plan else "添加类别预算后显示预算分配"
                )
            )
            plan_pie_empty.place(relx=0.5, rely=0.5, anchor="center")

    def open_category_budget_dialog(editing: bool) -> None:
        category = ""
        if editing:
            selection = tree.selection()
            if not selection:
                messagebox.showinfo(
                    translate("未选择预算"),
                    translate("请先选择要编辑的类别预算。"),
                    parent=dialog,
                )
                return
            category = selection[0]

        editor = tk.Toplevel(dialog)
        editor.title(translate("编辑预算" if editing else "添加类别预算"))
        editor.geometry("460x240" if editing else "480x260")
        editor.resizable(False, False)
        editor.transient(dialog)
        editor.configure(bg=color("#f3f5f8"))

        form = ttk.Frame(editor, style="App.TFrame", padding=12)
        form.pack(fill="both", expand=True)
        form.columnconfigure(1, weight=1)
        ttk.Label(form, text=translate("消费类别"), style="Hint.TLabel").grid(
            row=0, column=0, sticky="w", padx=(0, 12), pady=(0, 10)
        )
        category_var = tk.StringVar(value=category)
        category_box = ttk.Combobox(
            form,
            textvariable=category_var,
            values=categories,
            state="readonly",
        )
        category_box.grid(row=0, column=1, sticky="ew", pady=(0, 10))
        ttk.Label(form, text=translate("本期预算（JPY）"), style="Hint.TLabel").grid(
            row=1, column=0, sticky="w", padx=(0, 12), pady=(0, 10)
        )
        amount_var = tk.StringVar(value=str(plan.get(category, 0)) if editing else "")
        amount_entry = ttk.Entry(form, textvariable=amount_var, width=20)
        amount_entry.grid(row=1, column=1, sticky="w", pady=(0, 10))

        def save_category_budget() -> None:
            selected_category = category_var.get().strip()
            if not selected_category:
                messagebox.showerror(
                    translate("无法保存"),
                    translate("请先选择消费类别。"),
                    parent=editor,
                )
                return
            if editing and category not in plan:
                messagebox.showerror(
                    translate("无法保存"),
                    translate("所编辑的类别预算已不存在，请取消编辑后重试。"),
                    parent=editor,
                )
                return
            if editing and selected_category != category and selected_category in plan:
                messagebox.showinfo(
                    translate("类别预算已存在"),
                    translate("该类别已有预算，请使用“编辑所选预算”修改。"),
                    parent=editor,
                )
                return
            if not editing and selected_category in plan:
                messagebox.showinfo(
                    translate("类别预算已存在"),
                    translate("该类别已有预算，请使用“编辑所选预算”修改。"),
                    parent=editor,
                )
                return
            try:
                amount = to_minor_allow_zero(amount_var.get().strip(), "JPY", 0)
            except LedgerError as exc:
                messagebox.showerror(
                    translate("无法保存"),
                    f"{translate('请输入有效的日元预算金额。')}\n{exc}",
                    parent=editor,
                )
                return
            previous_plan = dict(plan)
            if editing:
                plan.pop(category, None)
            plan[selected_category] = amount
            if not persist_plan(previous_plan):
                plan.clear()
                plan.update(previous_plan)
                return
            refresh_plan()
            tree.selection_set(selected_category)
            remaining_tree.selection_set(selected_category)
            editor.destroy()

        buttons = ttk.Frame(form, style="App.TFrame")
        buttons.grid(row=2, column=0, columnspan=2, sticky="e", pady=(8, 0))
        ttk.Button(buttons, text=translate("取消"), command=editor.destroy).pack(
            side="right", padx=(8, 0)
        )
        ttk.Button(
            buttons,
            text=translate("保存"),
            style="Send.TButton",
            command=save_category_budget,
        ).pack(side="right")
        editor.bind("<Return>", lambda _event: save_category_budget())
        editor.bind("<Escape>", lambda _event: editor.destroy())
        editor.grab_set()
        editor.after_idle(category_box.focus_set if not editing else amount_entry.focus_set)

    def remove_category_budget() -> None:
        selection = tree.selection()
        if not selection:
            messagebox.showinfo(translate("未选择预算"), translate("请先选择要删除的类别预算。"), parent=dialog)
            return
        category = selection[0]
        if not confirm_delete_once(
            dialog,
            title="删除类别预算",
            target=category,
            impact="只移除该类别本期预算设定，不会删除账务流水。",
        ):
            return
        previous_plan = dict(plan)
        plan.pop(category, None)
        if not persist_plan(previous_plan):
            plan.clear()
            plan.update(previous_plan)
            return
        refresh_plan()

    edit_button.configure(command=lambda: open_category_budget_dialog(editing=True))
    add_budget_button.configure(command=lambda: open_category_budget_dialog(editing=False))
    remove_button.configure(command=remove_category_budget)

    def redraw(_event: Any = None) -> None:
        if not dialog.winfo_exists():
            return
        if defer_during_interactive_resize(dialog, (dialog, "budget-charts"), lambda: redraw()):
            return
        if trend_mode.get() == "monthly":
            trend_values, trend_labels = monthly_values, monthly_labels
        else:
            trend_values, trend_labels = daily, daily_labels
        _draw_line_chart(trend_canvas, trend_values, trend_labels, font_family)
        _draw_pie_chart(
            actual_pie_canvas, list(actual_by_category.items()), font_family, category_colors
        )
        if actual_by_category:
            actual_pie_empty.place_forget()
        else:
            actual_pie_empty.place(relx=0.5, rely=0.5, anchor="center")
        if any(trend_values):
            trend_empty.place_forget()
        else:
            trend_empty.place(relx=0.5, rely=0.5, anchor="center")

    hovered_point: int | None = None

    def hide_trend_tooltip(_event: Any = None) -> None:
        nonlocal hovered_point
        trend_canvas.delete("trend-hover-tooltip")
        hovered_point = None

    def show_trend_tooltip(event: tk.Event) -> None:
        nonlocal hovered_point
        points = getattr(trend_canvas, "_chart_points", [])
        if not points:
            hide_trend_tooltip()
            return
        nearest_index, nearest = min(
            enumerate(points),
            key=lambda item: (item[1][0] - event.x) ** 2 + (item[1][1] - event.y) ** 2,
        )
        x, y, amount, label = nearest
        if (x - event.x) ** 2 + (y - event.y) ** 2 > 100:
            hide_trend_tooltip()
            return
        if (
            hovered_point == nearest_index
            and trend_canvas.find_withtag("trend-hover-tooltip")
        ):
            return

        trend_canvas.delete("trend-hover-tooltip")
        hovered_point = nearest_index
        text_id = trend_canvas.create_text(
            x + 12,
            y - 10,
            text=f"{label} 消费：{amount:,} JPY",
            anchor="sw",
            fill=color("#1d2939"),
            font=(font_family, 9),
            tags=("trend-hover-tooltip",),
        )
        bounds = trend_canvas.bbox(text_id)
        if bounds is None:
            return
        shift_x = min(0, trend_canvas.winfo_width() - 6 - bounds[2])
        shift_x = max(5 - bounds[0], shift_x)
        shift_y = max(0, 5 - bounds[1])
        if shift_x or shift_y:
            trend_canvas.move(text_id, shift_x, shift_y)
            bounds = trend_canvas.bbox(text_id)
        if bounds is not None:
            background_id = trend_canvas.create_rectangle(
                bounds[0] - 6,
                bounds[1] - 4,
                bounds[2] + 6,
                bounds[3] + 4,
                fill=color("#ffffff"),
                outline=color("#3976b8"),
                width=1,
                tags=("trend-hover-tooltip",),
            )
            trend_canvas.tag_lower(background_id, text_id)

    trend_canvas.bind("<Configure>", redraw)
    trend_canvas.bind("<Motion>", show_trend_tooltip)
    trend_canvas.bind("<Leave>", hide_trend_tooltip)
    actual_pie_canvas.bind("<Configure>", redraw)
    def redraw_plan_chart(_event: Any = None) -> None:
        if not plan_pie_canvas.winfo_exists():
            return
        callback = lambda: _draw_pie_chart(
            plan_pie_canvas, list(plan.items()), font_family, category_colors
        )
        if defer_during_interactive_resize(
                plan_pie_canvas, plan_pie_canvas, callback):
            return
        callback()

    plan_pie_canvas.bind("<Configure>", redraw_plan_chart)
    dialog.after_idle(redraw)
    refresh_plan()

    if missing_fx_count:
        ttk.Label(
            left,
            text=f"{translate('缺少交易日汇率，未计入图表的支出：')}{missing_fx_count} {translate('笔')}",
            style="Hint.TLabel",
        ).grid(row=5, column=0, sticky="w", pady=(5, 0))

    closed = False

    def close_dialog() -> None:
        nonlocal closed
        if closed:
            return
        closed = True
        if container is None:
            dialog.destroy()

    if container is None:
        dialog.protocol("WM_DELETE_WINDOW", close_dialog)
        dialog.bind("<Escape>", lambda _event: close_dialog())
    else:
        container.bind(
            "<Destroy>",
            lambda event: close_dialog() if event.widget is container else None,
            add="+",
        )
