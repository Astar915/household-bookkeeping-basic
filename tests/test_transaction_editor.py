from __future__ import annotations

import tempfile
import tkinter as tk
from pathlib import Path
from tkinter import ttk
import unittest
from unittest.mock import Mock, patch

from bookkeeping.desktop_theme import configure_styles
from bookkeeping.gui import BookkeepingWindow
from bookkeeping.localization import install_tk_localization, set_language, translate
from bookkeeping.storage import Database


def descendants(widget):
    for child in widget.winfo_children():
        yield child
        yield from descendants(child)


class TransactionEditorTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        try:
            self.root = tk.Tk()
        except tk.TclError as exc:
            self.skipTest(f"Tk display unavailable: {exc}")
        self.addCleanup(self.root.destroy)
        self.addCleanup(set_language, "zh-CN")
        self.root.geometry("300x80")
        self.callback_errors = []
        self.root.report_callback_exception = lambda *error: self.callback_errors.append(error)
        self.info = self.enterContext(patch("bookkeeping.gui.messagebox.showinfo"))
        self.error = self.enterContext(patch("bookkeeping.gui.messagebox.showerror"))
        self.enterContext(patch("bookkeeping.gui._today_japan", return_value="2026-10-26"))
        self.database_path = Path(self.folder.name) / "ledger.sqlite3"
        self.window = object.__new__(BookkeepingWindow)
        self.window.root = self.root
        self.window.database_path = self.database_path
        self.window.busy = False
        self.window._queue_github_auto_sync = Mock()

    def open_editor(self, kind="expense", language="zh-CN"):
        self.window.language = language
        install_tk_localization(self.root, language)
        configure_styles(self.root, "Microsoft YaHei UI")
        database = Database(self.database_path)
        try:
            database.initialize()
            database.add_account(name="Test bank", account_type="bank", currency="JPY",
                                 opening_balance="5000", opening_date="2026-10-01")
            database.add_account(name="Test wallet", account_type="wallet", currency="JPY",
                                 opening_balance="1000", opening_date="2026-10-01")
            category_name = "自定义测试类别"
            category_id = database.add_category(category_name, "income" if kind == "income" else "expense")
            self.category_label = {"zh-CN": category_name, "ja-JP": "利用者の分類A",
                                   "en-US": "User category A"}[language]
            database.set_category_translation(category_id, language, self.category_label)
            self.transaction_id = database.add_transaction(
                occurred_on="2026-10-26", kind=kind, amount="825", currency="JPY",
                description="Synthetic editor entry", account_name="Test bank",
                category_name=None if kind == "transfer" else category_name,
                to_account_name="Test wallet" if kind == "transfer" else None,
            )
        finally:
            database.close()
        self.window.open_transaction_history()
        self.root.update()
        history = next(child for child in self.root.winfo_children() if isinstance(child, tk.Toplevel))
        tree = next(child for child in descendants(history) if isinstance(child, ttk.Treeview))
        tree.selection_set(str(self.transaction_id))
        self.root.update()
        edit = next(child for child in descendants(history)
                    if isinstance(child, ttk.Button)
                    and child.cget("text") == translate("编辑选中分录", language))
        edit.invoke()
        self.root.update()
        editor = next(child for child in history.winfo_children() if isinstance(child, tk.Toplevel))
        return editor

    def test_expense_editor_prefills_category_and_saves_from_visible_button(self):
        self.check_editor("expense", "zh-CN")

    def test_income_editor_in_japanese_saves_from_visible_button(self):
        self.check_editor("income", "ja-JP")

    def test_transfer_editor_in_english_saves_from_visible_button(self):
        self.check_editor("transfer", "en-US")

    def check_editor(self, kind, language):
        editor = self.open_editor(kind, language)
        self.assertEqual(self.callback_errors, [])
        confirm = next(child for child in descendants(editor)
                       if isinstance(child, ttk.Button)
                       and child.cget("text") == translate("确认修改", language))
        editor.geometry("570x460")
        self.root.update()
        self.assertTrue(confirm.winfo_ismapped())
        self.assertGreaterEqual(confirm.winfo_rooty(), editor.winfo_rooty())
        self.assertLessEqual(confirm.winfo_rooty() + confirm.winfo_height(),
                             editor.winfo_rooty() + editor.winfo_height())
        form = next(child for child in editor.winfo_children()
                    if child.grid_info().get("row") == 0)
        if kind != "transfer":
            category = next(child for child in form.winfo_children()
                            if isinstance(child, ttk.Combobox)
                            and child.grid_info().get("row") == 4
                            and child.grid_info().get("column") == 3)
            self.assertEqual(category.get(), self.category_label)
        for row in ([3, 5] if kind == "transfer" else [3]):
            amount = next(child for child in form.winfo_children()
                          if isinstance(child, ttk.Entry)
                          and not isinstance(child, ttk.Combobox)
                          and child.grid_info().get("row") == row
                          and child.grid_info().get("column") == 3)
            amount.delete(0, "end")
            amount.insert(0, "900")
        confirm.invoke()
        self.root.update()
        self.assertEqual(self.callback_errors, [])
        self.error.assert_not_called()
        self.assertFalse(editor.winfo_exists())
        database = Database(self.database_path)
        try:
            row = database.connection.execute("SELECT * FROM transactions WHERE id=?",
                                              (self.transaction_id,)).fetchone()
            self.assertEqual(row["amount_minor"], 900)
            self.assertEqual(row["kind"], kind)
            self.assertEqual(database.connection.execute("SELECT count(*) FROM transactions").fetchone()[0], 1)
            errors, _ = database.validate()
            self.assertEqual(errors, [])
        finally:
            database.close()
        self.assertEqual(len(list((Path(self.folder.name) / "backups").glob("*.sqlite3"))), 1)
        self.window._queue_github_auto_sync.assert_called_once()


if __name__ == "__main__":
    unittest.main()
