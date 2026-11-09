"""
ui.py
CustomTkinter user interface for GCash Transaction Record Manager.

Layout
------
    +--------------------------------------------------------------+
    |  Header (title, live date/time)                              |
    +--------------------------------------------------------------+
    |  [Cash-In]  [Cash-Out]  [Balance]  [Total]  [Transfer fees]  |
    +--------------------------------------------------------------+
    |  Period Summary (Daily / Weekly / Monthly, with < Prev Next >)|
    +----------------------+---------------------------------------+
    |  Transaction form    |  Search / filter bar                  |
    |  (add or edit)       |  Records table                        |
    +----------------------+---------------------------------------+
    |  Privacy notice                                              |
    |  Status bar                                                  |
    +--------------------------------------------------------------+

This file only depends on these functions from database.py (unchanged):
    add_transaction, update_transaction, delete_transaction,
    get_transaction, search_transactions, get_dashboard_totals,
    get_period_totals, shift_period, export_transactions_csv,
    import_transactions_csv

IMPORTANT: the main window must be created with customtkinter, e.g.
    import customtkinter as ctk
    root = ctk.CTk()          # instead of tk.Tk()
    app = GCashTransactionApp(root)
    root.mainloop()
"""

import re
import tkinter as tk
import tkinter.font as tkfont
from datetime import date, datetime
from tkinter import ttk, messagebox, filedialog

import customtkinter as ctk

import database

# --------------------------------------------------------------------------
# Constants
# --------------------------------------------------------------------------
TYPE_CASH_IN = "Cash-In"
TYPE_CASH_OUT = "Cash-Out / Withdrawal"
TRANSACTION_TYPES = (TYPE_CASH_IN, TYPE_CASH_OUT)

PERIOD_CHOICES = ("Daily", "Weekly", "Monthly")

# Palette (light blue, GCash-inspired)
BG = "#EAF2FF"           # window background
CARD = "#FFFFFF"         # card background
CARD_ALT = "#F3F8FF"     # zebra-stripe tint for table rows
BORDER = "#D5E3FA"
FIELD_BORDER = "#C4D6F2"
TEXT = "#0F1F3D"
MUTED = "#5F6F8F"

PRIMARY = "#0766F2"      # GCash-style blue
PRIMARY_DARK = "#044FC4"
PRIMARY_SOFT = "#E3EEFF"
PRIMARY_SOFT_HOVER = "#CFE0FD"
PANEL_TINT = "#F1F6FF"   # soft tint for inner boxes
SELECT = "#CFE2FF"       # selected table row

GREEN = "#12A150"        # Cash-In
GREEN_DARK = "#0A6E37"
RED = "#E23D45"          # Cash-Out
RED_DARK = "#A81E27"
RED_SOFT = "#FDEBEC"

AMBER = "#C88A00"        # Transfer fees accent
AMBER_SOFT = "#FFF3D6"
AMBER_TEXT = "#7A4D00"

TABLE_COLUMNS = ("id", "type", "amount", "fee", "date", "time", "reference", "notes")
TABLE_HEADINGS = {
    "id": "ID",
    "type": "Type",
    "amount": "Amount",
    "fee": "Fee",
    "date": "Date",
    "time": "Time",
    "reference": "Reference",
    "notes": "Notes",
}
TABLE_ANCHORS = {
    "id": "center",
    "type": "w",
    "amount": "e",
    "fee": "e",
    "date": "center",
    "time": "center",
    "reference": "center",
    "notes": "w",
}
TABLE_WIDTHS = {
    "id": 55,
    "type": 175,
    "amount": 120,
    "fee": 85,
    "date": 100,
    "time": 85,
    "reference": 90,
    "notes": 240,
}


def pick_font_family(root):
    """Choose the nicest font available on this computer."""
    available = set(tkfont.families(root))
    for name in (
        "Segoe UI",
        "SF Pro Text",
        "Helvetica Neue",
        "Ubuntu",
        "DejaVu Sans",
        "Arial",
    ):
        if name in available:
            return name
    return "Helvetica"


