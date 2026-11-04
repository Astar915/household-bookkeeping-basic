from __future__ import annotations

from .desktop_theme import color, fit_management_text, wrap_management_toolbar

import re
import sqlite3
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Any

from .food_categories import (
    FOOD_GROUP_LABELS,
    FOOD_GROUP_TO_CLASSIFICATION,
    FOOD_GROUPS,
    classify_food_name,
    is_confirmed_food_name,
)
from .food_review import PURCHASES_AS_EATEN_SETTING
from .natural_language import _today_japan
from .storage import Database, LedgerError, minor_to_text, parse_date
from .ui_confirm import confirm_delete_once
from .ui_fonts import choose_ui_font_family
from .localization import translate


GROUP_KEYS_BY_LABEL = {label: group for group, label in FOOD_GROUP_LABELS.items()}
FILTER_GROUPS_BY_LABEL = {
    label: group
    for group, label in FOOD_GROUP_LABELS.items()
    if group not in {"other", "unclassified"}
}
SOURCE_LABELS = {
    "receipt": "小票识别",
    "parsed": "文字解析",
    "manual": "手工记录",
    "imported": "历史小票导入",
}


def _effective_purchase_group(row: Any) -> str:
    """Re-read legacy auto-pending rows using current local name rules, without writing data."""
    group = str(row["food_group"])
    if (
        group == "unclassified"
        and str(row["classification"]) == "unclassified"
        and str(row["source"]) in {"receipt", "parsed", "imported"}
    ):
        return classify_food_name(str(row["item_name"]))
    return group


def _effective_purchase_classification(row: Any, group: str) -> str:
    classification = str(row["classification"])
    if (
        str(row["food_group"]) == "unclassified"
        and classification == "unclassified"
        and str(row["source"]) in {"receipt", "parsed", "imported"}
    ):
        return FOOD_GROUP_TO_CLASSIFICATION[group]
    return classification


def _confirmed_food_items_from_receipt(description: str) -> list[str]:
    match = re.match(r"^收据商品[:：]\s*(.+)$", description)
    if not match:
        return []
    return [
        value.strip()[:200]
        for value in re.split(r"[、,，;；\n]+", match.group(1))
        if value.strip() and is_confirmed_food_name(value.strip())
    ][:100]


def _read_items(text: str) -> list[tuple[str, str]]:
    result: list[tuple[str, str]] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if "|" in line:
            name, quantity = line.split("|", 1)
        else:
            name, quantity = line, ""
        if not name.strip():
            raise LedgerError("每行商品名称不能为空；数量可写在竖线后面")
        result.append((name.strip(), quantity.strip()))
    return result


