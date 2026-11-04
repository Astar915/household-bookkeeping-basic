from __future__ import annotations

from .desktop_theme import color, fit_management_text, wrap_management_toolbar

import sqlite3
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Any

from .depreciation import fixed_asset_values as _asset_values
from .depreciation import monthly_depreciation_minor
from .localization import translate_tree_item
from .natural_language import _today_japan
from .storage import Database, LedgerError, minor_to_text, to_minor
from .ui_confirm import confirm_delete_once


def open_fixed_asset_management(root: tk.Misc, database_path: Path) -> None:
    # The Tk localization wrapper captures source labels and refreshes this
    # window if the application language changes.
    tr = lambda value: value
    database = Database(database_path)
    try:
        database.initialize()
        currencies = {
            str(row["code"]): int(row["minor_digits"])
            for row in database.connection.execute(
                "SELECT code,minor_digits FROM currencies WHERE is_monetary=1 ORDER BY code"
            )
        }
    except (LedgerError, sqlite3.Error) as exc:
        database.close()
        messagebox.showerror(tr("无法打开固定资产"), str(exc), parent=root)
        return

    dialog = tk.Toplevel(root)
    dialog.title("固定资产与折旧")
    dialog.geometry("1080x660")
    dialog.minsize(900, 560)
    dialog.transient(root)
    dialog.configure(bg=color("#f3f5f8"))

    panel = ttk.Frame(dialog, style="App.TFrame", padding=12)
    panel.pack(fill="both", expand=True)
    fit_management_text(panel)
    panel.columnconfigure(0, weight=1)
    panel.rowconfigure(3, weight=1)
    ttk.Label(panel, text="固定资产与折旧", style="ManagementTitle.TLabel").grid(
        row=0, column=0, sticky="w"
    )
    ttk.Label(
        panel,
        text="按购入月份和预计使用月数计算直线折旧，购入月份计为第1个月。折旧只用于资产负债表账面价值，不新增利润表费用，也不改动原购买流水。报废后从报废月份起移出资产负债表；报废时剩余价值保留为参考信息。是否计入资产负债表，请在“家庭财务报表→资产负债表”中点击每项前的方框设置。",
        style="Hint.TLabel",
        wraplength=1240,
        justify="left",
    ).grid(row=1, column=0, sticky="ew", pady=(4, 8))

    actions = ttk.Frame(panel, style="App.TFrame")
    actions.grid(row=2, column=0, sticky="ew", pady=(0, 8))

    columns = (
        "name", "month", "cost", "monthly", "life", "depreciated", "book_value", "progress", "status",
    )
    tree = ttk.Treeview(panel, columns=columns, show="headings", height=10, selectmode="browse")
    headings = (
        ("name", "资产名称", 175, "w"),
        ("month", "购入月份", 92, "center"),
        ("cost", "购入金额", 115, "e"),
        ("monthly", "每月折旧", 115, "e"),
        ("life", "预计使用", 88, "center"),
        ("depreciated", "累计折旧", 115, "e"),
        ("book_value", "剩余账面价值", 135, "e"),
        ("progress", "折旧进度", 110, "center"),
        ("status", "状态", 115, "center"),
    )
    for column, heading, width, anchor in headings:
        tree.heading(column, text=heading)
        tree.column(column, width=width, minwidth=65, anchor=anchor, stretch=column == "name")
    tree.tag_configure("disposed", foreground=color("#667085"))
    tree.tag_configure("excluded", foreground=color("#667085"))
    tree.grid(row=3, column=0, sticky="nsew")
    vertical = ttk.Scrollbar(panel, orient="vertical", command=tree.yview)
    vertical.grid(row=3, column=1, sticky="ns")
    horizontal = ttk.Scrollbar(panel, orient="horizontal", command=tree.xview)
    horizontal.grid(row=4, column=0, sticky="ew")
    tree.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)

    detail = ttk.LabelFrame(panel, text="选中资产的折旧情况", padding=12)
    detail.grid(row=5, column=0, sticky="ew", pady=(12, 0))
    detail.columnconfigure(0, weight=1)
    progress_row = ttk.Frame(detail, style="App.TFrame")
    progress_row.grid(row=0, column=0, sticky="ew")
    progress_row.columnconfigure(0, weight=1)
    progress_bar = ttk.Progressbar(progress_row, mode="determinate", maximum=24, value=0)
    progress_bar.grid(row=0, column=0, sticky="ew", padx=(0, 10))
    progress_label = ttk.Label(progress_row, text="", style="Hint.TLabel", width=30)
    progress_label.grid(row=0, column=1, sticky="e")
    value_label = ttk.Label(detail, text="", style="Hint.TLabel", wraplength=1180)
    value_label.grid(row=1, column=0, sticky="ew", pady=(7, 0))

    footer = ttk.Frame(panel, style="App.TFrame")
    footer.grid(row=6, column=0, sticky="ew", pady=(10, 0))
    status_label = ttk.Label(footer, text="", style="Hint.TLabel")
    status_label.pack(side="left", fill="x", expand=True)

    def month_now() -> str:
        return _today_japan()[:7]

    def run_action(action: Any) -> None:
        try:
            action()
        except Exception as exc:
            messagebox.showerror(tr("操作失败"), str(exc), parent=dialog)

    def selected_asset() -> Any | None:
        selection = tree.selection()
        if not selection:
            return None
        return next(
            (asset for asset in database.list_fixed_assets() if int(asset["id"]) == int(selection[0])),
            None,
        )

    def render_selected(_event: Any = None) -> None:
        asset = selected_asset()
        if asset is None:
            progress_bar.configure(maximum=1, value=0)
            progress_label.configure(text="")
            value_label.configure(text="请选择一项固定资产查看折旧进度。")
            return
        reference_month = month_now()
        if asset["disposal_month"] and str(asset["disposal_month"]) < reference_month:
            reference_month = str(asset["disposal_month"])
        elapsed, accumulated, remaining = _asset_values(asset, reference_month)
        life = int(asset["useful_life_months"])
        elapsed_for_bar = min(life, elapsed)
        percentage = min(100, elapsed_for_bar * 100 // life)
        digits = currencies[str(asset["currency"])]
        monthly_value = monthly_depreciation_minor(
            int(asset["cost_minor"]), life, 1
        )
        progress_bar.configure(maximum=life, value=elapsed_for_bar)
        progress_label.configure(
            text="{elapsed}/{life}个月 · {percent}%".format(
                elapsed=elapsed_for_bar, life=life, percent=percentage
            )
        )
        detail_text = "每月折旧：{monthly}　累计折旧：{depreciated}　剩余账面价值：{remaining}　购入原值：{cost}".format(
            monthly=minor_to_text(monthly_value, digits, str(asset["currency"])),
            depreciated=minor_to_text(accumulated, digits, str(asset["currency"])),
            remaining=minor_to_text(remaining, digits, str(asset["currency"])),
            cost=minor_to_text(int(asset["cost_minor"]), digits, str(asset["currency"])),
        )
        if asset["disposal_month"]:
            detail_text += "　报废月份：{month}；该月起不计入资产负债表。".format(
                month=asset["disposal_month"]
            )
        value_label.configure(text=detail_text)

    def refresh(select_id: int | None = None) -> None:
        current_month = month_now()
        tree.delete(*tree.get_children())
        tree._bk_i18n_item_values = {}
        tree._bk_i18n_row_translatable = {}
        assets = database.list_fixed_assets()
        for asset in assets:
            asset_id = int(asset["id"])
            currency = str(asset["currency"])
            digits = currencies[currency]
            reference_month = current_month
            if asset["disposal_month"] and str(asset["disposal_month"]) < reference_month:
                reference_month = str(asset["disposal_month"])
            elapsed, accumulated, remaining = _asset_values(asset, reference_month)
            life = int(asset["useful_life_months"])
            progress_months = min(life, elapsed)
            progress_percent = min(100, progress_months * 100 // life)
            monthly_value = monthly_depreciation_minor(
                int(asset["cost_minor"]), life, 1
            )
            if str(asset["acquisition_month"]) > current_month:
                state = "尚未购入"
            elif asset["disposal_month"] and str(asset["disposal_month"]) > current_month:
                state = "计划报废 " + str(asset["disposal_month"])
            elif asset["disposal_month"]:
                state = "已报废 " + str(asset["disposal_month"])
            else:
                state = "使用中"
            tags: tuple[str, ...] = ()
            if asset["disposal_month"]:
                tags = ("disposed",)
            elif not bool(asset["include_in_balance_sheet"]):
                tags = ("excluded",)
            source_values = (
                str(asset["name"]), str(asset["acquisition_month"]),
                minor_to_text(int(asset["cost_minor"]), digits, currency),
                minor_to_text(monthly_value, digits, currency),
                "{months}个月".format(months=life),
                minor_to_text(accumulated, digits, currency),
                minor_to_text(remaining, digits, currency),
                "{percent}% · {elapsed}/{life}".format(
                    percent=progress_percent, elapsed=progress_months, life=life
                ),
                state,
            )
            display_values = tuple(
                translate_tree_item(value) if index in {4, 7, 8} else value
                for index, value in enumerate(source_values)
            )
            item_id = tree.insert(
                "", "end", iid=str(asset_id),
                values=display_values,
                tags=tags,
            )
            tree._bk_i18n_item_values[item_id] = source_values
            tree._bk_i18n_row_translatable[item_id] = {4, 7, 8}
        if select_id is not None and tree.exists(str(select_id)):
            tree.selection_set(str(select_id))
            tree.focus(str(select_id))
        elif assets:
            first_id = str(assets[0]["id"])
            tree.selection_set(first_id)
            tree.focus(first_id)
        render_selected()
        status_label.configure(
            text="共登记 {count} 项；截至 {month} 的进度按月份计算。".format(
                count=len(assets), month=current_month
            )
        )

    def open_editor(asset: Any | None = None) -> None:
        editor = tk.Toplevel(dialog)
        editor.title("编辑固定资产" if asset is not None else "登记固定资产")
        editor.geometry("560x520")
        editor.resizable(False, False)
        editor.transient(dialog)
        form = ttk.Frame(editor, padding=18)
        form.pack(fill="both", expand=True)
        form.columnconfigure(1, weight=1)
        name_var = tk.StringVar(value=str(asset["name"]) if asset else "")
        month_var = tk.StringVar(value=str(asset["acquisition_month"]) if asset else month_now())
        cost_var = tk.StringVar(value="")
        if asset:
            cost_var.set(minor_to_text(
                int(asset["cost_minor"]), currencies[str(asset["currency"])], str(asset["currency"])
            ).rsplit(" ", 1)[0])
        currency_var = tk.StringVar(value=str(asset["currency"]) if asset else ("JPY" if "JPY" in currencies else next(iter(currencies))))
        life_var = tk.StringVar(value=str(asset["useful_life_months"]) if asset else "24")
        disposal_var = tk.StringVar(value=str(asset["disposal_month"] or "") if asset else "")

        name_entry = ttk.Entry(form, textvariable=name_var)
        fields = (
            ("资产名称", name_entry),
            ("购入月份（支持202608、8月）", ttk.Entry(form, textvariable=month_var)),
            ("购入金额", ttk.Entry(form, textvariable=cost_var)),
        )
        for row_number, (label, widget) in enumerate(fields):
            ttk.Label(form, text=label, style="Hint.TLabel").grid(
                row=row_number * 2, column=0, sticky="w", pady=(0, 2)
            )
            widget.grid(row=row_number * 2 + 1, column=0, columnspan=2, sticky="ew", pady=(0, 10))
        ttk.Label(form, text="币种", style="Hint.TLabel").grid(row=6, column=0, sticky="w", pady=(0, 2))
        currency_box = ttk.Combobox(
            form, textvariable=currency_var, values=tuple(sorted(currencies)), state="readonly", width=12
        )
        currency_box.grid(row=7, column=0, sticky="w", pady=(0, 10))
        ttk.Label(form, text="预计使用月数", style="Hint.TLabel").grid(row=8, column=0, sticky="w", pady=(0, 2))
        ttk.Entry(form, textvariable=life_var, width=14).grid(row=9, column=0, sticky="w", pady=(0, 10))
        ttk.Label(form, text="报废月份（可留空，支持202608、8月）", style="Hint.TLabel").grid(row=10, column=0, sticky="w", pady=(0, 2))
        ttk.Entry(form, textvariable=disposal_var).grid(row=11, column=0, columnspan=2, sticky="ew", pady=(0, 7))
        ttk.Label(
            form,
            text="金额按该币种最小单位存储；月度舍入差额会在使用期内分配，累计折旧不会超过原值。",
            style="Hint.TLabel",
            wraplength=510,
        ).grid(row=12, column=0, columnspan=2, sticky="ew", pady=(3, 12))
        button_row = ttk.Frame(form, style="App.TFrame")
        button_row.grid(row=13, column=0, columnspan=2, sticky="e")

        def save() -> None:
            try:
                digits = currencies[currency_var.get()]
                cost_minor = to_minor(cost_var.get(), currency_var.get(), digits)
                try:
                    useful_life = int(life_var.get().strip())
                except ValueError as exc:
                    raise LedgerError("预计使用月数必须是整数") from exc
                saved_id = database.save_fixed_asset(
                    asset_id=int(asset["id"]) if asset is not None else None,
                    name=name_var.get(),
                    acquisition_month=month_var.get(),
                    cost_minor=cost_minor,
                    currency=currency_var.get(),
                    useful_life_months=useful_life,
                    include_in_balance_sheet=(
                        bool(asset["include_in_balance_sheet"]) if asset is not None else False
                    ),
                    disposal_month=disposal_var.get().strip() or None,
                )
            except (LedgerError, sqlite3.Error, KeyError) as exc:
                messagebox.showerror(tr("保存失败"), str(exc), parent=editor)
                return
            editor.destroy()
            refresh(saved_id)

        ttk.Button(button_row, text="取消", command=editor.destroy).pack(side="right", padx=(8, 0))
        ttk.Button(button_row, text="保存", style="Send.TButton", command=save).pack(side="right")
        editor.bind("<Escape>", lambda _event: editor.destroy())
        # Give the child window an explicit on-screen position. On Windows,
        # an unpositioned transient Toplevel can be created behind its parent.
        editor.update_idletasks()
        width = min(560, max(420, editor.winfo_screenwidth() - 24))
        height = min(520, max(380, editor.winfo_screenheight() - 72))
        parent_x = dialog.winfo_rootx()
        parent_y = dialog.winfo_rooty()
        parent_width = dialog.winfo_width()
        parent_height = dialog.winfo_height()
        x = parent_x + max(0, (parent_width - width) // 2)
        y = parent_y + max(0, (parent_height - height) // 2)
        x = min(max(8, x), editor.winfo_screenwidth() - width - 8)
        y = min(max(8, y), editor.winfo_screenheight() - height - 8)
        editor.geometry(f"{width}x{height}+{x}+{y}")
        editor.deiconify()
        editor.lift()
        editor.grab_set()
        name_entry.focus_set()

    def edit_selected() -> None:
        asset = selected_asset()
        if asset is None:
            messagebox.showinfo(tr("请选择资产"), tr("请先选择一项固定资产。"), parent=dialog)
            return
        open_editor(asset)

    def dispose_selected() -> None:
        asset = selected_asset()
        if asset is None:
            messagebox.showinfo(tr("请选择资产"), tr("请先选择一项固定资产。"), parent=dialog)
            return
        if asset["disposal_month"]:
            messagebox.showinfo(
                tr("资产已报废"),
                tr("该资产已标记为报废月份 {month}；如需修改，请编辑资产记录。").format(
                    month=asset["disposal_month"]
                ),
                parent=dialog,
            )
            return
        disposal_month = month_now()
        if disposal_month < str(asset["acquisition_month"]):
            messagebox.showerror(tr("无法报废"), tr("报废月份不能早于购入月份。"), parent=dialog)
            return
        if not messagebox.askyesno(
            tr("确认标记报废"),
            tr(
                "将“{name}”标记为 {month} 报废。该月起从资产负债表移除；报废时剩余账面价值仅保留参考，不会自动记入利润表。"
            ).format(name=asset["name"], month=disposal_month),
            parent=dialog,
        ):
            return
        try:
            database.save_fixed_asset(
                asset_id=int(asset["id"]),
                name=str(asset["name"]),
                acquisition_month=str(asset["acquisition_month"]),
                cost_minor=int(asset["cost_minor"]),
                currency=str(asset["currency"]),
                useful_life_months=int(asset["useful_life_months"]),
                include_in_balance_sheet=bool(asset["include_in_balance_sheet"]),
                disposal_month=disposal_month,
            )
        except (LedgerError, sqlite3.Error) as exc:
            messagebox.showerror(tr("更新失败"), str(exc), parent=dialog)
            return
        refresh(int(asset["id"]))

    def delete_selected() -> None:
        asset = selected_asset()
        if asset is None:
            messagebox.showinfo(tr("请选择资产"), tr("请先选择一项固定资产。"), parent=dialog)
            return
        if not confirm_delete_once(
            dialog,
            title=tr("删除固定资产登记"),
            target=str(asset["name"]),
            impact=tr("只删除该资产登记和折旧进度，不会删除或改写原有购买流水。"),
        ):
            return
        try:
            database.delete_fixed_asset(int(asset["id"]))
        except (LedgerError, sqlite3.Error) as exc:
            messagebox.showerror(tr("删除失败"), str(exc), parent=dialog)
            return
        refresh()

    ttk.Button(
        actions, text="＋ 登记固定资产", style="Settings.TButton",
        command=lambda: run_action(open_editor),
    ).pack(side="left", padx=(0, 8))
    ttk.Button(actions, text="编辑选中项", command=lambda: run_action(edit_selected)).pack(side="left", padx=(0, 8))
    ttk.Button(actions, text="设为本月报废", command=lambda: run_action(dispose_selected)).pack(side="left", padx=(0, 8))
    ttk.Button(actions, text="删除登记", command=lambda: run_action(delete_selected)).pack(side="left")
    ttk.Button(footer, text="关闭", command=lambda: close()).pack(side="right")
    tree.bind("<<TreeviewSelect>>", lambda event: run_action(lambda: render_selected(event)))
    tree.bind("<Double-1>", lambda _event: run_action(edit_selected))

    def close() -> None:
        try:
            database.close()
        finally:
            dialog.destroy()

    wrap_management_toolbar(actions)
    dialog.protocol("WM_DELETE_WINDOW", close)
    dialog.bind("<Escape>", lambda _event: close())
    refresh()