class GCashTransactionApp:
    """Main application window."""

    def __init__(self, root):
        if not isinstance(root, ctk.CTk):
            raise TypeError(
                "GCashTransactionApp needs a customtkinter window. "
                "In your main file, replace  root = tk.Tk()  with  "
                "root = ctk.CTk()  (after  import customtkinter as ctk)."
            )

        ctk.set_appearance_mode("light")
        ctk.set_default_color_theme("blue")

        self.root = root
        self.root.title("GCash Transaction Record Manager Designed by JAL Printing Services")

        self.scale = self.get_scale()
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        width = min(1260, int(screen_w / self.scale) - 40)
        height = min(820, int(screen_h / self.scale) - 90)
        x = max((screen_w - int(width * self.scale)) // 2, 0)
        self.root.geometry(f"{width}x{height}+{x}+8")
        self.root.minsize(1000, 600)
        self.root.configure(fg_color=BG)

        self.font_family = pick_font_family(root)
        self._fonts = {}

        self.selected_id = None      # None = adding, otherwise editing this ID
        self.row_cache = {}          # iid -> row dict (used for sorting)
        self.sort_state = None       # (column, reverse)
        self.total_records = 0
        self._search_job = None
        self._status_job = None

        # Form variables
        self.type_var = tk.StringVar(value=TYPE_CASH_OUT)
        self.amount_var = tk.StringVar()
        self.fee_var = tk.StringVar()
        self.date_var = tk.StringVar()
        self.time_var = tk.StringVar()
        self.reference_var = tk.StringVar()
        self.notes_var = tk.StringVar()
        self.error_var = tk.StringVar()

        # Search / filter variables
        self.search_var = tk.StringVar()
        self.filter_type_var = tk.StringVar(value="All")
        self.filter_date_var = tk.StringVar()

        # Dashboard variables
        self.cash_in_total_var = tk.StringVar(value="₱0.00")
        self.cash_out_total_var = tk.StringVar(value="₱0.00")
        self.cash_in_count_var = tk.StringVar(value="0 transactions")
        self.cash_out_count_var = tk.StringVar(value="0 transactions")
        self.balance_var = tk.StringVar(value="₱0.00")
        self.total_count_var = tk.StringVar(value="0")
        self.total_fees_var = tk.StringVar(value="₱0.00")

        # Period summary variables (daily / weekly / monthly)
        self.period_var = tk.StringVar(value="Daily")
        self.period_ref_date = date.today()
        self.period_label_var = tk.StringVar(value="Loading…")
        self.period_cash_in_var = tk.StringVar(value="₱0.00")
        self.period_cash_out_var = tk.StringVar(value="₱0.00")
        self.period_fees_var = tk.StringVar(value="₱0.00")
        self.period_balance_var = tk.StringVar(value="₱0.00")

        self.setup_style()
        self.build_ui()
        self.bind_shortcuts()
        self.reset_form()
        self.refresh_table()
        self.tick_clock()

        # Keep the Cash-In / Cash-Out toggle colors in sync with the form.
        self.type_var.trace_add("write", lambda *_: self.update_type_buttons())
        self.update_type_buttons()

        # Live search: register traces only after the UI is fully built.
        self.search_var.trace_add("write", lambda *_: self.schedule_refresh())
        self.filter_date_var.trace_add("write", self.on_date_filter_change)

        self.root.protocol("WM_DELETE_WINDOW", self.root.destroy)

    # ----------------------------------------------------------------------
    # Helpers
    # ----------------------------------------------------------------------
    def get_scale(self):
        """Display scaling factor used by customtkinter (1.0 = 100%)."""
        try:
            return float(self.root._get_window_scaling())
        except Exception:
            return 1.0

    def font(self, size=13, weight="normal"):
        """A customtkinter font (used by CTk widgets)."""
        key = (size, weight)
        if key not in self._fonts:
            self._fonts[key] = ctk.CTkFont(
                family=self.font_family, size=size, weight=weight
            )
        return self._fonts[key]

    def tfont(self, size=10, weight="normal"):
        """A plain tuple font (used by the ttk table)."""
        return (self.font_family, size, weight)

    @staticmethod
    def money(value):
        value = float(value or 0)
        sign = "-" if value < 0 else ""
        return f"{sign}₱{abs(value):,.2f}"

    @staticmethod
    def make_card(parent):
        """A white rounded panel with a thin border."""
        return ctk.CTkFrame(
            parent,
            fg_color=CARD,
            corner_radius=14,
            border_width=1,
            border_color=BORDER,
        )

    def make_button(
        self, parent, text, command, kind="soft", width=90, height=34, **kwargs
    ):
        """Create a styled button. kind: primary | soft | danger | link."""
        styles = {
            "primary": dict(
                fg_color=PRIMARY,
                hover_color=PRIMARY_DARK,
                text_color="white",
                text_color_disabled="#DCE6F8",
            ),
            "soft": dict(
                fg_color=PRIMARY_SOFT,
                hover_color=PRIMARY_SOFT_HOVER,
                text_color=PRIMARY_DARK,
                text_color_disabled="#9FB0CC",
            ),
            "danger": dict(
                fg_color=CARD,
                hover_color=RED_SOFT,
                text_color=RED_DARK,
                text_color_disabled="#C3C8D4",
                border_width=1,
                border_color="#F1B9BB",
            ),
            "link": dict(
                fg_color="transparent",
                hover_color=PRIMARY_SOFT,
                text_color=PRIMARY,
                text_color_disabled="#9FB0CC",
            ),
        }
        options = dict(styles[kind])
        options.update(kwargs)
        return ctk.CTkButton(
            parent,
            text=text,
            command=command,
            width=width,
            height=height,
            corner_radius=10,
            font=self.font(13, "bold"),
            **options,
        )

    def make_entry(self, parent, variable, size=14, bold=False, **kwargs):
        """Create a rounded entry whose border turns blue when focused."""
        entry = ctk.CTkEntry(
            parent,
            textvariable=variable,
            height=36,
            corner_radius=10,
            border_width=1,
            border_color=FIELD_BORDER,
            fg_color="white",
            text_color=TEXT,
            font=self.font(size, "bold" if bold else "normal"),
            **kwargs,
        )
        entry.bind("<FocusIn>", lambda event: entry.configure(border_color=PRIMARY))
        entry.bind(
            "<FocusOut>", lambda event: entry.configure(border_color=FIELD_BORDER)
        )
        return entry

    def make_option_menu(self, parent, variable, values, command=None, width=150):
        """Create a rounded drop-down."""
        return ctk.CTkOptionMenu(
            parent,
            variable=variable,
            values=list(values),
            command=command,
            width=width,
            height=36,
            corner_radius=10,
            fg_color=PRIMARY_SOFT,
            button_color=PRIMARY,
            button_hover_color=PRIMARY_DARK,
            text_color=TEXT,
            dropdown_fg_color="white",
            dropdown_text_color=TEXT,
            dropdown_hover_color=PRIMARY_SOFT,
            font=self.font(13),
            dropdown_font=self.font(13),
            anchor="w",
        )

    # ----------------------------------------------------------------------
    # Styling (only the table still uses ttk)
    # ----------------------------------------------------------------------
    def setup_style(self):
        """Configure the ttk theme used by the records table."""
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        style.configure(
            "Treeview",
            font=self.tfont(10),
            rowheight=int(34 * self.scale),
            background="white",
            fieldbackground="white",
            foreground=TEXT,
            borderwidth=0,
        )
        style.map(
            "Treeview",
            background=[("selected", SELECT)],
            foreground=[("selected", TEXT)],
        )
        style.configure(
            "Treeview.Heading",
            font=self.tfont(9, "bold"),
            background=PRIMARY_SOFT,
            foreground=PRIMARY_DARK,
            relief="flat",
            padding=(8, 9),
            borderwidth=0,
        )
        style.map("Treeview.Heading", background=[("active", PRIMARY_SOFT_HOVER)])

    # ----------------------------------------------------------------------
    # UI construction
    # ----------------------------------------------------------------------
    def build_ui(self):
        self.build_header()
        self.build_footer()          # packed at the bottom first

        body = ctk.CTkFrame(self.root, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=14, pady=(12, 6))

        self.build_dashboard(body)
        self.build_period_panel(body)

        content = ctk.CTkFrame(body, fg_color="transparent")
        content.pack(fill="both", expand=True, pady=(10, 0))
        content.grid_columnconfigure(1, weight=1)
        content.grid_rowconfigure(0, weight=1)

        self.build_form_panel(content)
        self.build_table_panel(content)

    def build_header(self):
        header = ctk.CTkFrame(self.root, fg_color=PRIMARY, corner_radius=0)
        header.pack(fill="x")

        inner = ctk.CTkFrame(header, fg_color="transparent")
        inner.pack(fill="x", padx=18, pady=12)

        badge = self._badge(inner, "₱", "white", PRIMARY, size=42, font_size=20)
        badge.pack(side="left", padx=(0, 12))

        title_box = ctk.CTkFrame(inner, fg_color="transparent")
        title_box.pack(side="left")
        ctk.CTkLabel(
            title_box,
            text="GCash Transaction Record Manager",
            text_color="white",
            font=self.font(21, "bold"),
            anchor="w",
        ).pack(anchor="w")
        ctk.CTkLabel(
            title_box,
            text="Track cash-in, cash-out, and transfer fees",
            text_color="#CFE0FF",
            font=self.font(12),
            anchor="w",
        ).pack(anchor="w")

        self.clock_label = ctk.CTkLabel(
            inner,
            text="",
            text_color="#E1ECFF",
            font=self.font(13),
        )
        self.clock_label.pack(side="right")

        ctk.CTkFrame(self.root, fg_color=PRIMARY_DARK, height=3, corner_radius=0).pack(
            fill="x"
        )

    def build_footer(self):
        # Status bar (bottom-most)
        status = ctk.CTkFrame(self.root, fg_color="transparent")
        status.pack(side="bottom", fill="x", padx=14, pady=(2, 4))

        self.status_label = ctk.CTkLabel(
            status, text="Ready", text_color=MUTED, font=self.font(12), anchor="w"
        )
        self.status_label.pack(side="left")

        self.count_label = ctk.CTkLabel(
            status, text="", text_color=MUTED, font=self.font(12), anchor="e"
        )
        self.count_label.pack(side="right")

        # Privacy notice, directly above the status bar
        notice = ctk.CTkFrame(self.root, fg_color=AMBER_SOFT, corner_radius=0)
        notice.pack(side="bottom", fill="x")
        ctk.CTkLabel(
            notice,
            text=(
                "Privacy: never store your MPIN, OTP, password, or full "
                "account / reference numbers in this app."
            ),
            text_color=AMBER_TEXT,
            font=self.font(12),
            anchor="w",
        ).pack(side="left", padx=16, pady=5)

    def build_dashboard(self, parent):
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x")

        self.create_metric_card(
            row, 0, "Total Cash-In",
            self.cash_in_total_var, self.cash_in_count_var, GREEN,
            symbol="↑",
        )
        self.create_metric_card(
            row, 1, "Total Cash-Out",
            self.cash_out_total_var, self.cash_out_count_var, RED,
            symbol="↓",
        )
        # The balance is the main number, so it gets the solid blue card.
        self.balance_value_label = self.create_metric_card(
            row, 2, "Balance Difference",
            self.balance_var, None, PRIMARY,
            symbol="=", hero=True,
        )
        self.create_metric_card(
            row, 3, "All Transactions",
            self.total_count_var, None, "#5B6B8C",
            symbol="Σ",
        )
        self.create_metric_card(
            row, 4, "Total Transfer Fees",
            self.total_fees_var, None, AMBER_TEXT,
            symbol="₱", badge_color=AMBER,
        )

    def _badge(self, parent, symbol, color, symbol_color="white", size=36, font_size=16):
        """A small circular icon badge."""
        circle = ctk.CTkFrame(
            parent, width=size, height=size, corner_radius=size // 2, fg_color=color
        )
        circle.pack_propagate(False)
        ctk.CTkLabel(
            circle,
            text=symbol,
            text_color=symbol_color,
            fg_color="transparent",
            font=self.font(font_size, "bold"),
        ).place(relx=0.5, rely=0.5, anchor="center")
        return circle

    def create_metric_card(
        self, parent, column, title, value_var, sub_var, color,
        symbol="₱", badge_color=None, hero=False,
    ):
        """A dashboard card: icon badge on the left, label and figure on the right."""
        badge_color = badge_color or color

        card = ctk.CTkFrame(
            parent,
            corner_radius=14,
            fg_color=PRIMARY if hero else CARD,
            border_width=0 if hero else 1,
            border_color=BORDER,
        )
        card.grid(row=0, column=column, sticky="nsew", padx=(0, 10 if column < 4 else 0))
        parent.grid_columnconfigure(column, weight=1, uniform="metrics")

        body = ctk.CTkFrame(card, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=14, pady=12)

        if hero:
            badge = self._badge(body, symbol, "white", PRIMARY)
        else:
            badge = self._badge(body, symbol, badge_color)
        badge.pack(side="left", anchor="n")

        text_col = ctk.CTkFrame(body, fg_color="transparent")
        text_col.pack(side="left", padx=(12, 0), fill="x", expand=True)

        ctk.CTkLabel(
            text_col,
            text=title,
            text_color="#D6E6FF" if hero else MUTED,
            font=self.font(12, "bold"),
            anchor="w",
        ).pack(anchor="w")

        value_label = ctk.CTkLabel(
            text_col,
            textvariable=value_var,
            text_color="white" if hero else color,
            font=self.font(24, "bold"),
            anchor="w",
        )
        value_label.pack(anchor="w")

        if sub_var is not None:
            ctk.CTkLabel(
                text_col,
                textvariable=sub_var,
                text_color=MUTED,
                font=self.font(12),
                anchor="w",
            ).pack(anchor="w")
        return value_label

    # ---- Period summary panel (daily / weekly / monthly) -----------------
    def build_period_panel(self, parent):
        card = self.make_card(parent)
        card.pack(fill="x", pady=(10, 0))

        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill="both", expand=True, padx=14, pady=12)

        top = ctk.CTkFrame(inner, fg_color="transparent")
        top.pack(fill="x")

        ctk.CTkLabel(
            top, text="Period Summary", text_color=TEXT, font=self.font(18, "bold")
        ).pack(side="left")

        self.make_option_menu(
            top,
            self.period_var,
            PERIOD_CHOICES,
            command=lambda choice: self.refresh_period_summary(),
            width=110,
        ).pack(side="right")

        nav = ctk.CTkFrame(top, fg_color="transparent")
        nav.pack(side="right", padx=(0, 12))

        self.make_button(
            nav, "◀", lambda: self.shift_period(-1), "soft", width=38
        ).pack(side="left")
        ctk.CTkLabel(
            nav,
            textvariable=self.period_label_var,
            text_color=TEXT,
            font=self.font(13, "bold"),
            width=210,
            anchor="center",
        ).pack(side="left", padx=6)
        self.make_button(
            nav, "▶", lambda: self.shift_period(1), "soft", width=38
        ).pack(side="left")
        self.make_button(
            nav, "Today", self.reset_period_today, "link", width=56
        ).pack(side="left", padx=(8, 0))

        metrics = ctk.CTkFrame(inner, fg_color="transparent")
        metrics.pack(fill="x", pady=(10, 0))
        for column in range(4):
            metrics.grid_columnconfigure(column, weight=1, uniform="period_metrics")

        self._period_metric(metrics, 0, "Cash-In", self.period_cash_in_var, GREEN)
        self._period_metric(metrics, 1, "Cash-Out", self.period_cash_out_var, RED)
        self._period_metric(
            metrics, 2, "Transfer Fees", self.period_fees_var, AMBER_TEXT
        )
        self.period_balance_label = self._period_metric(
            metrics, 3, "Net Balance", self.period_balance_var, PRIMARY
        )

    def _period_metric(self, parent, column, title, value_var, color):
        box = ctk.CTkFrame(parent, fg_color=PANEL_TINT, corner_radius=10)
        box.grid(row=0, column=column, sticky="ew", padx=(0, 10) if column < 3 else 0)
        ctk.CTkLabel(
            box, text=title, text_color=MUTED, font=self.font(12, "bold"), anchor="w"
        ).pack(anchor="w", padx=14, pady=(8, 0))
        label = ctk.CTkLabel(
            box,
            textvariable=value_var,
            text_color=color,
            font=self.font(20, "bold"),
            anchor="w",
        )
        label.pack(anchor="w", padx=14, pady=(0, 8))
        return label

    def shift_period(self, direction):
        self.period_ref_date = database.shift_period(
            self.period_ref_date, self.period_var.get(), direction
        )
        self.refresh_period_summary()

    def reset_period_today(self):
        self.period_ref_date = date.today()
        self.refresh_period_summary()

    def refresh_period_summary(self):
        """Reload the daily/weekly/monthly totals card from the database."""
        try:
            totals = database.get_period_totals(
                self.period_var.get().lower(), self.period_ref_date
            )
        except Exception as exc:
            self.set_status(f"Could not load period summary: {exc}", "error")
            return

        self.period_label_var.set(totals["label"])
        self.period_cash_in_var.set(self.money(totals["total_cash_in"]))
        self.period_cash_out_var.set(self.money(totals["total_cash_out"]))
        self.period_fees_var.set(self.money(totals["total_transfer_fees"]))
        balance = totals["balance_difference"]
        self.period_balance_var.set(self.money(balance))
        self.period_balance_label.configure(
            text_color=PRIMARY if balance >= 0 else RED_DARK
        )

    # ---- Form panel ------------------------------------------------------
    def build_form_panel(self, parent):
        card = self.make_card(parent)
        card.grid(row=0, column=0, sticky="ns", padx=(0, 10))

        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill="both", expand=True, padx=14, pady=12)

        # Forces the panel to a comfortable fixed width.
        ctk.CTkFrame(inner, width=330, height=1, fg_color="transparent").pack(
            side="top"
        )

        # ---- Action area: packed FIRST at the bottom, so the buttons are
        # always visible even on a small screen.
        actions = ctk.CTkFrame(inner, fg_color="transparent")
        actions.pack(side="bottom", fill="x")

        ctk.CTkLabel(
            actions,
            textvariable=self.error_var,
            text_color=RED_DARK,
            font=self.font(12, "bold"),
            wraplength=320,
            justify="left",
            anchor="w",
        ).pack(anchor="w", pady=(6, 0))

        self.primary_btn = self.make_button(
            actions,
            "Add Transaction",
            self.submit_form,
            "primary",
            width=200,
            height=44,
        )
        self.primary_btn.configure(font=self.font(15, "bold"))
        self.primary_btn.pack(fill="x", pady=(6, 8))

        btn_row = ctk.CTkFrame(actions, fg_color="transparent")
        btn_row.pack(fill="x")
        btn_row.grid_columnconfigure(0, weight=1, uniform="btn")
        btn_row.grid_columnconfigure(1, weight=1, uniform="btn")

        self.delete_btn = self.make_button(
            btn_row, "Delete", self.delete_transaction, "danger", width=100
        )
        self.delete_btn.grid(row=0, column=0, sticky="ew", padx=(0, 4))

        self.make_button(
            btn_row, "Clear Form", self.reset_form, "soft", width=100
        ).grid(row=0, column=1, sticky="ew", padx=(4, 0))

        # ---- Mode banner: "New transaction" or "Editing transaction #12"
        self.mode_frame = ctk.CTkFrame(inner, fg_color=PRIMARY_SOFT, corner_radius=10)
        self.mode_frame.pack(side="top", fill="x")
        self.mode_label = ctk.CTkLabel(
            self.mode_frame,
            text="New transaction",
            text_color=PRIMARY_DARK,
            fg_color="transparent",
            font=self.font(13, "bold"),
            anchor="w",
        )
        self.mode_label.pack(anchor="w", padx=12, pady=6)

        # ---- Fields (two-column grid)
        fields = ctk.CTkFrame(inner, fg_color="transparent")
        fields.pack(side="top", fill="x", pady=(4, 0))
        fields.grid_columnconfigure(0, weight=1, uniform="fields")
        fields.grid_columnconfigure(1, weight=1, uniform="fields")

        left_pad = (0, 6)
        right_pad = (6, 0)

        # Transaction type: segmented toggle
        self.grid_label(fields, "Transaction type", 0, 0, columnspan=2)
        seg = ctk.CTkFrame(fields, fg_color="#E6EEFB", corner_radius=12)
        seg.grid(row=1, column=0, columnspan=2, sticky="ew")
        seg.grid_columnconfigure(0, weight=1, uniform="seg")
        seg.grid_columnconfigure(1, weight=1, uniform="seg")
        self.cash_in_btn = ctk.CTkButton(
            seg,
            text=TYPE_CASH_IN,
            command=lambda: self.type_var.set(TYPE_CASH_IN),
            height=36,
            corner_radius=10,
            font=self.font(13, "bold"),
            fg_color="transparent",
            hover_color="#D6E2F7",
            text_color=MUTED,
        )
        self.cash_in_btn.grid(row=0, column=0, sticky="ew", padx=(3, 1), pady=3)
        self.cash_out_btn = ctk.CTkButton(
            seg,
            text=TYPE_CASH_OUT,
            command=lambda: self.type_var.set(TYPE_CASH_OUT),
            height=36,
            corner_radius=10,
            font=self.font(13, "bold"),
            fg_color="transparent",
            hover_color="#D6E2F7",
            text_color=MUTED,
        )
        self.cash_out_btn.grid(row=0, column=1, sticky="ew", padx=(1, 3), pady=3)

        # Amount | Transfer fee
        self.grid_label(fields, "Amount (₱)", 2, 0, padx=left_pad)
        self.grid_label(fields, "Transfer fee (₱, optional)", 2, 1, padx=right_pad)

        vcmd_amount = (
            self.root.register(
                lambda p: re.fullmatch(r"[0-9,]*\.?[0-9]{0,2}", p) is not None
            ),
            "%P",
        )
        self.amount_entry = self.make_entry(
            fields,
            self.amount_var,
            size=17,
            bold=True,
            validate="key",
            validatecommand=vcmd_amount,
        )
        self.amount_entry.grid(row=3, column=0, sticky="ew", padx=left_pad)

        # Transfer fee (optional) — the amount GCash charges you for the
        # transfer itself, separate from the cash-in / cash-out amount.
        vcmd_fee = (
            self.root.register(
                lambda p: re.fullmatch(r"[0-9,]*\.?[0-9]{0,2}", p) is not None
            ),
            "%P",
        )
        self.fee_entry = self.make_entry(
            fields,
            self.fee_var,
            size=14,
            validate="key",
            validatecommand=vcmd_fee,
        )
        self.fee_entry.grid(row=3, column=1, sticky="ew", padx=right_pad)

        # Date | Time
        self.grid_label(fields, "Date (YYYY-MM-DD)", 4, 0, padx=left_pad)

        time_header = ctk.CTkFrame(fields, fg_color="transparent")
        time_header.grid(row=4, column=1, sticky="ew", padx=right_pad, pady=(8, 2))
        ctk.CTkLabel(
            time_header,
            text="Time (HH:MM:SS)",
            text_color=MUTED,
            font=self.font(12, "bold"),
            anchor="w",
        ).pack(side="left")
        self.make_button(
            time_header, "Use now", self.fill_current_datetime, "link",
            width=52, height=22,
        ).pack(side="right")

        self.date_entry = self.make_entry(fields, self.date_var)
        self.date_entry.grid(row=5, column=0, sticky="ew", padx=left_pad)
        self.time_entry = self.make_entry(fields, self.time_var)
        self.time_entry.grid(row=5, column=1, sticky="ew", padx=right_pad)

        # Reference
        self.grid_label(
            fields, "Reference (last 4–6 digits)", 6, 0, columnspan=2
        )
        vcmd_ref = (
            self.root.register(lambda p: re.fullmatch(r"[0-9]{0,6}", p) is not None),
            "%P",
        )
        self.reference_entry = self.make_entry(
            fields,
            self.reference_var,
            validate="key",
            validatecommand=vcmd_ref,
        )
        self.reference_entry.grid(row=7, column=0, columnspan=2, sticky="ew")

        # Notes
        self.grid_label(fields, "Notes (optional)", 8, 0, columnspan=2)
        self.notes_entry = self.make_entry(fields, self.notes_var)
        self.notes_entry.grid(row=9, column=0, columnspan=2, sticky="ew")

        # Press Enter in any field to submit
        for entry in (
            self.amount_entry,
            self.date_entry,
            self.time_entry,
            self.reference_entry,
            self.fee_entry,
            self.notes_entry,
        ):
            entry.bind("<Return>", lambda event: self.submit_form())

    def grid_label(self, parent, text, row, column, columnspan=1, padx=0):
        ctk.CTkLabel(
            parent,
            text=text,
            text_color=MUTED,
            font=self.font(12, "bold"),
            anchor="w",
        ).grid(
            row=row,
            column=column,
            columnspan=columnspan,
            sticky="w",
            padx=padx,
            pady=(8 if row else 2, 2),
        )

    def update_type_buttons(self):
        """Color the Cash-In / Cash-Out toggle to match the chosen type."""
        current = self.type_var.get()
        if current == TYPE_CASH_IN:
            self.cash_in_btn.configure(fg_color=GREEN, hover_color=GREEN_DARK, text_color="white")
            self.cash_out_btn.configure(fg_color="transparent", hover_color="#D6E2F7", text_color=MUTED)
        else:
            self.cash_out_btn.configure(fg_color=RED, hover_color=RED_DARK, text_color="white")
            self.cash_in_btn.configure(fg_color="transparent", hover_color="#D6E2F7", text_color=MUTED)

    # ---- Table panel -----------------------------------------------------
    def build_table_panel(self, parent):
        card = self.make_card(parent)
        card.grid(row=0, column=1, sticky="nsew")

        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill="both", expand=True, padx=14, pady=12)

        # Title row
        top = ctk.CTkFrame(inner, fg_color="transparent")
        top.pack(fill="x")
        ctk.CTkLabel(
            top, text="Transaction Records", text_color=TEXT, font=self.font(18, "bold")
        ).pack(side="left")
        self.make_button(top, "Refresh", self.refresh_table, "soft", width=80).pack(
            side="right"
        )
        self.make_button(
            top, "View Details", self.view_details, "soft", width=104
        ).pack(side="right", padx=(0, 6))
        self.make_button(top, "Import CSV", self.import_csv, "soft", width=96).pack(
            side="right", padx=(0, 6)
        )
        self.make_button(top, "Export CSV", self.export_csv, "soft", width=96).pack(
            side="right", padx=(0, 6)
        )

        # Search / filter row
        filters = ctk.CTkFrame(inner, fg_color="transparent")
        filters.pack(fill="x", pady=(8, 8))
        filters.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            filters,
            text="Search reference, date, type, or notes",
            text_color=MUTED,
            font=self.font(12, "bold"),
            anchor="w",
        ).grid(row=0, column=0, sticky="w", pady=(0, 3))
        ctk.CTkLabel(
            filters, text="Type", text_color=MUTED,
            font=self.font(12, "bold"), anchor="w",
        ).grid(row=0, column=1, sticky="w", pady=(0, 3), padx=(10, 0))
        ctk.CTkLabel(
            filters, text="Date (YYYY-MM-DD)", text_color=MUTED,
            font=self.font(12, "bold"), anchor="w",
        ).grid(row=0, column=2, sticky="w", pady=(0, 3), padx=(10, 0))

        self.search_entry = self.make_entry(filters, self.search_var)
        self.search_entry.grid(row=1, column=0, sticky="ew")

        type_menu = self.make_option_menu(
            filters,
            self.filter_type_var,
            ["All", TYPE_CASH_IN, TYPE_CASH_OUT],
            command=self.on_filter_type_change,
            width=190,
        )
        type_menu.grid(row=1, column=1, sticky="ew", padx=(10, 0))

        date_frame = ctk.CTkFrame(filters, fg_color="transparent")
        date_frame.grid(row=1, column=2, sticky="ew", padx=(10, 0))
        self.filter_date_entry = self.make_entry(
            date_frame, self.filter_date_var, width=120
        )
        self.filter_date_entry.pack(side="left")
        self.filter_date_entry.bind("<Return>", lambda event: self.refresh_table())
        self.make_button(
            date_frame, "Today", self.filter_today, "link", width=52
        ).pack(side="left", padx=(4, 0))

        self.make_button(
            filters, "Clear Filters", self.clear_search, "soft", width=100, height=36
        ).grid(row=1, column=3, padx=(10, 0))

        # Table
        tree_frame = ctk.CTkFrame(
            inner,
            fg_color=CARD,
            corner_radius=10,
            border_width=1,
            border_color=BORDER,
        )
        tree_frame.pack(fill="both", expand=True)
        tree_frame.grid_rowconfigure(0, weight=1)
        tree_frame.grid_columnconfigure(0, weight=1)

        self.tree = ttk.Treeview(
            tree_frame,
            columns=TABLE_COLUMNS,
            show="headings",
            selectmode="browse",
        )

        for column in TABLE_COLUMNS:
            self.tree.heading(
                column,
                text=TABLE_HEADINGS[column],
                anchor=TABLE_ANCHORS[column],
                command=lambda c=column: self.on_sort(c),
            )
            self.tree.column(
                column,
                width=int(TABLE_WIDTHS[column] * self.scale),
                minwidth=int(50 * self.scale),
                anchor=TABLE_ANCHORS[column],
                stretch=(column == "notes"),
            )

        # Cash-In rows read green, Cash-Out rows read red; alternating rows
        # get a faint tint (zebra striping) so wide rows stay easy to scan.
        self.tree.tag_configure("cashin", foreground=GREEN_DARK)
        self.tree.tag_configure("cashout", foreground=RED_DARK)
        self.tree.tag_configure("evenrow", background=CARD)
        self.tree.tag_configure("oddrow", background=CARD_ALT)

        y_scroll = ctk.CTkScrollbar(
            tree_frame,
            orientation="vertical",
            command=self.tree.yview,
            width=12,
            button_color="#BFD1F0",
            button_hover_color="#98B3E6",
        )
        x_scroll = ctk.CTkScrollbar(
            tree_frame,
            orientation="horizontal",
            command=self.tree.xview,
            height=12,
            button_color="#BFD1F0",
            button_hover_color="#98B3E6",
        )
        self.tree.configure(
            yscrollcommand=y_scroll.set, xscrollcommand=x_scroll.set
        )

        self.tree.grid(row=0, column=0, sticky="nsew", padx=(4, 0), pady=(4, 0))
        y_scroll.grid(row=0, column=1, sticky="ns", padx=(2, 3), pady=3)
        x_scroll.grid(row=1, column=0, sticky="ew", padx=4, pady=(2, 3))

        # Friendly empty state
        self.empty_label = ctk.CTkLabel(
            tree_frame,
            text="No transactions to show.\nAdd one using the form, or clear the filters.",
            text_color=MUTED,
            fg_color=CARD,
            font=self.font(14),
            justify="center",
        )

        self.tree.bind("<Double-1>", self.view_details)
        self.tree.bind("<Return>", self.view_details)
        self.tree.bind("<Delete>", lambda event: self.delete_transaction())
        self.tree.bind("<<TreeviewSelect>>", self.on_tree_select)

    def bind_shortcuts(self):
        self.root.bind("<Control-f>", self.focus_search)
        self.root.bind("<Control-n>", lambda event: self.reset_form())
        self.root.bind("<Escape>", lambda event: self.reset_form())

    # ----------------------------------------------------------------------
    # Small UI utilities
    # ----------------------------------------------------------------------
    def tick_clock(self):
        now = datetime.now()
        self.clock_label.configure(
            text=now.strftime("%A, %d %B %Y     %I:%M:%S %p")
        )
        self.root.after(1000, self.tick_clock)

    def set_status(self, text, kind="info"):
        """Show a short message in the status bar, then reset it."""
        colors = {
            "info": MUTED,
            "success": GREEN_DARK,
            "warn": AMBER_TEXT,
            "error": RED_DARK,
        }
        self.status_label.configure(text=text, text_color=colors.get(kind, MUTED))

        if self._status_job is not None:
            self.root.after_cancel(self._status_job)
        self._status_job = self.root.after(
            6000,
            lambda: self.status_label.configure(text="Ready", text_color=MUTED),
        )

    def focus_search(self, event=None):
        self.search_entry.focus_set()
        self.search_entry.select_range(0, "end")
        return "break"

    def update_mode(self):
        """Switch the form between 'add' and 'edit' appearance."""
        if self.selected_id is None:
            self.mode_frame.configure(fg_color=PRIMARY_SOFT)
            self.mode_label.configure(
                text="New transaction", text_color=PRIMARY_DARK
            )
            self.primary_btn.configure(text="Add Transaction")
            self.delete_btn.configure(state="disabled")
        else:
            self.mode_frame.configure(fg_color=AMBER_SOFT)
            self.mode_label.configure(
                text=f"Editing transaction #{self.selected_id}",
                text_color=AMBER_TEXT,
            )
            self.primary_btn.configure(text="Save Changes")
            self.delete_btn.configure(state="normal")

    def fill_current_datetime(self):
        """Fill date and time with the computer's current local date/time."""
        now = datetime.now()
        self.date_var.set(now.strftime("%Y-%m-%d"))
        self.time_var.set(now.strftime("%H:%M:%S"))

    # ----------------------------------------------------------------------
    # Form logic
    # ----------------------------------------------------------------------
    def reset_form(self):
        """Return the form to 'new transaction' mode."""
        self.selected_id = None
        self.amount_var.set("")
        self.fee_var.set("")
        self.reference_var.set("")
        self.notes_var.set("")
        self.error_var.set("")
        self.fill_current_datetime()

        for item in self.tree.selection():
            self.tree.selection_remove(item)

        self.update_mode()
        self.amount_entry.focus_set()

    def fail(self, message, widget=None):
        """Show an inline validation message and focus the bad field."""
        self.error_var.set(message)
        if widget is not None:
            widget.focus_set()
            widget.select_range(0, "end")
        return None

    def validate_form(self):
        """Validate user-entered transaction information."""
        self.error_var.set("")

        transaction_type = self.type_var.get().strip()
        amount_text = self.amount_var.get().strip().replace(",", "")
        fee_text = self.fee_var.get().strip().replace(",", "")
        date_text = self.date_var.get().strip()
        time_text = self.time_var.get().strip()
        reference = self.reference_var.get().strip()
        notes = self.notes_var.get().strip()

        if transaction_type not in TRANSACTION_TYPES:
            return self.fail("Choose Cash-In or Cash-Out / Withdrawal.")

        try:
            amount = round(float(amount_text), 2)
            if amount <= 0:
                raise ValueError
        except ValueError:
            return self.fail(
                "Enter an amount greater than zero, for example 500 or 500.50.",
                self.amount_entry,
            )

        if fee_text == "":
            transfer_fee = 0.0
        else:
            try:
                transfer_fee = round(float(fee_text), 2)
                if transfer_fee < 0:
                    raise ValueError
            except ValueError:
                return self.fail(
                    "Transfer fee must be zero or a positive amount, "
                    "for example 15 or 15.00.",
                    self.fee_entry,
                )

        if not date_text:
            return self.fail("Enter a date.", self.date_entry)
        try:
            date_text = datetime.strptime(date_text, "%Y-%m-%d").strftime("%Y-%m-%d")
        except ValueError:
            return self.fail(
                "Use the date format YYYY-MM-DD, for example 2026-09-17.",
                self.date_entry,
            )

        if not time_text:
            return self.fail("Enter a time.", self.time_entry)
        parsed_time = None
        for fmt in ("%H:%M:%S", "%H:%M"):
            try:
                parsed_time = datetime.strptime(time_text, fmt)
                break
            except ValueError:
                continue
        if parsed_time is None:
            return self.fail(
                "Use the time format HH:MM:SS, for example 23:05:30.",
                self.time_entry,
            )
        time_text = parsed_time.strftime("%H:%M:%S")

        if not re.fullmatch(r"\d{4,6}", reference):
            return self.fail(
                "Enter only the last 4–6 digits of the reference number.",
                self.reference_entry,
            )

        # Show the cleaned-up values back in the form
        self.date_var.set(date_text)
        self.time_var.set(time_text)
        self.fee_var.set(f"{transfer_fee:.2f}" if transfer_fee else "")

        return {
            "transaction_type": transaction_type,
            "amount": amount,
            "transaction_date": date_text,
            "transaction_time": time_text,
            "reference_last_digits": reference,
            "notes": notes,
            "transfer_fee": transfer_fee,
        }

    def submit_form(self):
        """Add a new transaction, or save changes to the selected one."""
        data = self.validate_form()
        if not data:
            return

        if self.selected_id is None:
            self.add_transaction(data)
        else:
            self.edit_transaction(data)

    def add_transaction(self, data):
        created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        try:
            transaction_id = database.add_transaction(
                data["transaction_type"],
                data["amount"],
                data["transaction_date"],
                data["transaction_time"],
                data["reference_last_digits"],
                data["notes"],
                created_at,
                transfer_fee=data["transfer_fee"],
            )
        except ValueError as exc:
            self.report_duplicate(exc)
            return
        except Exception as exc:
            messagebox.showerror(
                "Database Error", f"Could not save the transaction.\n\n{exc}"
            )
            return

        self.reset_form()
        self.refresh_table()
        if self.tree.exists(str(transaction_id)):
            self.tree.see(str(transaction_id))
        self.set_status(
            f"Transaction #{transaction_id} added: "
            f"{data['transaction_type']}, {self.money(data['amount'])}.",
            "success",
        )

    def edit_transaction(self, data):
        transaction_id = self.selected_id

        try:
            database.update_transaction(
                transaction_id,
                data["transaction_type"],
                data["amount"],
                data["transaction_date"],
                data["transaction_time"],
                data["reference_last_digits"],
                data["notes"],
                transfer_fee=data["transfer_fee"],
            )
        except ValueError as exc:
            self.report_duplicate(exc)
            return
        except Exception as exc:
            messagebox.showerror(
                "Database Error", f"Could not update the transaction.\n\n{exc}"
            )
            return

        self.reset_form()
        self.refresh_table()
        self.set_status(f"Transaction #{transaction_id} updated.", "success")

    def report_duplicate(self, exc):
        self.error_var.set(
            "This reference number is already recorded. "
            "Check the last 4–6 digits and try again."
        )
        messagebox.showwarning(
            "Duplicate Reference",
            f"{exc}\n\nPlease check the last 4–6 digits of the reference number.",
        )
        self.reference_entry.focus_set()

    def delete_transaction(self):
        """Delete the selected transaction after confirmation."""
        if self.selected_id is None:
            self.set_status("Select a transaction from the table first.", "warn")
            return

        transaction_id = self.selected_id
        confirm = messagebox.askyesno(
            "Delete Transaction",
            f"Delete transaction #{transaction_id}?\n\nThis cannot be undone.",
            icon="warning",
        )
        if not confirm:
            return

        try:
            database.delete_transaction(transaction_id)
        except Exception as exc:
            messagebox.showerror(
                "Database Error", f"Could not delete the transaction.\n\n{exc}"
            )
            return

        self.reset_form()
        self.refresh_table()
        self.set_status(f"Transaction #{transaction_id} deleted.", "success")

    # ----------------------------------------------------------------------
    # Search / filter
    # ----------------------------------------------------------------------
    def schedule_refresh(self):
        """Wait briefly after typing so the table isn't rebuilt on every key."""
        if self._search_job is not None:
            self.root.after_cancel(self._search_job)
        self._search_job = self.root.after(250, self.refresh_table)

    def on_date_filter_change(self, *_):
        text = self.filter_date_var.get().strip()
        if text == "" or len(text) == 10:
            self.schedule_refresh()

    def on_filter_type_change(self, choice=None):
        self.refresh_table()

    def filter_today(self):
        self.filter_date_var.set(datetime.now().strftime("%Y-%m-%d"))

    def clear_search(self):
        """Clear search and filter controls."""
        self.search_var.set("")
        self.filter_type_var.set("All")
        self.filter_date_var.set("")
        self.refresh_table()

    # ----------------------------------------------------------------------
    # CSV export / import (backups and moving data into a new install)
    # ----------------------------------------------------------------------
    def export_csv(self):
        """Save every transaction to a CSV file the user picks."""
        filepath = filedialog.asksaveasfilename(
            title="Export Transactions",
            defaultextension=".csv",
            filetypes=[("CSV file", "*.csv")],
            initialfile="gcash_transactions_export.csv",
        )
        if not filepath:
            return

        try:
            count = database.export_transactions_csv(filepath)
        except Exception as exc:
            messagebox.showerror(
                "Export Failed", f"Could not export transactions.\n\n{exc}"
            )
            return

        self.set_status(f"Exported {count} transaction(s) to {filepath}.", "success")
        messagebox.showinfo(
            "Export Complete", f"Exported {count} transaction(s) to:\n{filepath}"
        )

    def import_csv(self):
        """Import transactions from a CSV file the user picks."""
        filepath = filedialog.askopenfilename(
            title="Import Transactions",
            filetypes=[("CSV file", "*.csv")],
        )
        if not filepath:
            return

        confirm = messagebox.askyesno(
            "Import Transactions",
            "This will add every valid row from the chosen CSV file into "
            "this database. Rows whose reference number is already "
            "recorded will be skipped automatically.\n\nContinue?",
        )
        if not confirm:
            return

        try:
            imported, skipped = database.import_transactions_csv(filepath)
        except Exception as exc:
            messagebox.showerror(
                "Import Failed", f"Could not import transactions.\n\n{exc}"
            )
            return

        self.refresh_table()

        message = f"Imported {imported} transaction(s)."
        if skipped:
            message += f" Skipped {len(skipped)} row(s) (duplicates or invalid data)."
        self.set_status(message, "success" if imported else "warn")
        messagebox.showinfo("Import Complete", message)

    # ----------------------------------------------------------------------
    # Table
    # ----------------------------------------------------------------------
    def row_values(self, row):
        is_in = row["transaction_type"] == TYPE_CASH_IN
        sign = "+" if is_in else "-"
        fee = float(row["transfer_fee"] or 0)
        fee_text = f"₱{fee:,.2f}" if fee else "—"
        return (
            row["id"],
            row["transaction_type"],
            f"{sign} ₱{float(row['amount']):,.2f}",
            fee_text,
            row["transaction_date"],
            row["transaction_time"],
            row["reference_last_digits"],
            row["notes"] or "",
        )

    def refresh_table(self):
        """Reload the table and dashboard from the database."""
        if self._search_job is not None:
            self.root.after_cancel(self._search_job)
            self._search_job = None

        try:
            rows = database.search_transactions(
                search_text=self.search_var.get(),
                transaction_type=self.filter_type_var.get(),
                date_filter=self.filter_date_var.get(),
            )
        except Exception as exc:
            messagebox.showerror(
                "Database Error", f"Could not load transactions.\n\n{exc}"
            )
            return

        self.tree.delete(*self.tree.get_children())
        self.row_cache.clear()

        for row in rows:
            row = dict(row)
            iid = str(row["id"])
            self.row_cache[iid] = row
            tag = "cashin" if row["transaction_type"] == TYPE_CASH_IN else "cashout"
            self.tree.insert("", "end", iid=iid, values=self.row_values(row), tags=(tag,))
        # apply_sort() (below) also applies zebra striping to match the
        # rows' final on-screen order, whatever that order turns out to be.

        self.apply_sort()

        # Keep the edited row highlighted if it is still visible
        if self.selected_id is not None and self.tree.exists(str(self.selected_id)):
            self.tree.selection_set(str(self.selected_id))

        if rows:
            self.empty_label.place_forget()
        else:
            self.empty_label.place(relx=0.5, rely=0.42, anchor="center")
            self.empty_label.lift()

        self.update_dashboard()
        self.refresh_period_summary()
        self.count_label.configure(
            text=f"Showing {len(rows)} of {self.total_records} records"
        )

    def update_dashboard(self):
        """Update dashboard totals."""
        try:
            totals = database.get_dashboard_totals()
        except Exception as exc:
            self.set_status(f"Could not load totals: {exc}", "error")
            return

        cash_in_count = int(totals["cash_in_count"])
        cash_out_count = int(totals["cash_out_count"])
        balance = float(totals["balance_difference"])

        self.cash_in_total_var.set(self.money(totals["total_cash_in"]))
        self.cash_out_total_var.set(self.money(totals["total_cash_out"]))
        self.cash_in_count_var.set(self.plural(cash_in_count, "transaction"))
        self.cash_out_count_var.set(self.plural(cash_out_count, "transaction"))
        self.balance_var.set(self.money(balance))
        # The balance card sits on solid blue, so use white / a light red.
        self.balance_value_label.configure(
            text_color="white" if balance >= 0 else "#FFC9CC"
        )

        self.total_records = cash_in_count + cash_out_count
        self.total_count_var.set(str(self.total_records))
        self.total_fees_var.set(self.money(totals.get("total_transfer_fees", 0)))

    @staticmethod
    def plural(count, word):
        return f"{count} {word}" + ("" if count == 1 else "s")

    # ---- Sorting ---------------------------------------------------------
    def sort_value(self, column, iid):
        row = self.row_cache[iid]
        if column == "id":
            return int(row["id"])
        if column == "type":
            return row["transaction_type"].lower()
        if column == "amount":
            return float(row["amount"])
        if column == "date":
            return (row["transaction_date"], row["transaction_time"])
        if column == "time":
            return row["transaction_time"]
        if column == "reference":
            return row["reference_last_digits"]
        return (row["notes"] or "").lower()

    def on_sort(self, column):
        """Click a heading to sort; click again to reverse."""
        if self.sort_state and self.sort_state[0] == column:
            reverse = not self.sort_state[1]
        else:
            reverse = False
        self.sort_state = (column, reverse)
        self.apply_sort()

    def apply_sort(self):
        if self.sort_state:
            column, reverse = self.sort_state
            items = list(self.tree.get_children(""))
            items.sort(key=lambda iid: self.sort_value(column, iid), reverse=reverse)
            for index, iid in enumerate(items):
                self.tree.move(iid, "", index)
        self.restripe_rows()
        self.update_headings()

    def restripe_rows(self):
        """Reapply zebra striping based on the current on-screen row order."""
        for index, iid in enumerate(self.tree.get_children("")):
            current_tags = list(self.tree.item(iid, "tags"))
            type_tag = "cashin" if "cashin" in current_tags else "cashout"
            zebra_tag = "evenrow" if index % 2 == 0 else "oddrow"
            self.tree.item(iid, tags=(type_tag, zebra_tag))

    def update_headings(self):
        for column in TABLE_COLUMNS:
            text = TABLE_HEADINGS[column]
            if self.sort_state and self.sort_state[0] == column:
                text += "  ▼" if self.sort_state[1] else "  ▲"
            self.tree.heading(column, text=text)

    # ---- Selection and details ------------------------------------------
    def on_tree_select(self, event=None):
        """Load the selected row into the form for editing."""
        selection = self.tree.selection()
        if not selection:
            return

        transaction_id = int(selection[0])
        if transaction_id == self.selected_id:
            return

        try:
            row = database.get_transaction(transaction_id)
        except Exception as exc:
            self.set_status(f"Could not load transaction: {exc}", "error")
            return
        if row is None:
            return

        self.selected_id = transaction_id
        self.type_var.set(row["transaction_type"])
        self.amount_var.set(f"{float(row['amount']):.2f}")
        fee = float(row["transfer_fee"] or 0)
        self.fee_var.set(f"{fee:.2f}" if fee else "")
        self.date_var.set(row["transaction_date"])
        self.time_var.set(row["transaction_time"])
        self.reference_var.set(row["reference_last_digits"])
        self.notes_var.set(row["notes"] or "")
        self.error_var.set("")
        self.update_mode()

    def view_details(self, event=None):
        """Show a details window for the selected transaction."""
        selection = self.tree.selection()
        if not selection:
            messagebox.showwarning(
                "No Selection", "Please select a transaction first."
            )
            return

        try:
            row = database.get_transaction(int(selection[0]))
        except Exception as exc:
            messagebox.showerror("Database Error", f"Could not load details.\n\n{exc}")
            return
        if row is None:
            messagebox.showerror(
                "Not Found", "The selected transaction could not be found."
            )
            return

        is_in = row["transaction_type"] == TYPE_CASH_IN
        accent = GREEN if is_in else RED

        win = tk.Toplevel(self.root)
        win.title(f"Transaction #{row['id']}")
        win.configure(bg=CARD)
        win.resizable(False, False)
        win.transient(self.root)

        top = ctk.CTkFrame(win, fg_color=accent, corner_radius=0)
        top.pack(fill="x")
        ctk.CTkLabel(
            top,
            text=row["transaction_type"],
            text_color="white",
            font=self.font(13, "bold"),
            anchor="w",
        ).pack(anchor="w", padx=22, pady=(16, 0))
        ctk.CTkLabel(
            top,
            text=self.money(row["amount"]),
            text_color="white",
            font=self.font(34, "bold"),
            anchor="w",
        ).pack(anchor="w", padx=22, pady=(0, 16))

        body = ctk.CTkFrame(win, fg_color=CARD, corner_radius=0)
        body.pack(fill="both", expand=True, padx=22, pady=(14, 6))
        body.grid_columnconfigure(1, weight=1, minsize=260)

        fee = float(row["transfer_fee"] or 0)
        details = [
            ("Transaction ID", f"#{row['id']}"),
            ("Transfer Fee", self.money(fee) if fee else "(None)"),
            ("Date", row["transaction_date"]),
            ("Time", row["transaction_time"]),
            ("Reference", row["reference_last_digits"]),
            ("Notes", row["notes"] or "(None)"),
            ("Recorded on", row["created_at"]),
        ]
        for index, (label, value) in enumerate(details):
            ctk.CTkLabel(
                body, text=label, text_color=MUTED,
                font=self.font(12), anchor="w",
            ).grid(row=index, column=0, sticky="nw", pady=5, padx=(0, 18))
            ctk.CTkLabel(
                body, text=value, text_color=TEXT,
                font=self.font(13, "bold"), anchor="w",
                justify="left", wraplength=280,
            ).grid(row=index, column=1, sticky="nw", pady=5)

        self.make_button(
            win, "Close", win.destroy, "primary", width=96, height=36
        ).pack(anchor="e", padx=22, pady=(4, 18))
        win.bind("<Escape>", lambda event: win.destroy())

        # Center over the main window
        win.update_idletasks()
        x = self.root.winfo_x() + (self.root.winfo_width() - win.winfo_width()) // 2
        y = self.root.winfo_y() + (self.root.winfo_height() - win.winfo_height()) // 2
        win.geometry(f"+{max(x, 0)}+{max(y, 0)}")

        try:
            win.grab_set()
        except tk.TclError:
            pass
        win.focus_set()