def open_food_tracking(root: tk.Misc, database_path: Path) -> None:
    ui_font_family = choose_ui_font_family(root)
    database = Database(database_path)
    try:
        database.initialize()
    except (LedgerError, sqlite3.Error) as exc:
        database.close()
        messagebox.showerror("无法打开食材记录", str(exc), parent=root)
        return

    dialog = tk.Toplevel(root)
    dialog.title("食材与饮食记录")
    dialog.geometry("1040x660")
    dialog.minsize(880, 540)
    dialog.transient(root)
    dialog.configure(bg=color("#f3f5f8"))

    panel = ttk.Frame(dialog, style="App.TFrame", padding=12)
    panel.pack(fill="both", expand=True)
    fit_management_text(panel)
    panel.columnconfigure(0, weight=1)
    panel.rowconfigure(4, weight=1)

    ttk.Label(panel, text="食材与饮食记录", style="ManagementTitle.TLabel").grid(
        row=0, column=0, sticky="w"
    )
    ttk.Label(
        panel,
        text=(
            "记录购买的食材和食品，按本地规则自动归类为肉蛋奶、蔬菜水果、"
            "主食粮食、零食点心等；名称不明确时保留为待识别，你可以手动修改。数量按原文保存，"
            "不会自动估算库存。饮食回顾可按你的偏好把已购食品视为已吃，不需要单独登记食用记录。"
        ),
        style="Hint.TLabel",
        wraplength=950,
    ).grid(row=1, column=0, sticky="ew", pady=(4, 8))

    count_purchases_var = tk.BooleanVar(
        value=database.get_setting(PURCHASES_AS_EATEN_SETTING, "0") == "1"
    )
    count_purchases_option = ttk.Checkbutton(
        panel,
        text="饮食回顾把已购食品按已吃计入（其他商品不计；待识别项不参与营养分类）",
        variable=count_purchases_var,
        command=lambda: save_food_review_preference(),
    )
    count_purchases_option.grid(row=2, column=0, sticky="w", pady=(0, 8))

    actions = ttk.Frame(panel, style="App.TFrame")
    actions.grid(row=3, column=0, sticky="ew", pady=(0, 10))

    notebook = ttk.Notebook(panel)
    notebook.grid(row=4, column=0, sticky="nsew")
    purchase_page = ttk.Frame(notebook, padding=10)
    consumption_page = ttk.Frame(notebook, padding=10)
    purchase_page.columnconfigure(0, weight=1)
    purchase_page.rowconfigure(1, weight=1)
    consumption_page.columnconfigure(0, weight=1)
    consumption_page.rowconfigure(0, weight=1)
    notebook.add(purchase_page, text="采购记录")

    purchase_toolbar = ttk.Frame(purchase_page, style="App.TFrame")
    purchase_toolbar.grid(row=0, column=0, sticky="ew", pady=(0, 8))
    ttk.Label(purchase_toolbar, text="显示：", style="Hint.TLabel").pack(side="left")
    filter_var = tk.StringVar(value="食材")
    filter_box = ttk.Combobox(
        purchase_toolbar,
        textvariable=filter_var,
        values=(
            "全部商品", "待识别", "食材", "其他商品",
            *(FOOD_GROUP_LABELS[group] for group in FOOD_GROUPS
              if group not in {"other", "unclassified"}),
        ),
        state="readonly",
        width=14,
    )
    filter_box.pack(side="left")

    purchase_tree = ttk.Treeview(
        purchase_page,
        columns=("date", "item", "quantity", "classification", "source", "ledger"),
        show="headings",
        selectmode="browse",
    )
    for key, title, width, anchor in (
        ("date", "日期", 100, "w"),
        ("item", "商品/食材", 390, "w"),
        ("quantity", "数量", 120, "w"),
        ("classification", "分类", 125, "center"),
        ("source", "来源", 115, "center"),
        ("ledger", "账本流水", 100, "center"),
    ):
        purchase_tree.heading(key, text=title)
        purchase_tree.column(key, width=width, minwidth=70, anchor=anchor, stretch=key == "item")
    purchase_tree.grid(row=1, column=0, sticky="nsew")
    purchase_scrollbar = ttk.Scrollbar(
        purchase_page, orient="vertical", command=purchase_tree.yview
    )
    purchase_scrollbar.grid(row=1, column=1, sticky="ns")
    purchase_tree.configure(yscrollcommand=purchase_scrollbar.set)

    purchase_controls = ttk.Frame(purchase_page, style="App.TFrame")
    purchase_controls.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(9, 0))

    consumption_tree = ttk.Treeview(
        consumption_page,
        columns=("date", "meal", "item", "quantity", "note"),
        show="headings",
        selectmode="browse",
    )
    for key, title, width, anchor in (
        ("date", "日期", 105, "w"),
        ("meal", "餐次", 105, "center"),
        ("item", "吃了什么", 310, "w"),
        ("quantity", "数量", 120, "w"),
        ("note", "备注", 270, "w"),
    ):
        consumption_tree.heading(key, text=title)
        consumption_tree.column(key, width=width, minwidth=70, anchor=anchor, stretch=key in {"item", "note"})
    consumption_tree.grid(row=0, column=0, sticky="nsew")
    consumption_scrollbar = ttk.Scrollbar(
        consumption_page, orient="vertical", command=consumption_tree.yview
    )
    consumption_scrollbar.grid(row=0, column=1, sticky="ns")
    consumption_tree.configure(yscrollcommand=consumption_scrollbar.set)
    consumption_controls = ttk.Frame(consumption_page, style="App.TFrame")
    consumption_controls.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(9, 0))

    status_var = tk.StringVar(value="")
    ttk.Label(panel, textvariable=status_var, style="Hint.TLabel").grid(
        row=5, column=0, sticky="ew", pady=(8, 0)
    )
    footer = ttk.Frame(panel, style="App.TFrame")
    footer.grid(row=6, column=0, sticky="ew", pady=(12, 0))
    ttk.Button(footer, text="刷新", command=lambda: refresh()).pack(side="left")
    ttk.Button(footer, text="关闭", command=dialog.destroy).pack(side="right")

    def refresh() -> None:
        purchase_tree.delete(*purchase_tree.get_children())
        selected_filter = filter_var.get()
        query = """SELECT id,purchase_date,item_name,quantity_text,classification,food_group,source,transaction_id
                   FROM food_purchase_items"""
        query += " ORDER BY purchase_date DESC,id DESC"
        all_purchase_rows = database.connection.execute(query).fetchall()
        purchase_rows: list[tuple[Any, str]] = []
        for row in all_purchase_rows:
            group = _effective_purchase_group(row)
            classification = _effective_purchase_classification(row, group)
            if selected_filter == "待识别" and group != "unclassified":
                continue
            if selected_filter in FILTER_GROUPS_BY_LABEL and group != FILTER_GROUPS_BY_LABEL[selected_filter]:
                continue
            if selected_filter in {"食材", "其他商品"}:
                wanted = {"食材": "ingredient", "其他商品": "other"}[selected_filter]
                if classification != wanted:
                    continue
            purchase_rows.append((row, group))
        for row, group in purchase_rows:
            transaction_label = f"#{row['transaction_id']}" if row["transaction_id"] else "—"
            purchase_tree.insert(
                "", "end", iid=str(row["id"]),
                values=(
                    row["purchase_date"], row["item_name"],
                    row["quantity_text"] or ("1" if row["source"] in {"receipt", "parsed", "imported"} else ""),
                    translate(FOOD_GROUP_LABELS[group]),
                    translate(SOURCE_LABELS[row["source"]]), transaction_label,
                ),
            )

        consumption_tree.delete(*consumption_tree.get_children())
        consumption_rows = database.connection.execute(
            """SELECT id,consumed_on,meal,item_name,quantity_text,note
               FROM food_consumption_records ORDER BY consumed_on DESC,id DESC"""
        ).fetchall()
        for row in consumption_rows:
            consumption_tree.insert(
                "", "end", iid=str(row["id"]),
                values=(row["consumed_on"], row["meal"] or "—", row["item_name"],
                        row["quantity_text"], row["note"]),
            )
        unclassified_count = sum(
            1 for _row, group in purchase_rows if group == "unclassified"
        )
        status_var.set(
            f"当前显示 {len(purchase_rows)} 条采购商品。"
            + (f"其中 {unclassified_count} 条待识别。" if unclassified_count else "")
        )

    def save_food_review_preference() -> None:
        enabled = count_purchases_var.get()
        try:
            database.set_setting(
                PURCHASES_AS_EATEN_SETTING,
                "1" if enabled else "0",
                "饮食回顾是否把已购食品按已吃计入；其他商品不计，待识别项不参与营养分类",
            )
        except sqlite3.Error as exc:
            count_purchases_var.set(not enabled)
            messagebox.showerror("保存失败", str(exc), parent=dialog)
            return
        status_var.set(
            "已开启：食品采购计作已吃；其他商品排除，待识别项不参与营养分类。" if enabled
            else "饮食回顾只统计食用记录。"
        )

    def save_manual_entries(*, purchase: bool) -> None:
        entry = tk.Toplevel(dialog)
        entry.title("记录购买食材" if purchase else "记录吃过的食物")
        entry.geometry("560x600")
        entry.minsize(480, 480)
        entry.transient(dialog)
        entry.configure(bg=color("#f3f5f8"))
        form = ttk.Frame(entry, style="App.TFrame", padding=12)
        form.pack(fill="both", expand=True)
        form.columnconfigure(0, weight=1)
        form.rowconfigure(2, weight=1)

        date_var = tk.StringVar(value=_today_japan())
        ttk.Label(form, text="日期（支持202608、8月）", style="Hint.TLabel").grid(
            row=0, column=0, sticky="w"
        )
        ttk.Entry(form, textvariable=date_var).grid(
            row=1, column=0, sticky="ew", pady=(3, 10)
        )

        next_row = 2
        meal_var = tk.StringVar(value="")
        if not purchase:
            ttk.Label(form, text="餐次（可选）", style="Hint.TLabel").grid(
                row=next_row, column=0, sticky="w"
            )
            meal_var.set("")
            meal_box = ttk.Combobox(
                form, textvariable=meal_var,
                values=("", "早餐", "午餐", "晚餐", "加餐", "其他"),
                state="readonly",
            )
            meal_box.grid(row=next_row + 1, column=0, sticky="ew", pady=(3, 10))
            next_row += 2

        ttk.Label(
            form,
            text="每行填写一种" + ("食材" if purchase else "食物") + "；数量可写作“名称 | 数量/单位”。",
            style="Hint.TLabel",
            wraplength=470,
        ).grid(row=next_row, column=0, sticky="w")
        items_box = tk.Text(form, height=12, wrap="word", font=(ui_font_family, 11))
        items_box.grid(row=next_row + 1, column=0, sticky="nsew", pady=(5, 10))
        form.rowconfigure(next_row + 1, weight=1)

        note_var = tk.StringVar(value="")
        if not purchase:
            ttk.Label(form, text="备注（可选）", style="Hint.TLabel").grid(
                row=next_row + 2, column=0, sticky="w"
            )
            ttk.Entry(form, textvariable=note_var).grid(
                row=next_row + 3, column=0, sticky="ew", pady=(3, 10)
            )

        buttons = ttk.Frame(form, style="App.TFrame")
        buttons.grid(row=next_row + 4, column=0, sticky="ew", pady=(10, 0))

        def save() -> None:
            try:
                date_text = parse_date(date_var.get().strip()).isoformat()
                items = _read_items(items_box.get("1.0", "end-1c"))
                if not items:
                    raise LedgerError("请至少填写一行商品")
                if purchase:
                    database.add_food_purchases(date_text, items)
                    status_var.set(f"已保存 {len(items)} 条采购食材记录。")
                else:
                    database.add_food_consumptions(
                        date_text, items, meal=meal_var.get(), note=note_var.get()
                    )
                    status_var.set(f"已保存 {len(items)} 条食用记录。")
            except (LedgerError, sqlite3.Error) as exc:
                messagebox.showerror("保存失败", str(exc), parent=entry)
                return
            entry.destroy()
            refresh()

        ttk.Button(buttons, text="取消", command=entry.destroy).pack(side="right", padx=(8, 0))
        ttk.Button(buttons, text="保存", style="Send.TButton", command=save).pack(side="right")
        entry.bind("<Escape>", lambda _event: entry.destroy())
        entry.grab_set()
        items_box.focus_set()

    def import_existing_receipts() -> None:
        rows = database.connection.execute(
            """SELECT t.id,t.occurred_on,t.amount_minor,t.currency,c.minor_digits,t.description
               FROM transactions t
               JOIN currencies c ON c.code=t.currency
               WHERE t.kind='expense'
                 AND (t.description LIKE '收据商品：%' OR t.description LIKE '收据商品:%')
                 AND NOT EXISTS (
                     SELECT 1 FROM food_purchase_items p WHERE p.transaction_id=t.id
                 )
               ORDER BY t.occurred_on DESC,t.id DESC"""
        ).fetchall()
        rows = [
            row for row in rows
            if _confirmed_food_items_from_receipt(str(row["description"]))
        ]
        if not rows:
            messagebox.showinfo(
                translate("没有可导入的小票"),
                translate("没有找到含有可确认食品、且尚未导入的已记账小票。纯非食品小票和无法确认的商品不会进入食材记录。"),
                parent=dialog,
            )
            return

        picker = tk.Toplevel(dialog)
        picker.title("导入已记账小票商品")
        picker.geometry("780x500")
        picker.minsize(640, 400)
        picker.transient(dialog)
        picker.configure(bg=color("#f3f5f8"))
        box = ttk.Frame(picker, style="App.TFrame", padding=16)
        box.pack(fill="both", expand=True)
        box.columnconfigure(0, weight=1)
        box.rowconfigure(1, weight=1)
        ttk.Label(
            box,
            text=translate("选择收据消费。仅导入名称线索明确的食品商品；非食品、占位词和无法确认的商品不加入食材记录，财务流水不变。"),
            style="Hint.TLabel",
            wraplength=660,
        ).grid(row=0, column=0, sticky="ew", pady=(0, 8))
        receipt_list = tk.Listbox(box, selectmode="extended", font=(ui_font_family, 10))
        receipt_list.grid(row=1, column=0, sticky="nsew")
        receipt_scroll = ttk.Scrollbar(box, orient="vertical", command=receipt_list.yview)
        receipt_scroll.grid(row=1, column=1, sticky="ns")
        receipt_list.configure(yscrollcommand=receipt_scroll.set)
        for row in rows:
            description = str(row["description"])
            summary = re.split(r"[:：]", description, maxsplit=1)[-1]
            amount_label = minor_to_text(
                int(row["amount_minor"]), int(row["minor_digits"]), str(row["currency"])
            )
            receipt_list.insert(
                "end", f"#{row['id']}  {row['occurred_on']}  {amount_label}  {summary}"
            )
        picker_buttons = ttk.Frame(box, style="App.TFrame")
        picker_buttons.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(12, 0))

        def import_selected() -> None:
            selected = receipt_list.curselection()
            if not selected:
                messagebox.showinfo("请选择小票", "请先选择至少一张小票。", parent=picker)
                return
            try:
                inserted = database.import_receipt_purchase_items(
                    [int(rows[index]["id"]) for index in selected]
                )
            except (LedgerError, sqlite3.Error) as exc:
                messagebox.showerror("导入失败", str(exc), parent=picker)
                return
            picker.destroy()
            refresh()
            status_var.set(
                translate("已导入 {count} 条可识别食品商品行；非食品和无法确认的项目不加入食材记录。")
                .format(count=inserted)
            )

        ttk.Button(picker_buttons, text="取消", command=picker.destroy).pack(side="right", padx=(8, 0))
        ttk.Button(picker_buttons, text="导入所选", style="Send.TButton", command=import_selected).pack(side="right")
        picker.grab_set()

    def edit_purchase() -> None:
        selection = purchase_tree.selection()
        if not selection:
            messagebox.showinfo("请选择商品", "请先选择一条采购商品记录。", parent=dialog)
            return
        item_id = int(selection[0])
        try:
            row = database.connection.execute(
                "SELECT item_name,quantity_text,source,classification,food_group FROM food_purchase_items WHERE id=?",
                (item_id,),
            ).fetchone()
        except sqlite3.Error as exc:
            messagebox.showerror("读取失败", str(exc), parent=dialog)
            return
        if row is None:
            refresh()
            return
        initial_group = _effective_purchase_group(row)
        editor = tk.Toplevel(dialog)
        editor.title("编辑采购商品")
        editor.geometry("520x390")
        editor.minsize(480, 360)
        editor.transient(dialog)
        editor.configure(bg=color("#f3f5f8"))
        form = ttk.Frame(editor, style="App.TFrame", padding=12)
        form.pack(fill="both", expand=True)
        form.columnconfigure(0, weight=1)
        ttk.Label(form, text="编辑采购商品", style="ManagementTitle.TLabel").grid(
            row=0, column=0, sticky="w", pady=(0, 10)
        )
        name_var = tk.StringVar(value=row["item_name"])
        quantity_var = tk.StringVar(
            value=row["quantity_text"]
            or ("1" if row["source"] in {"receipt", "parsed", "imported"} else "")
        )
        group_var = tk.StringVar(value=FOOD_GROUP_LABELS[initial_group])
        ttk.Label(form, text="商品/食材名称", style="Hint.TLabel").grid(row=1, column=0, sticky="w")
        ttk.Entry(form, textvariable=name_var).grid(row=2, column=0, sticky="ew", pady=(3, 10))
        ttk.Label(form, text="数量/单位（可选）", style="Hint.TLabel").grid(row=3, column=0, sticky="w")
        ttk.Entry(form, textvariable=quantity_var).grid(row=4, column=0, sticky="ew", pady=(3, 10))
        ttk.Label(form, text="食品分类", style="Hint.TLabel").grid(row=5, column=0, sticky="w")
        group_box = ttk.Combobox(
            form,
            textvariable=group_var,
            values=tuple(FOOD_GROUP_LABELS[group] for group in FOOD_GROUPS),
            state="readonly",
        )
        group_box.grid(row=6, column=0, sticky="ew", pady=(3, 6))
        category_actions = ttk.Frame(form, style="App.TFrame")
        category_actions.grid(row=7, column=0, sticky="ew", pady=(0, 5))
        category_status_var = tk.StringVar(value="")
        ttk.Label(
            form,
            textvariable=category_status_var,
            style="Hint.TLabel",
            wraplength=460,
        ).grid(row=8, column=0, sticky="w", pady=(0, 10))

        def apply_editor_category() -> None:
            try:
                database.set_food_purchase_group(item_id, GROUP_KEYS_BY_LABEL[group_var.get()])
            except (KeyError, LedgerError, sqlite3.Error) as exc:
                messagebox.showerror("更新失败", str(exc), parent=editor)
                return
            refresh()
            if purchase_tree.exists(str(item_id)):
                purchase_tree.selection_set(str(item_id))
                purchase_tree.focus(str(item_id))
            category_status_var.set("分类已应用；名称和数量请点保存后生效。")

        def reclassify_editor_item() -> None:
            group = classify_food_name(name_var.get())
            group_var.set(FOOD_GROUP_LABELS[group])
            category_status_var.set(
                f"自动分类结果：{translate(FOOD_GROUP_LABELS[group])}；点击保存后生效。"
            )

        ttk.Button(category_actions, text="应用分类", command=apply_editor_category).pack(
            side="left", padx=(0, 8)
        )
        ttk.Button(category_actions, text="重新自动分类", command=reclassify_editor_item).pack(
            side="left"
        )
        buttons = ttk.Frame(form, style="App.TFrame")
        buttons.grid(row=9, column=0, sticky="ew")

        def save_edit() -> None:
            try:
                database.update_food_purchase_item(
                    item_id,
                    name_var.get(),
                    quantity_var.get(),
                    food_group=GROUP_KEYS_BY_LABEL[group_var.get()],
                )
            except (KeyError, LedgerError, sqlite3.Error) as exc:
                messagebox.showerror("保存失败", str(exc), parent=editor)
                return
            editor.destroy()
            refresh()

        ttk.Button(buttons, text="取消", command=editor.destroy).pack(side="right", padx=(8, 0))
        ttk.Button(buttons, text="保存", style="Send.TButton", command=save_edit).pack(side="right")
        editor.grab_set()

    def remove_purchase() -> None:
        selection = purchase_tree.selection()
        if not selection:
            messagebox.showinfo("请选择记录", "请先选择一条采购商品记录。", parent=dialog)
            return
        purchase = purchase_tree.item(selection[0], "values")
        item_name = str(purchase[1]) if len(purchase) > 1 else "选中的采购商品"
        purchase_date = str(purchase[0]) if purchase else "日期未知"
        if not confirm_delete_once(
            dialog,
            title="移除采购商品记录",
            target=f"{purchase_date} 的“{item_name}”",
            impact="只移除此商品记录，不会删除对应的财务流水。",
        ):
            return
        try:
            database.delete_food_purchase_item(int(selection[0]))
        except (LedgerError, sqlite3.Error) as exc:
            messagebox.showerror("移除失败", str(exc), parent=dialog)
            return
        refresh()

    def remove_consumption() -> None:
        selection = consumption_tree.selection()
        if not selection:
            messagebox.showinfo("请选择记录", "请先选择一条食用记录。", parent=dialog)
            return
        consumption = consumption_tree.item(selection[0], "values")
        consumed_on = str(consumption[0]) if consumption else "日期未知"
        item_name = str(consumption[2]) if len(consumption) > 2 else "选中的食用记录"
        if not confirm_delete_once(
            dialog,
            title="删除食用记录",
            target=f"{consumed_on} 的“{item_name}”",
            impact="这条饮食记录将从本地账本数据库中永久删除。",
        ):
            return
        try:
            database.delete_food_consumption(int(selection[0]))
        except (LedgerError, sqlite3.Error) as exc:
            messagebox.showerror("删除失败", str(exc), parent=dialog)
            return
        refresh()

    ttk.Button(
        actions, text="＋ 记录采购食材", style="Settings.TButton",
        command=lambda: save_manual_entries(purchase=True),
    ).pack(side="left", padx=(0, 8))
    ttk.Button(
        actions, text="从已记账小票导入商品", style="Settings.TButton",
        command=import_existing_receipts,
    ).pack(side="left")
    ttk.Button(purchase_controls, text="编辑商品/数量", command=edit_purchase).pack(side="left", padx=(0, 7))
    ttk.Button(purchase_controls, text="移除此商品行", command=remove_purchase).pack(side="left")
    ttk.Button(consumption_controls, text="删除选中食用记录", command=remove_consumption).pack(side="left")

    filter_box.bind("<<ComboboxSelected>>", lambda _event: refresh())
    wrap_management_toolbar(actions)
    dialog.protocol("WM_DELETE_WINDOW", lambda: (database.close(), dialog.destroy()))
    dialog.bind("<Escape>", lambda _event: (database.close(), dialog.destroy()))
    refresh()
    dialog.grab_set()
