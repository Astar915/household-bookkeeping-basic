"""Native desktop workspace with a persistent navigation rail and financial overview.

This presentation layer reads existing financial services. Mutating actions go
through the existing, confirmed desktop workflows; it never imports a web ledger.
"""
from __future__ import annotations

import math
import queue
import re
import threading
from pathlib import Path
import tkinter as tk
from tkinter import messagebox, ttk

from .credit_management import credit_card_overview
from .desktop_theme import PALETTE, RoundedPanel
from .desktop_frame import (
    DesktopFrame, DesktopPanedWindow, ResizeRenderCoordinator, WindowResizeMessageHook, center_window,
    defer_during_interactive_resize,
)
from .desktop_layout import (
    DesktopLayoutStore, MIN_SIDEBAR_WIDTH, MAX_SIDEBAR_WIDTH,
    MIN_CONTENT_WIDTH, SASH_WIDTH,
)
from .desktop_tooltip import Tooltip
from .desktop_favorites import DesktopFavoriteStore
from .financial_statements import build_balance_sheet, build_profit_statement
from .localization import translate
from .natural_language import _today_japan
from .storage import Database, minor_to_text


def read_overview(path):
    database = Database(path)
    try:
        database.connection.execute("PRAGMA query_only=ON")
        database.connection.execute("BEGIN")
        today = _today_japan()
        balance = build_balance_sheet(database, today)
        profit = build_profit_statement(database, today)
        settings = dict(database.connection.execute("SELECT key,value FROM settings"))
        transactions = [dict(row) for row in database.connection.execute(
            """SELECT t.*, c.name category_name,a.name account_name,b.name to_account_name,
                      currency.minor_digits currency_minor_digits
               FROM transactions t LEFT JOIN categories c ON c.id=t.category_id
               LEFT JOIN accounts a ON a.id=t.account_id
               LEFT JOIN accounts b ON b.id=t.to_account_id
               JOIN currencies currency ON currency.code=t.currency
               ORDER BY t.occurred_on DESC,t.id DESC LIMIT 2000"""
        )]
        cards = credit_card_overview(database, as_of=today)
        return {"balance": balance, "profit": profit, "settings": settings,
                "transactions": transactions, "cards": cards}
    finally:
        database.close()


class RoundedProgressBar(tk.Canvas):
    """Small rounded progress track matching the mobile overview bars."""
    def __init__(self, master, value, *, height, track, gradient=False, fill=None):
        super().__init__(master, height=height + 4, bg=PALETTE["surface"],
                         highlightthickness=0, bd=0)
        self.value = max(0.0, min(1.0, float(value)))
        self.bar_height = height
        self.track_color = track
        self.gradient = gradient
        self.fill_color = fill or "#7da7e0"
        self._bar_image = None
        self._draw_pending = None
        self.bind("<Configure>", self._redraw)
        self.after_idle(self._draw)

    def _redraw(self, _event=None):
        if defer_during_interactive_resize(self, self, self._draw):
            if self._draw_pending is not None:
                self.after_cancel(self._draw_pending)
                self._draw_pending = None
            return
        if self._draw_pending is not None:
            self.after_cancel(self._draw_pending)
        self._draw_pending = self.after(36, self._draw)

    def _pill(self, left, right, top, height, color):
        width = right - left
        if width <= 0:
            return
        radius = min(height / 2, width / 2)
        if width > 2 * radius:
            self.create_rectangle(left + radius, top, right - radius, top + height,
                                  fill=color, outline="")
        self.create_oval(left, top, left + 2 * radius, top + height,
                         fill=color, outline="")
        if width > 2 * radius:
            self.create_oval(right - 2 * radius, top, right, top + height,
                             fill=color, outline="")

    @staticmethod
    def _mix(start, end, ratio):
        a = tuple(int(start[index:index + 2], 16) for index in (1, 3, 5))
        b = tuple(int(end[index:index + 2], 16) for index in (1, 3, 5))
        return "#" + "".join(f"{round(x + (y - x) * ratio):02x}" for x, y in zip(a, b))

    def _draw(self):
        self._draw_pending = None
        if not self.winfo_exists():
            return
        if defer_during_interactive_resize(self, self, self._draw):
            return
        self.delete("all")
        width = self.winfo_width()
        canvas_height = self.winfo_height()
        if width < 2 or canvas_height < 2:
            return
        try:
            from PIL import ImageTk
        except ImportError:
            self._draw_canvas_fallback(width, canvas_height)
            return

        rendered = self._render_image(
            width, canvas_height, self.bar_height, self.value,
            self.track_color, self.gradient, self.fill_color,
        )
        self._bar_image = ImageTk.PhotoImage(rendered, master=self)
        self.create_image(0, 0, image=self._bar_image, anchor="nw")

    @staticmethod
    def _render_image(width, canvas_height, bar_height, value, track_color, use_gradient, fill_color):
        from PIL import Image, ImageDraw

        # Tk's native ovals and narrow gradient strips leave visible steps at
        # this 7–8 px height. Draw at 4x resolution, then downsample once.
        scale = 4
        pixel_width, pixel_height = width * scale, canvas_height * scale
        scaled_bar_height = min(bar_height, canvas_height) * scale
        top = ((canvas_height - min(bar_height, canvas_height)) // 2) * scale
        radius = scaled_bar_height // 2
        rendered = Image.new("RGBA", (pixel_width, pixel_height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(rendered)
        draw.rounded_rectangle(
            (0, top, pixel_width - 1, top + scaled_bar_height - 1),
            radius=radius, fill=track_color,
        )

        filled_width = round(pixel_width * value)
        if filled_width > 0:
            fill_radius = min(radius, filled_width // 2)
            bounds = (0, top, filled_width - 1, top + scaled_bar_height - 1)
            if use_gradient:
                fill_mask = Image.new("L", (pixel_width, pixel_height), 0)
                ImageDraw.Draw(fill_mask).rounded_rectangle(
                    bounds, radius=fill_radius, fill=255,
                )
                start = (0x65, 0xB4, 0xF9)
                end = (0x00, 0x7A, 0xFF)
                row = Image.new("RGB", (filled_width, 1))
                row.putdata([
                    tuple(round(a + (b - a) * x / max(1, filled_width - 1))
                          for a, b in zip(start, end))
                    for x in range(filled_width)
                ])
                gradient_image = row.resize(
                    (filled_width, scaled_bar_height), Image.Resampling.BILINEAR,
                )
                overlay = Image.new("RGBA", (pixel_width, pixel_height), (0, 0, 0, 0))
                overlay.paste(gradient_image, (0, top))
                rendered = Image.composite(overlay, rendered, fill_mask)
            else:
                ImageDraw.Draw(rendered).rounded_rectangle(
                    bounds, radius=fill_radius, fill=fill_color,
                )

        return rendered.resize((width, canvas_height), Image.Resampling.LANCZOS)

    def _draw_canvas_fallback(self, width, canvas_height):
        """Keep the progress bar usable if Pillow is unavailable at runtime."""
        height = self.bar_height
        top = (canvas_height - height) / 2
        self._pill(0, width, top, height, self.track_color)
        filled = width * self.value
        if filled <= 0:
            return
        if not self.gradient:
            self._pill(0, filled, top, height, self.fill_color)
            return
        radius = min(height / 2, filled / 2)
        if filled > 2 * radius:
            inner_left, inner_right = radius, filled - radius
            strips = max(1, min(64, int(inner_right - inner_left)))
            for index in range(strips):
                x1 = inner_left + (inner_right - inner_left) * index / strips
                x2 = inner_left + (inner_right - inner_left) * (index + 1) / strips + 1
                ratio = (x1 + x2) / (2 * max(1, filled))
                self.create_rectangle(x1, top, x2, top + height,
                                      fill=self._mix("#65b4f9", "#007aff", ratio), outline="")
        self.create_oval(0, top, 2 * radius, top + height, fill="#65b4f9", outline="")
        if filled > 2 * radius:
            self.create_oval(filled - 2 * radius, top, filled, top + height,
                             fill="#007aff", outline="")


class GradientHero(tk.Canvas):
    """Resolution independent gradient hero; works without optional Pillow."""
    def __init__(self, master, shell):
        super().__init__(master, height=176, bg=PALETTE["background"], highlightthickness=0, bd=0)
        self.shell = shell
        self._appearance_fixed_artwork = True
        self.pending = None
        self._hero_image = None
        self._hero_image_key = None
        self._toggle_image = None
        self._toggle_image_key = None
        self.record = ttk.Button(self, text="＋  记一笔", style="HeroPrimary.TButton",
                                 command=lambda: shell.navigate("entry"))
        self.accounts = ttk.Button(self, text="查看账户", style="HeroSecondary.TButton",
                                   command=lambda: shell.navigate("assets"))
        self.tag_bind("hero-mode-toggle", "<Button-1>", self.toggle_profit_mode)
        self.tag_bind("hero-mode-toggle", "<Enter>", lambda _event: self.configure(cursor="hand2"))
        self.tag_bind("hero-mode-toggle", "<Leave>", lambda _event: self.configure(cursor=""))
        self.bind("<Configure>", self.schedule)

    def toggle_profit_mode(self, _event=None):
        self.shell.hero_profit_mode = not self.shell.hero_profit_mode
        self.draw()
        return "break"

    def schedule(self, _event=None):
        if self.pending:
            self.after_cancel(self.pending)
        self.pending = None
        if defer_during_interactive_resize(self, self, self.draw):
            return
        self.pending = self.after(24, self.draw)

    def draw(self):
        self.pending = None
        if not self.winfo_exists():
            return
        if defer_during_interactive_resize(self, self, self.draw):
            return
        self.delete("all")
        w, h = self.winfo_width(), self.winfo_height()
        if w < 10:
            return
        self.configure(bg=PALETTE["background"])
        self._draw_gradient_background(w, h)
        data = self.shell.snapshot
        show_profit = self.shell.hero_profit_mode
        if show_profit:
            profit = data["profit"] if data else None
            jpy_summary = profit["currencies"].get("JPY", {}) if profit else {}
            amount = jpy_summary.get("net_minor") if profit else None
            cny_summary = profit["currencies"].get("CNY", {}) if profit else {}
            cny_amount = cny_summary.get("net_minor") if profit else None
            cny_jpy_amount = cny_summary.get("jpy_equivalent_net_minor") if profit else None
            cny_missing_rates = int(cny_summary.get("missing_jpy_conversion_count", 0)) if profit else 0
            title = translate("当期纯利润 · JPY", self.shell.locale)
            subtitle = translate("人民币净利润", self.shell.locale) + " · " + self.shell.money(
                cny_amount, "CNY", mask_key="period-profit-cny"
            )
            if cny_missing_rates:
                subtitle += "（" + translate("汇率不全", self.shell.locale) + "）"
            else:
                subtitle += "（≈ " + self.shell.money(
                    cny_jpy_amount, "JPY", mask_key="period-profit-cny-jpy"
                ) + "）"
            amount_mask_key = "period-profit-jpy"
        else:
            balance = data["balance"] if data else None
            amount = None if balance is None else balance["net_assets"].get("JPY", 0)
            cny_amount = None if balance is None else balance["net_assets"].get("CNY", 0)
            title = translate("总净资产 · JPY", self.shell.locale)
            subtitle = translate("人民币资产独立核算", self.shell.locale) + " · " + self.shell.money(
                cny_amount, "CNY", mask_key="cny-assets"
            )
            amount_mask_key = "net-assets"
        self.create_text(24, 20, anchor="nw", text=title,
                         fill="#c0cbdf", font=(self.shell.family, 11))
        self.create_text(24, 49, anchor="nw", text=self.shell.money(amount, mask_key=amount_mask_key),
                         fill="#ffffff", font=("Consolas", 20) if self.shell.hidden else
                         (self.shell.family, 29 if w > 650 else 25, "bold"))
        self.create_text(25, 105, anchor="nw", text=subtitle,
                         fill="#b9c8df", font=(self.shell.family, 10))
        self.create_text(w-24, 20, anchor="ne", text=translate("我的账本", self.shell.locale),
                         fill="#c0cbdf", font=(self.shell.family, 11))
        toggle_x, toggle_y = 38, h-24
        start,end=((30,50,76),(61,65,98)) if PALETTE["background"]=="#11131b" else ((24,46,80),(62,76,119))
        blend = toggle_x / max(1, w)
        toggle_fill = "#%02x%02x%02x" % tuple(
            round(a+(b-a)*blend) for a,b in zip(start,end)
        )
        self._draw_mode_toggle(toggle_x, toggle_y, toggle_fill)
        # Canvas children cannot inherit the painted gradient. Match each native
        # button's transparent corners to the gradient at its own center.
        start,end=((30,50,76),(61,65,98)) if PALETTE["background"]=="#11131b" else ((24,46,80),(62,76,119))
        for button, base, center in (
            (self.accounts, "HeroSecondary.TButton", w-24-self.accounts.winfo_reqwidth()/2),
            (self.record, "HeroPrimary.TButton", w-36-self.accounts.winfo_reqwidth()-self.record.winfo_reqwidth()/2),
        ):
            ratio=max(0,min(1,center/max(1,w)))
            backing="#%02x%02x%02x" % tuple(round(a+(b-a)*ratio) for a,b in zip(start,end))
            style_name="HeroBlend"+backing[1:]+"."+base
            style=ttk.Style(self)
            style.configure(style_name, background=backing)
            style.map(style_name, background=[("!disabled",backing),("disabled",backing)])
            button.configure(style=style_name)
        self.create_window(w-24, h-20, anchor="se", window=self.accounts)
        self.create_window(w-36-self.accounts.winfo_reqwidth(), h-20, anchor="se", window=self.record)

    def _draw_gradient_background(self, width, height):
        """Supersample the card gradient and rounded edge to remove Canvas stair steps."""
        try:
            from PIL import Image, ImageDraw, ImageTk
        except ImportError:
            start,end=((30,50,76),(61,65,98)) if PALETTE["background"]=="#11131b" else ((24,46,80),(62,76,119))
            for x in range(0, width, 2):
                ratio = x / max(1, width-1)
                rgb = tuple(round(a+(b-a)*ratio) for a,b in zip(start,end))
                self.create_rectangle(x, 0, x+2, height, fill="#%02x%02x%02x" % rgb, outline="")
            self.create_arc(0, 0, 28, 28, start=90, extent=90, outline=PALETTE["background"], width=14)
            self.create_arc(width-28, 0, width, 28, start=0, extent=90, outline=PALETTE["background"], width=14)
            self.create_arc(width-28, height-28, width, height, start=270, extent=90, outline=PALETTE["background"], width=14)
            self.create_arc(0, height-28, 28, height, start=180, extent=90, outline=PALETTE["background"], width=14)
            return

        key = (width, height, PALETTE["background"])
        if self._hero_image_key != key:
            scale = 4
            pixel_width, pixel_height = width*scale, height*scale
            start,end=((30,50,76),(61,65,98)) if PALETTE["background"]=="#11131b" else ((24,46,80),(62,76,119))
            gradient = Image.new("RGB", (pixel_width, 1))
            gradient.putdata([
                tuple(round(a+(b-a)*x/max(1,pixel_width-1)) for a,b in zip(start,end))
                for x in range(pixel_width)
            ])
            bitmap = gradient.resize((pixel_width, pixel_height), Image.Resampling.BILINEAR).convert("RGBA")
            mask = Image.new("L", (pixel_width, pixel_height), 0)
            ImageDraw.Draw(mask).rounded_rectangle(
                (0, 0, pixel_width-1, pixel_height-1), radius=14*scale, fill=255
            )
            bitmap.putalpha(mask)
            bitmap = bitmap.resize((width, height), Image.Resampling.LANCZOS)
            self._hero_image = ImageTk.PhotoImage(bitmap, master=self)
            self._hero_image_key = key
        self.create_image(0, 0, anchor="nw", image=self._hero_image, tags=("hero-background",))
        self.tag_lower("hero-background")

    def _draw_mode_toggle(self, center_x, center_y, background):
        try:
            from PIL import Image, ImageDraw, ImageTk
        except ImportError:
            tags = ("hero-mode-toggle",)
            radius = 13
            self.create_oval(center_x-radius, center_y-radius, center_x+radius, center_y+radius,
                             fill=background, outline="#91a9cf", width=1, tags=tags)
            self.create_arc(center_x-7, center_y-7, center_x+7, center_y+7,
                            start=45, extent=285, style="arc", outline="#e0e9f7", width=2, tags=tags)
            return

        key = (background, "light", 28)
        if self._toggle_image_key != key:
            scale, size = 4, 28
            image = Image.new("RGBA", (size*scale, size*scale), (0,0,0,0))
            draw = ImageDraw.Draw(image)
            draw.ellipse((scale, scale, (size-1)*scale, (size-1)*scale),
                         fill=(*tuple(int(background[index:index+2],16) for index in (1,3,5)),255),
                         outline=(145,169,207,255), width=scale)
            cx = cy = (size*scale)//2
            radius = 6*scale
            draw.arc((cx-radius, cy-radius, cx+radius, cy+radius), 45, 325,
                     fill=(224,233,247,255), width=2*scale)
            angle = math.radians(325)
            tip = (cx+radius*math.cos(angle), cy+radius*math.sin(angle))
            tangent = (-math.sin(angle), math.cos(angle))
            normal = (-tangent[1], tangent[0])
            base = (tip[0]-4*scale*tangent[0], tip[1]-4*scale*tangent[1])
            wing = 2*scale
            draw.polygon((tip,
                          (base[0]+wing*normal[0], base[1]+wing*normal[1]),
                          (base[0]-wing*normal[0], base[1]-wing*normal[1])),
                         fill=(224,233,247,255))
            image = image.resize((size, size), Image.Resampling.LANCZOS)
            self._toggle_image = ImageTk.PhotoImage(image, master=self)
            self._toggle_image_key = key
        self.create_image(center_x-14, center_y-14, anchor="nw", image=self._toggle_image,
                          tags=("hero-mode-toggle",))


class DesktopShell:
    def __init__(self, app):
        self.app, self.root, self.family = app, app.root, app.ui_font_family
        self.page = "home"
        self.snapshot = None
        self.hidden = False
        self.loading = False
        self.results = queue.Queue()
        self.palette = dict(PALETTE)
        self.locale = app.language
        self.filter_text = ""
        self.ledger_limit = 50
        self.asset_tab = "cash"
        self.hero_profit_mode = True
        self.poll_count = 0
        self.file_signature = None
        self.resize_coordinator = ResizeRenderCoordinator(self.root)
        self.root._bk_resize_coordinator = self.resize_coordinator
        self._tracked_window_sizes = {}
        self._resize_source_after = {}
        self._resize_message_hooks = {}
        self.root.bind_all("<Configure>", self._track_window_resize, add="+")
        self.root.bind_all("<Map>", self._attach_window_resize_hook, add="+")
        self.root.bind_all("<Destroy>", self._forget_window_resize, add="+")
        self.shell = ttk.Frame(self.root, style="App.TFrame")
        self.shell.pack(fill="both", expand=True)
        self.shell.rowconfigure(1, weight=1)
        self.shell.columnconfigure(0, weight=1)
        self._topbar()
        self.layout_store = DesktopLayoutStore()
        self.saved_sidebar_width = self.layout_store.load_sidebar_width()
        self._last_saved_sidebar_width = None
        self.panes = DesktopPanedWindow(
            self.shell, orient=tk.HORIZONTAL, background=PALETTE["border"],
            borderwidth=0, relief="flat", sashwidth=SASH_WIDTH, sashpad=0,
            sashrelief="flat", sashcursor="sb_h_double_arrow",
            showhandle=True, handlesize=6, handlepad=0, opaqueresize=False,
        )
        self.panes.grid(row=1, column=0, sticky="nsew")
        self.host = ttk.Frame(self.panes, style="App.TFrame")
        self.host.columnconfigure(0, weight=1)
        self.host.rowconfigure(0, weight=1)
        self.pages = {}
        self.contents = {}
        self.canvases = {}
        for page in ("home", "entry", "ledger", "assets", "more"):
            frame = ttk.Frame(self.host, style="App.TFrame")
            frame.grid(row=0, column=0, sticky="nsew")
            self.pages[page] = frame
            if page != "entry":
                self._scroll_page(page, frame)
        self.record_page = self.pages["entry"]
        self.navigation = ttk.Frame(self.panes, style="Surface.TFrame", padding=(10, 18))
        self.panes.add(
            self.navigation, minsize=MIN_SIDEBAR_WIDTH,
            width=self.saved_sidebar_width, stretch="never",
        )
        self.panes.add(self.host, minsize=MIN_CONTENT_WIDTH, stretch="always")
        self.panes.bind("<ButtonRelease-1>", self._save_sidebar_width_after_drag, add="+")
        self.root.after_idle(self._restore_sidebar_width)
        self.navigation.columnconfigure(0, weight=1)
        self.nav_buttons = {}
        for index, (page, title) in enumerate((
            ("home", "总览"), ("entry", "记录"), ("ledger", "账单"),
            ("assets", "资产"), ("more", "更多"),
        )):
            button = ttk.Button(self.navigation, text="  "+translate(title), width=11, compound="left",
                                style="Dock.TButton", command=lambda value=page: self.navigate(value))
            button.grid(row=index, column=0, pady=(0, 5), sticky="ew")
            self.nav_buttons[page] = button
        ttk.Separator(self.navigation).grid(row=5, column=0, sticky="ew", pady=(16, 9))
        self.favorite_store = DesktopFavoriteStore()
        self.favorite_ids = self.favorite_store.load()
        self.favorite_actions = {
            "accounts": ("银行账户和信用卡", self.app.open_accounts_workspace),
            "cash": ("现金管理", self.app.open_cash_management),
            "credit": ("信用卡管理", self.app.open_credit_management),
            "payments": ("付款方式和定期付款", self.app.open_payment_recurring_workspace),
            "reports": ("财务报表和预算", self.app.open_reports_savings_workspace),
            "fixed_assets": ("固定资产管理", self.app.open_fixed_assets),
            "food": ("食材与饮食记录", self.app.open_food_tracking),
            "backup": ("备份与同步", lambda: self.app.open_settings("账本与备份")),
            "skills": ("设置与 Agent Skill", lambda: self.app.open_settings("Agent 配置与 Skill")),
        }
        self.favorite_heading = ttk.Frame(self.navigation, style="Surface.TFrame")
        self.favorite_heading.grid(row=6, column=0, sticky="ew", pady=(0, 3))
        self.favorite_heading.columnconfigure(0, weight=1)
        ttk.Label(self.favorite_heading, text=translate("常用功能", self.locale),
                  style="Hint.TLabel").grid(row=0, column=0, sticky="w", padx=(10, 0))
        self.favorite_add_button = ttk.Button(
            self.favorite_heading, text="＋", style="FavoriteAdd.TButton",
            command=self._open_favorite_picker,
        )
        self.favorite_add_button.grid(row=0, column=1, sticky="e", padx=(0, 4))
        Tooltip(self.favorite_add_button, lambda: translate("添加常用功能", self.locale))
        self.favorite_list = ttk.Frame(self.navigation, style="Surface.TFrame")
        self.favorite_list.grid(row=7, column=0, sticky="new")
        self.navigation.rowconfigure(8, weight=1)
        ttk.Separator(self.navigation).grid(row=9, column=0, sticky="ew", pady=(10, 8))
        self.sidebar_settings_button = ttk.Button(
            self.navigation, text=translate("⚙  设置", self.locale), style="Dock.TButton",
            command=self.app.open_settings,
        )
        self.sidebar_settings_button.grid(row=10, column=0, sticky="ew")
        self.nav_icons = {}
        self.update_icons()
        self._render_favorites()
        self.error = ""
        self.navigate("home")
        self.root.after(150, self.refresh)
        self.root.after(150, self._poll)
        self.root.bind("<FocusIn>", self._focus_refresh, add="+")

    def _track_window_resize(self, event):
        window = getattr(event, "widget", None)
        if not isinstance(window, (tk.Tk, tk.Toplevel)):
            return
        try:
            if window.winfo_toplevel() is not window:
                return
            size = (event.width, event.height)
            previous = self._tracked_window_sizes.get(window)
            self._tracked_window_sizes[window] = size
            if previous is None or previous == size:
                return
            source = ("tk-window-configure", id(window))
            self.resize_coordinator.set_source_active(source, True)
            pending = self._resize_source_after.pop(source, None)
            if pending is not None:
                self.root.after_cancel(pending)

            def finish_resize(source_key=source):
                self._resize_source_after.pop(source_key, None)
                self.resize_coordinator.set_source_active(source_key, False)

            self._resize_source_after[source] = self.root.after(120, finish_resize)
        except tk.TclError:
            return

    def _attach_window_resize_hook(self, event):
        window = getattr(event, "widget", None)
        if not isinstance(window, tk.Toplevel) or window in self._resize_message_hooks:
            return
        try:
            if window.winfo_toplevel() is not window or window.overrideredirect():
                return
            hook = WindowResizeMessageHook(window, self.resize_coordinator)
            if hook.install():
                self._resize_message_hooks[window] = hook
        except tk.TclError:
            return

    def _forget_window_resize(self, event):
        window = getattr(event, "widget", None)
        hook = self._resize_message_hooks.pop(window, None)
        if hook is not None:
            hook.detach()
        if window not in self._tracked_window_sizes:
            return
        self._tracked_window_sizes.pop(window, None)
        source = ("tk-window-configure", id(window))
        pending = self._resize_source_after.pop(source, None)
        if pending is not None:
            try:
                self.root.after_cancel(pending)
            except tk.TclError:
                pass
        self.resize_coordinator.set_source_active(source, False)

    def _restore_sidebar_width(self) -> None:
        if not self.panes.winfo_exists():
            return
        if not self.panes.winfo_ismapped() or self.panes.winfo_width() < 10:
            self.root.after(100, self._restore_sidebar_width)
            return
        try:
            self.panes.sash_place(0, self.saved_sidebar_width, 0)
            self._last_saved_sidebar_width = self.panes.sash_coord(0)[0]
        except tk.TclError:
            # The PanedWindow may not have its final geometry until it is mapped.
            if self.root.winfo_exists():
                self.root.after(100, self._restore_sidebar_width)

    def _save_sidebar_width_after_drag(self, _event=None) -> None:
        if self.root.winfo_exists():
            self.root.after_idle(self._clamp_and_save_sidebar_width)

    def _clamp_and_save_sidebar_width(self) -> None:
        self._clamp_sidebar_sash()
        self._save_sidebar_width()

    def _clamp_sidebar_sash(self) -> None:
        try:
            position = int(self.panes.sash_coord(0)[0])
            available = self.panes.winfo_width() - MIN_CONTENT_WIDTH - SASH_WIDTH
        except (tk.TclError, TypeError, IndexError):
            return
        maximum = min(MAX_SIDEBAR_WIDTH, available)
        if maximum < MIN_SIDEBAR_WIDTH:
            return
        clamped = max(MIN_SIDEBAR_WIDTH, min(maximum, position))
        if clamped != position:
            self.panes.sash_place(0, clamped, 0)

    def _save_sidebar_width(self) -> None:
        try:
            width = int(self.panes.sash_coord(0)[0])
        except (tk.TclError, TypeError, IndexError):
            return
        width = max(MIN_SIDEBAR_WIDTH, min(MAX_SIDEBAR_WIDTH, width))
        if width == self._last_saved_sidebar_width:
            return
        try:
            self.layout_store.save_sidebar_width(width)
        except OSError as exc:
            messagebox.showerror(
                translate("无法保存界面布局", self.locale),
                translate("侧边栏宽度没有保存：{error}", self.locale).format(error=exc),
                parent=self.root,
            )
            return
        self.saved_sidebar_width = width
        self._last_saved_sidebar_width = width

    def _persist_favorites(self, favorites: list[str]) -> bool:
        try:
            self.favorite_store.save(favorites)
        except OSError as exc:
            messagebox.showerror(
                translate("无法保存常用功能", self.locale),
                translate("常用功能没有保存：{error}", self.locale).format(error=exc),
                parent=self.root,
            )
            return False
        self.favorite_ids = favorites
        self._render_favorites()
        return True

    def _draw_favorite(self, target, label, flags):
        if not target.winfo_exists():
            return
        target.delete("all")
        width, height = target.winfo_width(), target.winfo_height()
        if width < 4 or height < 4:
            return
        active = flags["hovered"] or flags["focused"]
        fill = PALETTE["favorite_hover"] if active else PALETTE["surface"]
        outline = PALETTE["border"] if active else PALETTE["surface"]

        def rounded_rect(color_value, inset):
            left, top = inset, inset
            right, bottom = width - inset - 1, height - inset - 1
            radius = max(1, (bottom - top + 1) // 2)
            target.create_rectangle(left + radius, top, right - radius, bottom,
                                    fill=color_value, outline="")
            target.create_rectangle(left, top + radius, right, bottom - radius,
                                    fill=color_value, outline="")
            for x, y in ((left, top), (right - 2 * radius + 1, top),
                         (right - 2 * radius + 1, bottom - 2 * radius + 1),
                         (left, bottom - 2 * radius + 1)):
                target.create_oval(x, y, x + 2 * radius - 1, y + 2 * radius - 1,
                                   fill=color_value, outline="")

        rounded_rect(outline, 0)
        rounded_rect(fill, 1)
        target.create_text(
            12, height / 2, text=translate(label, self.locale),
            anchor="w", font=(self.family, 9),
            fill=PALETTE["text"] if active else PALETTE["muted"],
        )
        if active:
            target.create_text(
                width - 17, height / 2 - 1, text="×",
                anchor="center", font=(self.family, 12, "bold"),
                fill=PALETTE["favorite_remove_text"],
            )

    def _render_favorites(self) -> None:
        for child in self.favorite_list.winfo_children():
            child.destroy()
        for favorite_id in self.favorite_ids:
            favorite = self.favorite_actions.get(favorite_id)
            if favorite is None:
                continue
            title, command = favorite
            row = ttk.Frame(self.favorite_list, style="Surface.TFrame")
            row.pack(fill="x", pady=(0, 3))
            button = tk.Canvas(
                row, height=34, bg=PALETTE["surface"], highlightthickness=0,
                bd=0, cursor="hand2", takefocus=True,
            )
            button.pack(fill="x", expand=True)
            state = {"hovered": False, "focused": False}

            def draw_favorite(target=button, label=title, flags=state):
                callback = lambda target=target, label=label, flags=flags: self._draw_favorite(
                    target, label, flags
                )
                if defer_during_interactive_resize(target, target, callback):
                    return
                self._draw_favorite(target, label, flags)

            def show_favorite(_event=None, flags=state, draw=draw_favorite):
                flags["hovered"] = True
                draw()

            def hide_favorite(_event=None, flags=state, draw=draw_favorite):
                flags["hovered"] = False
                draw()

            def focus_favorite(_event=None, flags=state, draw=draw_favorite):
                flags["focused"] = True
                draw()

            def blur_favorite(_event=None, flags=state, draw=draw_favorite):
                flags["focused"] = False
                draw()

            def activate_favorite(event, value=favorite_id, callback=command, target=button):
                if event.x >= target.winfo_width() - 36:
                    self._remove_favorite(value)
                else:
                    callback()
                return "break"

            button.bind("<Configure>", lambda _event, draw=draw_favorite: draw(), add="+")
            button.bind("<Enter>", show_favorite, add="+")
            button.bind("<Leave>", hide_favorite, add="+")
            button.bind("<FocusIn>", focus_favorite, add="+")
            button.bind("<FocusOut>", blur_favorite, add="+")
            button.bind("<ButtonRelease-1>", activate_favorite, add="+")
            button.bind("<Return>", lambda _event, callback=command: callback(), add="+")
            button.bind("<space>", lambda _event, callback=command: callback(), add="+")
            Tooltip(button, lambda value=title, target=button: translate(
                "移除此常用功能" if target.winfo_pointerx() - target.winfo_rootx()
                >= target.winfo_width() - 36 else value, self.locale
            ))
        if not self.favorite_ids:
            ttk.Label(
                self.favorite_list, text=translate("点击加号添加常用功能", self.locale),
                style="Hint.TLabel", wraplength=145,
            ).pack(anchor="w", padx=10, pady=(2, 8))

    def _open_favorite_picker(self) -> None:
        available = [key for key in self.favorite_actions if key not in self.favorite_ids]
        dialog = tk.Toplevel(self.root)
        dialog.title(translate("添加常用功能", self.locale))
        dialog.transient(self.root)
        dialog.configure(bg=PALETTE["background"])
        dialog.resizable(False, False)
        panel = ttk.Frame(dialog, style="App.TFrame", padding=16)
        panel.pack(fill="both", expand=True)
        ttk.Label(panel, text=translate("添加常用功能", self.locale),
                  style="ManagementTitle.TLabel").pack(anchor="w", pady=(0, 4))
        ttk.Label(panel, text=translate("选择要固定在左侧的功能", self.locale),
                  style="Hint.TLabel").pack(anchor="w", pady=(0, 12))
        if not available:
            ttk.Label(panel, text=translate("所有功能都已添加", self.locale),
                      style="Hint.TLabel").pack(anchor="w", pady=12)
        else:
            for favorite_id in available:
                title = self.favorite_actions[favorite_id][0]
                ttk.Button(
                    panel, text="＋  "+translate(title, self.locale), style="Settings.TButton",
                    command=lambda value=favorite_id, popup=dialog: self._add_favorite(value, popup),
                ).pack(fill="x", pady=3)
        ttk.Button(panel, text=translate("关闭", self.locale), command=dialog.destroy).pack(
            anchor="e", pady=(12, 0)
        )
        dialog.update_idletasks()
        center_window(dialog, self.root)
        dialog.grab_set()

    def _add_favorite(self, favorite_id: str, dialog: tk.Toplevel) -> None:
        if favorite_id in self.favorite_ids or favorite_id not in self.favorite_actions:
            return
        if self._persist_favorites([*self.favorite_ids, favorite_id]):
            dialog.destroy()

    def _remove_favorite(self, favorite_id: str) -> None:
        if favorite_id in self.favorite_ids:
            self._persist_favorites([value for value in self.favorite_ids if value != favorite_id])

    def update_icons(self):
        paths = {
            "home": [[(3,11),(12,3),(21,11)],[(5,10),(5,21),(10,21),(10,14),(14,14),(14,21),(19,21),(19,10)]],
            "entry": [[(4,4),(20,4),(20,17),(10,17),(4,21),(4,4)],[(8,8),(16,8)],[(8,12),(15,12)]],
            "ledger": [[(5,3),(20,3),(20,21),(5,21),(5,3)],[(9,3),(9,21)],[(12,8),(17,8)],[(12,12),(17,12)]],
            "assets": [[(4,6),(20,6),(21,8),(21,20),(3,20),(3,7),(16,3)],[(21,11),(16,11),(16,16),(21,16)]],
            "more": [],
        }
        def distance(x,y,a,b):
            dx,dy=b[0]-a[0],b[1]-a[1]
            t=max(0,min(1,((x-a[0])*dx+(y-a[1])*dy)/max(1,dx*dx+dy*dy)))
            return math.hypot(x-a[0]-t*dx,y-a[1]-t*dy)
        for key, lines in paths.items():
            segments=[(points[i],points[i+1]) for points in lines for i in range(len(points)-1)]
            for active in (False,True):
                ink=PALETTE["accent" if active else "muted"]
                background=PALETTE["selected" if active else "surface"]
                fg=tuple(int(ink[i:i+2],16) for i in (1,3,5))
                bg=tuple(int(background[i:i+2],16) for i in (1,3,5))
                pixels=bytearray()
                for y in range(26):
                    for x in range(26):
                        d=min((distance(x,y,a,b) for a,b in segments),default=100)
                        if key=="more":
                            d=min(math.hypot(x-c,y-12) for c in (5,12,19))-.6
                        coverage=max(0,min(1,1.5-d))
                        pixels.extend(round(a*coverage+b*(1-coverage)) for a,b in zip(fg,bg))
                self.nav_icons[(key,active)]=tk.PhotoImage(master=self.root,data=b"P6\n26 26\n255\n"+pixels,format="PPM")

    def _topbar(self):
        self.window_frame = DesktopFrame(self.root)
        self.window_frame.add_resize_listener(self.resize_coordinator.set_active)
        top = ttk.Frame(self.shell, style="Surface.TFrame", padding=(14, 4, 4, 4))
        top.grid(row=0, column=0, sticky="ew")
        top.columnconfigure(1, weight=1)
        title = ttk.Label(top, text="家庭记账", style="Brand.TLabel")
        title.grid(row=0, column=0, sticky="w", padx=(0, 24))
        drag_area = ttk.Frame(top, style="Surface.TFrame")
        drag_area.grid(row=0, column=1, sticky="nsew")
        for target in (top, title, drag_area):
            self.window_frame.bind_drag(target)
        def caption_icon(column, text, command, tooltip, hover_style="CaptionIconHover.TLabel"):
            icon = ttk.Label(
                top, text=text, width=3, style="CaptionIcon.TLabel", cursor="hand2", takefocus=True,
            )
            icon.grid(row=0, column=column, sticky="ns")
            icon.bind("<Enter>", lambda _event: icon.configure(style=hover_style), add="+")
            icon.bind("<Leave>", lambda _event: icon.configure(style="CaptionIcon.TLabel"), add="+")

            def activate(_event=None):
                command()
                return "break"

            icon.bind("<ButtonRelease-1>", activate, add="+")
            icon.bind("<Return>", activate, add="+")
            icon.bind("<space>", activate, add="+")
            Tooltip(icon, tooltip)
            return icon

        caption_icon(2, "🔄", self.app.restart_application, lambda: translate("重启软件", self.locale))
        caption_icon(3, "−", self.root.iconify, "最小化")
        caption_icon(
            4, "□", self.window_frame.maximize,
            lambda: translate("还原窗口", self.locale)
            if self.root.state() == "zoomed" else translate("最大化", self.locale),
        )
        caption_icon(5, "×", self.app.close, "关闭窗口", "CaptionCloseHover.TLabel")

    def _scroll_page(self, page, parent):
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(0, weight=1)
        canvas = tk.Canvas(parent, bg=PALETTE["background"], highlightthickness=0, bd=0, yscrollincrement=1)
        canvas._bk_smooth_scroll = True
        bar = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=bar.set)
        canvas.grid(row=0, column=0, sticky="nsew")
        bar.grid(row=0, column=1, sticky="ns")
        body = ttk.Frame(canvas, style="App.TFrame")
        window = canvas.create_window((0,0), anchor="nw", window=body)
        latest_width = [canvas.winfo_width()]
        def apply_resize():
            if not canvas.winfo_exists():
                return
            width = max(300, min(1240, latest_width[0]-40))
            canvas.itemconfigure(window, width=width)
            canvas.coords(window, max(20,(latest_width[0]-width)//2), 0)
        def resize(event):
            latest_width[0] = event.width
            if defer_during_interactive_resize(canvas, canvas, apply_resize):
                return
            apply_resize()
        canvas.bind("<Configure>", resize)
        def update_scrollregion(_event=None):
            if defer_during_interactive_resize(
                    canvas, (canvas, "scrollregion"), update_scrollregion):
                return
            canvas.configure(scrollregion=canvas.bbox("all"))
        body.bind("<Configure>", update_scrollregion)
        self.contents[page], self.canvases[page] = body, canvas

    def navigate(self, page):
        if page not in self.pages:
            return
        self.page = page
        self.pages[page].tkraise()
        if hasattr(self, "nav_buttons"):
            for key, button in self.nav_buttons.items():
                button.configure(style="Selected.Dock.TButton" if key == page else "Dock.TButton",
                                 image=self.nav_icons.get((key,key == page),""))
        self.render(page)
        if page == "entry" and hasattr(self.app, "input_box"):
            self.app.input_box.focus_set()
        if page != "entry":
            self.canvases[page].after_idle(lambda value=page:self.canvases[value].yview_moveto(0))
            self.refresh()

    def refresh(self):
        if self.loading or self.app._github_restore_in_progress:
            return
        self.loading = True
        def load():
            try:
                self.results.put((read_overview(self.app.database_path), ""))
            except Exception as exc:
                self.results.put((None, str(exc)))
        threading.Thread(target=load, name="desktop-overview-reader", daemon=True).start()

    def _focus_refresh(self, event):
        if event.widget is self.root:
            self.refresh()

    def _poll(self):
        try:
            changed = self.palette != PALETTE or self.locale != self.app.language
            if changed:
                self.palette, self.locale = dict(PALETTE), self.app.language
                self.update_icons()
                for key,button in self.nav_buttons.items():
                    button.configure(image=self.nav_icons[(key,key==self.page)])
                self.render(self.page)
            try:
                data, self.error = self.results.get_nowait()
                self.loading = False
                if data is not None:
                    changed = data != self.snapshot
                    self.snapshot = data
                else:
                    changed = True
                if changed and not (self.page=="ledger" and isinstance(self.root.focus_get(),ttk.Entry)):
                    self.render(self.page)
            except queue.Empty:
                pass
            self.poll_count += 1
            if self.poll_count % 10 == 0:
                try:
                    paths = (self.app.database_path, Path(str(self.app.database_path)+"-wal"))
                    signature = tuple((path.stat().st_mtime_ns,path.stat().st_size) if path.exists() else None for path in paths)+(_today_japan(),)
                    if signature != self.file_signature:
                        self.file_signature = signature
                        self.refresh()
                except OSError:
                    pass
            self.root.after(200, self._poll)
        except tk.TclError:
            pass

    def display_name(self, value):
        return re.sub(r"\d", "*", value) if self.hidden else value

    def mask(self, key="amount"):
        # Deliberately independent of the number and its magnitude.
        import zlib
        counts = {"net-assets": 6, "cny-assets": 4, "expense_minor": 4,
                  "income_minor": 5, "budget-remaining": 5, "budget-total": 4}
        count = counts.get(str(key), 4 + zlib.crc32(str(key).encode("utf-8")) % 3)
        return "*" * count

    def money(self, value, currency="JPY", *, mask_key="amount"):
        if self.hidden:
            return self.mask(mask_key)
        if value is None:
            return "—"
        return minor_to_text(int(value), 2 if currency == "CNY" else 0, currency)

    def toggle_hidden(self):
        self.hidden = not self.hidden
        self.render(self.page)

    def label(self, parent, text, size=11, role="text", bold=False, surface=True):
        masked = self.hidden and bool(re.fullmatch(r"\+?\*{4,6}", str(text)))
        mask_size = max(9, round(size * .72))
        font = ("Consolas", mask_size) if masked else (
            (self.family,size,"bold") if bold else (self.family,size))
        return tk.Label(parent, text=text, bg=PALETTE["surface" if surface else "background"],
                        fg=PALETTE.get(role, role), font=font,
                        pady=max(0,(size-mask_size)//2) if masked else 0,
                        anchor="nw" if masked else "w", justify="left", wraplength=820)

    def card(self, parent, **kwargs):
        return RoundedPanel(parent, padding=18, radius=12, **kwargs)

    def heading(self, parent, title):
        row = ttk.Frame(parent, style="App.TFrame", padding=(0, 18, 0, 16))
        row.pack(fill="x")
        row.columnconfigure(0, weight=1)

        self.label(row, title, 21, bold=True, surface=False).grid(row=1,column=0,sticky="w",pady=(4,0))
        privacy_button = ttk.Button(row, text="◉" if self.hidden else "◎", style="Circle.TButton", width=3,
                                    command=self.toggle_hidden)
        privacy_button.grid(row=0,column=1,rowspan=2,padx=(0,8))
        Tooltip(privacy_button, lambda: "显示金额" if self.hidden else "隐藏金额")
        refresh_button = ttk.Button(row, text="↻", style="Circle.TButton", width=3, command=self.refresh)
        refresh_button.grid(row=0,column=2,rowspan=2)
        Tooltip(refresh_button, "刷新")

    def render(self, page):
        if page == "entry":
            return
        body = self.contents[page]
        position = self.canvases[page].yview()[0]
        for child in body.winfo_children():
            child.destroy()
        self.heading(body, {"home":"总览", "ledger":"账单", "assets":"资产", "more":"更多"}[page])
        if self.error:
            card = self.card(body)
            card.pack(fill="x", pady=(0,12))
            self.label(card.body, translate("账本暂时无法读取，请刷新重试。"), role="muted").pack(anchor="w")
        getattr(self, "render_"+page)(body)
        ttk.Frame(body, height=24, style="App.TFrame").pack()
        self.canvases[page].after_idle(lambda: self.canvases[page].yview_moveto(position))

    def render_home(self, body):
        hero = GradientHero(body, self)
        hero.pack(fill="x", pady=(0,12))
        metrics = ttk.Frame(body, style="App.TFrame")
        metrics.pack(fill="x", pady=(0,12))
        metrics.columnconfigure(0,weight=1,uniform="metrics")
        metrics.columnconfigure(1,weight=1,uniform="metrics")
        metrics.columnconfigure(2,weight=2,uniform="metrics")
        data = self.snapshot
        profit = data["profit"] if data else None
        summary = profit["jpy_equivalent"] if profit else {}
        small_cards=[]
        for column, title, key, tone, note in (
            (0,"本期支出","expense_minor",PALETTE["expense"], (profit["start"]+" — "+profit["through"]) if profit else ""),
            (1,"本期收入","income_minor",PALETTE["income"],translate("含人民币参考汇率折算")),
        ):
            card = self.card(metrics)
            card.grid(row=0,column=column,sticky="nsew",padx=(0,14))
            small_cards.append(card)
            self.label(card.body,title,10,"muted").pack(anchor="w")
            self.label(card.body,self.money(summary.get(key),mask_key=key),18,tone,True).pack(anchor="w",pady=(12,10))
            text = self.label(card.body,note,9,"muted")
            text.configure(wraplength=225)
            text.pack(anchor="w")
        budget_card = self.card(metrics)
        budget_card.grid(row=0,column=2,sticky="nsew")
        layout={"wide":None}
        def reflow(event):
            if defer_during_interactive_resize(metrics, metrics, lambda: reflow(None)):
                return
            width = metrics.winfo_width() if event is None else event.width
            wide=width>=860
            if wide==layout["wide"]:
                return
            layout["wide"]=wide
            metrics.columnconfigure(2,weight=2 if wide else 0,uniform="metrics" if wide else "")
            for index,card in enumerate(small_cards):
                card.grid_configure(row=0,column=index,columnspan=1,padx=(0,14 if wide or index==0 else 0))
            budget_card.grid_configure(row=0 if wide else 1,column=2 if wide else 0,columnspan=1 if wide else 2,pady=(0,0) if wide else (14,0))
        metrics.bind("<Configure>",reflow)

        row = ttk.Frame(budget_card.body,style="Surface.TFrame")
        row.pack(fill="x")
        self.label(row,"预算，还剩",12,bold=True).pack(side="left")
        ttk.Button(row,text="›",width=3,style="Surface.Settings.TButton",command=self.app.open_savings_plan).pack(side="right")
        budget = int(data["settings"].get("monthly_jpy_budget_minor", "0")) if data else 0
        expense = int(summary.get("expense_minor",0))
        self.label(budget_card.body,self.money(budget-expense,mask_key="budget-remaining") if data else "—",20,bold=True).pack(anchor="w",pady=(14,14))
        percent = max(0,min(100,expense*100//budget)) if budget>0 else 0
        RoundedProgressBar(budget_card.body, percent / 100, height=8,
                           track=PALETTE["selected"], gradient=True).pack(fill="x")
        self.label(budget_card.body,translate("预算")+" "+self.money(budget,mask_key="budget-total") if data else "—",9,"muted").pack(anchor="e",pady=(8,0))
        details = ttk.Frame(body, style="App.TFrame")
        details.pack(fill="x")
        details.columnconfigure(0, weight=1, uniform="details")
        details.columnconfigure(1, weight=1, uniform="details")
        category_card = card = self.card(details)
        card.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        row=ttk.Frame(card.body,style="Surface.TFrame");row.pack(fill="x",pady=(0,12))
        self.label(row,"钱花在哪里",13,bold=True).pack(side="left")
        ttk.Button(row,text="报表",style="Surface.Settings.TButton",command=self.app.open_financial_statements).pack(side="right")
        categories = sorted(summary.get("categories",{}).items(),key=lambda pair:pair[1],reverse=True)[:6]
        maximum = max([int(value) for _,value in categories]+[1])
        category_colors = ("#7da7e0", "#88baa9", "#b09ccf", "#e4b18b", "#88b9c9", "#d8a3b1")
        for index, (name,value) in enumerate(categories):
            row=ttk.Frame(card.body,style="Surface.TFrame");row.pack(fill="x",pady=(7,4))
            self.label(row,name,10).pack(side="left")
            self.label(row,self.money(value,mask_key="category:"+name),10,bold=True).pack(side="right")
            ratio = max(0, min(1, int(value) / maximum))
            RoundedProgressBar(card.body, ratio, height=7, track=PALETTE["border"],
                               fill=category_colors[index % len(category_colors)]).pack(fill="x",pady=(0,8))
        if not categories:
            self.label(card.body,"记录后会在这里呈现",11,"muted").pack(anchor="w")
        recent_card = card = self.card(details)
        card.grid(row=0, column=1, sticky="nsew")
        detail_layout = {"wide": None}
        def reflow_details(event):
            if defer_during_interactive_resize(details, details, lambda: reflow_details(None)):
                return
            width = details.winfo_width() if event is None else event.width
            wide = width >= 930
            if detail_layout["wide"] == wide:
                return
            detail_layout["wide"] = wide
            details.columnconfigure(1, weight=1 if wide else 0, uniform="details" if wide else "")
            category_card.grid_configure(padx=(0,12) if wide else 0)
            recent_card.grid_configure(row=0 if wide else 1, column=1 if wide else 0, pady=0 if wide else (12,0))
        details.bind("<Configure>", reflow_details)
        row=ttk.Frame(card.body,style="Surface.TFrame");row.pack(fill="x",pady=(0,8))
        self.label(row,"最近记录",13,bold=True).pack(side="left")
        ttk.Button(row,text="全部",style="Surface.Settings.TButton",command=lambda:self.navigate("ledger")).pack(side="right")
        for transaction in (data["transactions"][:4] if data else []):
            self.transaction_row(card.body,transaction)
        if not data or not data["transactions"]:
            self.label(card.body,"从第一笔开始记录生活",11,"muted").pack(anchor="w",pady=12)
        if summary.get("missing_conversion_count",0):
            self.label(body,"部分历史人民币记录缺少汇率，未计入合并报表。",10,"muted",surface=False).pack(anchor="w")

    def transaction_row(self, parent, item):
        row = ttk.Frame(parent,style="Surface.TFrame",padding=(0,9))
        row.pack(fill="x")
        row.columnconfigure(1,weight=1)
        tone = PALETTE["income"] if item["kind"] == "income" else PALETTE["expense"] if item["kind"] == "expense" else PALETTE["accent"]
        self.label(row,{"income":"↙","expense":"↗","transfer":"⇄"}.get(item["kind"],"•"),18,tone).grid(row=0,column=0,rowspan=3,padx=(0,18))
        self.label(row,item["description"],12,bold=True).grid(row=0,column=1,sticky="w")
        account=item.get("account_name") or translate("备查")
        if item["kind"] == "transfer":
            account += " → "+(item.get("to_account_name") or "")
        self.label(row,(item.get("category_name") or "")+" · "+account,10,"muted").grid(row=1,column=1,sticky="w",pady=(4,0))
        self.label(row,item["occurred_on"],9,"muted").grid(row=2,column=1,sticky="w",pady=(4,0))
        sign={"income":"+","expense":"−"}.get(item["kind"],"")
        self.label(row,sign+self.money(item["amount_minor"],item["currency"],mask_key="transaction:"+str(item["id"])),13,tone,True).grid(row=0,column=2,rowspan=2,padx=(14,0))
        for target in (row,*row.winfo_children()):
            target.configure(cursor="hand2")
            target.bind("<Button-1>",lambda _event,value=item:self.show_transaction(value))

    def show_transaction(self,item):
        dialog=tk.Toplevel(self.root)
        dialog.title("交易详情");dialog.transient(self.root)
        dialog.geometry("640x480");dialog.minsize(520,420)
        panel=ttk.Frame(dialog,style="App.TFrame",padding=26);panel.pack(fill="both",expand=True)
        self.label(panel,"交易详情",22,bold=True,surface=False).pack(anchor="w",pady=(0,20))
        card=self.card(panel);card.pack(fill="both",expand=True)
        for title,value in (("说明",item["description"]),("日期",item["occurred_on"]),
                            ("类别",item.get("category_name") or "—"),
                            ("账户",(item.get("account_name") or translate("备查"))+((" → "+(item.get("to_account_name") or "")) if item["kind"]=="transfer" else "")),
                            ("金额",{"income":"+","expense":"−"}.get(item["kind"],"")+self.money(item["amount_minor"],item["currency"]))):
            self.label(card.body,translate(title)+"  ·  "+value,11).pack(anchor="w",pady=(0,12))
        ttk.Button(panel,text="关闭",command=dialog.destroy).pack(anchor="e",pady=(16,0))
        dialog.bind("<Escape>",lambda _event:dialog.destroy())


    def render_ledger(self, body):
        controls=self.card(body);controls.pack(fill="x",pady=(0,12))
        row=ttk.Frame(controls.body,style="Surface.TFrame");row.pack(fill="x")
        self.label(row,"查找记录",11,"muted").pack(side="left",padx=(0,12))
        query=tk.StringVar(value=self.filter_text)
        entry=ttk.Entry(row,textvariable=query);entry.pack(side="left",fill="x",expand=True,padx=(0,12))
        def search():
            self.filter_text=query.get().strip();self.ledger_limit=50;self.render("ledger")
        entry.bind("<Return>",lambda _event:search())
        ttk.Button(row,text="搜索",command=search).pack(side="left")
        ttk.Button(row,text="管理账单",command=self.app.open_transaction_history).pack(side="left",padx=(10,0))
        card=self.card(body);card.pack(fill="x",pady=(0,12))
        rows=self.snapshot["transactions"] if self.snapshot else []
        if self.filter_text:
            query=self.filter_text.casefold()
            rows=[row for row in rows if query in " ".join(str(row.get(key) or "") for key in
                  ("description","account_name","to_account_name","category_name","occurred_on","amount_minor")).casefold()]
        for transaction in rows[:self.ledger_limit]:
            self.transaction_row(card.body,transaction)
            tk.Frame(card.body,height=1,bg=PALETTE["border"]).pack(fill="x")
        if not rows:
            self.label(card.body,"暂无记录",11,"muted").pack(anchor="w")
        if len(rows)>self.ledger_limit:
            def more():
                self.ledger_limit+=50;self.render("ledger")
            ttk.Button(card.body,text="加载更多",command=more).pack(pady=(14,0))

    def render_assets(self, body):
        tabs=ttk.Frame(body,style="App.TFrame");tabs.pack(fill="x",pady=(0,12))
        for key,title in (("cash","资金账户"),("credit","信用卡"),("fixed","固定资产")):
            def select(value=key):
                self.asset_tab=value;self.render("assets")
            ttk.Button(tabs,text=title,style="Selected.Agent.TButton" if self.asset_tab==key else "Agent.TButton",
                       command=select).pack(side="left",padx=(0,8))
        if not self.snapshot:
            return
        manage = self.app.open_cash_management if self.asset_tab=="cash" else self.app.open_credit_management if self.asset_tab=="credit" else self.app.open_fixed_assets
        actions=ttk.Frame(body,style="App.TFrame");actions.pack(fill="x",pady=(0,12))
        actions.columnconfigure(0,weight=1)
        note=self.label(actions,"账户与额度按本机账本计算",10,"muted",surface=False)
        note.grid(row=0,column=0,sticky="w",padx=(0,12))
        ttk.Button(actions,text="管理账户" if self.asset_tab=="cash" else "管理信用卡" if self.asset_tab=="credit" else "资产管理",
                   style="HeaderPrimary.TButton",command=manage).grid(row=0,column=1,sticky="e")
        def resize_actions(event=None):
            width = actions.winfo_width() if event is None else event.width
            callback = lambda width=width: note.configure(wraplength=max(160,width-190))
            if defer_during_interactive_resize(actions, actions, callback):
                return
            callback()
        actions.bind("<Configure>",resize_actions)
        grid=ttk.Frame(body,style="App.TFrame");grid.pack(fill="x",anchor="w")
        grid.columnconfigure(0,weight=1)
        cards=[]
        def resize_cards(event=None):
            if defer_during_interactive_resize(grid, grid, lambda: resize_cards()):
                return
            width=max(1,min(760,grid.winfo_width() if event is None else event.width))
            for card in cards:
                if int(card.cget("width")) != width:
                    card.configure(width=width)
        grid.bind("<Configure>",resize_cards)

        def add_card():
            card=RoundedPanel(grid,padding=12,radius=12,width=760)
            cards.append(card)
            card.grid(row=len(cards)-1,column=0,sticky="w",pady=(0,8))
            return card

        def fit_card(card):
            def resize(event=None):
                if defer_during_interactive_resize(card.body, card.body, lambda: resize()):
                    return
                width = card.body.winfo_width() if event is None else event.width
                for label in card.body.winfo_children():
                    if isinstance(label,tk.Label):
                        label.configure(wraplength=max(160,width-2))
            card.body.bind("<Configure>",resize,add="+")

        if self.asset_tab=="credit":
            warning=self.label(body,"欠款为额度差额估算，不代表当月账单。",9,"muted",surface=False)
            warning.pack(before=grid,anchor="w",pady=(0,10))
            for item in self.snapshot["cards"]:
                card=add_card()
                self.label(card.body,self.display_name(item["name"]),12,bold=True).pack(anchor="w")
                self.label(card.body,"当前可用额度",9,"muted").pack(anchor="w",pady=(5,2))
                self.label(card.body,self.money(item["available_minor"],item["currency"],mask_key="credit:"+str(item.get("id",item.get("name","")))),18,bold=True).pack(anchor="w")
                detail=translate("总额度")+" "+self.money(item["limit_minor"],item["currency"])+"     "+translate("欠款估算")+" "+self.money(item["debt_estimate_minor"],item["currency"])
                self.label(card.body,detail,9,"muted").pack(anchor="w",pady=(5,0))
                fit_card(card)
            return
        for item in self.snapshot["balance"]["rows"]:
            is_fixed=item["section"]=="固定资产"
            if (self.asset_tab=="fixed") != is_fixed or item["section"].startswith("负债") or "信用卡" in item["section"]:
                continue
            card=add_card()
            self.label(card.body,self.display_name(item["name"]),12,bold=True).pack(anchor="w")
            asset_key="asset:"+str(item.get("id",item.get("name","")))
            headline=item.get("original_cost_text",item["amount_text"]) if is_fixed else item["amount_text"]
            self.label(card.body,self.mask(asset_key) if self.hidden else headline,20,bold=True).pack(anchor="w",pady=(7,5))
            if is_fixed:
                depreciation=item.get("accumulated_depreciation_text","")
                detail=("−"+depreciation) if depreciation else "−0"
                if self.hidden:
                    detail="−"+self.mask(asset_key+":depreciation")
                self.label(card.body,detail,9,"muted").pack(anchor="w")
            fit_card(card)

    def render_more(self, body):
        for title, subtitle, action in (
            ("付款方式和定期付款","管理支付规则与周期性收支",self.app.open_payment_recurring_workspace),
            ("财务报表和预算","查看家庭财务并管理分类预算",self.app.open_reports_savings_workspace),
            ("资产管理","管理投资资产与固定资产，查看资产价格、月度折旧和账面价值",self.app.open_fixed_assets),
            ("食材与饮食记录","查看采购商品和自动分类结果",self.app.open_food_tracking),
        ):
            card=self.card(body);card.pack(fill="x",pady=(0,14))
            texts=tk.Frame(card.body,bg=PALETTE["surface"]);texts.pack(side="left",fill="x",expand=True)
            self.label(texts,title,14,bold=True).pack(anchor="w")
            self.label(texts,subtitle,10,"muted").pack(anchor="w",pady=(5,0))
            ttk.Button(card.body,text="›",style="Surface.Settings.TButton",width=4,command=action).pack(side="right",padx=(12,0))
            def activate_card(_event, command=action):
                command()
                return "break"

            def bind_card_area(widget):
                widget.configure(cursor="hand2")
                # Keep the arrow's native keyboard/mouse command. Binding it
                # again would run the action twice on a single click.
                if not isinstance(widget, ttk.Button):
                    widget.bind("<ButtonRelease-1>", activate_card, add="+")
                for child in widget.winfo_children():
                    bind_card_area(child)

            bind_card_area(card)
