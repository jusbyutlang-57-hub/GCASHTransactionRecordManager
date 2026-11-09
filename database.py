import calendar
import csv
import sqlite3
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional, List, Tuple

# Store the database beside the real, running program.
#
# When this app is packaged with PyInstaller, Path(__file__) no longer
# points next to the .exe -- it points inside PyInstaller's bundled/
# extracted files instead. For a --onefile build that location is a
# temporary folder that gets deleted as soon as the app closes, which
# would silently wipe out the database every time. sys.frozen is set by
# PyInstaller at runtime, so we use sys.executable's folder in that case,
# and __file__'s folder otherwise (e.g. when running "python main.py").
if getattr(sys, "frozen", False):
    BASE_DIR = Path(sys.executable).resolve().parent
else:
    BASE_DIR = Path(__file__).resolve().parent

DB_PATH = BASE_DIR / "gcash_records.db"

#connection to local sqlite database
def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

#check if a column already exists on a table
def _column_exists(conn, table, column):
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return any(r["name"] == column for r in rows)

#CREATES THE TRANSACTIONS TABLE AND ENFORE UNIQUE REF. DIGITS TO ENSURE SECURITY
def initialize_database():
    with get_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                transaction_type TEXT NOT NULL,
                amount REAL NOT NULL CHECK(amount > 0),
                transaction_date TEXT NOT NULL,
                transaction_time TEXT NOT NULL,
                reference_last_digits TEXT NOT NULL,
                notes TEXT DEFAULT '',
                created_at TEXT NOT NULL
            )
            """
        )

        # --- Migration: add transfer_fee to databases created before this
        # feature existed. Existing rows default to 0.00, so nothing is
        # lost and old records simply show no fee.
        if not _column_exists(conn, "transactions", "transfer_fee"):
            conn.execute(
                """
                ALTER TABLE transactions
                ADD COLUMN transfer_fee REAL NOT NULL DEFAULT 0
                """
            )

        # The same last reference digits cannot be used twice,
        # whether the transaction is Cash-In or Cash-Out / Withdrawal.
        # Protect the reference digits at the database level when possible.
        # If an older database already contains duplicates, keep the app
        # usable and let add/update validation handle future entries.
        try:
            conn.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS
                idx_unique_reference_last_digits
                ON transactions(reference_last_digits)
                """
            )
        except sqlite3.IntegrityError:
            pass

        conn.commit()


def _reference_exists(conn, reference_last_digits, exclude_id=None):
    """Check whether the reference digits are already used."""
    if exclude_id is None:
        row = conn.execute(
            """
            SELECT id
            FROM transactions
            WHERE reference_last_digits = ?
            LIMIT 1
            """,
            (reference_last_digits,),
        ).fetchone()
    else:
        row = conn.execute(
            """
            SELECT id
            FROM transactions
            WHERE reference_last_digits = ?
              AND id != ?
            LIMIT 1
            """,
            (reference_last_digits, exclude_id),
        ).fetchone()

    return row is not None


def add_transaction(transaction_type, amount, transaction_date,
                    transaction_time, reference_last_digits, notes, created_at,
                    transfer_fee=0.0):
    """Insert a new transaction and return its generated ID."""
    with get_connection() as conn:
        if _reference_exists(conn, reference_last_digits):
            raise ValueError(
                "⚠️🚨⚠️🚨The last reference digits are already used by another "
                "transaction. Please enter the correct reference digits⚠️🚨⚠️🚨"
                "THIS MEANS THAT SOMEBODY ALREADY CLAIMED THIS REFERENE NUMBER"
            )

        try:
            cursor = conn.execute(
                """
                INSERT INTO transactions
                (transaction_type, amount, transaction_date, transaction_time,
                 reference_last_digits, notes, created_at, transfer_fee)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    transaction_type,
                    amount,
                    transaction_date,
                    transaction_time,
                    reference_last_digits,
                    notes,
                    created_at,
                    transfer_fee,
                ),
            )
            conn.commit()
            return cursor.lastrowid

        except sqlite3.IntegrityError as e:
            if "reference_last_digits" in str(e):
                raise ValueError(
                    "🚨🚨⚠️⚠️The Last REFERENCE DIGITS are already used by another "
                    "transaction. DUPLICATE REFERENCE ARE NOT ALLOWED⚠️⚠️🚨🚨"
                )
            raise


def update_transaction(transaction_id, transaction_type, amount,
                       transaction_date, transaction_time,
                       reference_last_digits, notes, transfer_fee=0.0):
    """Update an existing transaction."""
    with get_connection() as conn:
        if _reference_exists(conn, reference_last_digits, transaction_id):
            raise ValueError(
                "🚨🚨⚠️⚠️The last reference digits are already used by another "
                "transaction. Please enter a different reference🚨🚨⚠️⚠️"
            )

        try:
            conn.execute(
                """
                UPDATE transactions
                SET transaction_type = ?,
                    amount = ?,
                    transaction_date = ?,
                    transaction_time = ?,
                    reference_last_digits = ?,
                    notes = ?,
                    transfer_fee = ?
                WHERE id = ?
                """,
                (
                    transaction_type,
                    amount,
                    transaction_date,
                    transaction_time,
                    reference_last_digits,
                    notes,
                    transfer_fee,
                    transaction_id,
                ),
            )
            conn.commit()

        except sqlite3.IntegrityError as e:
            if "reference_last_digits" in str(e):
                raise ValueError(
                    "🚨🚨⚠️⚠️The last REFERENCE DIGITS are already used by another "
                    "transaction. DUPLICATE REFERENCE DIGITS are not allowed🚨🚨⚠️⚠️"
                )
            raise


def delete_transaction(transaction_id):
    """Delete one transaction by ID."""
    with get_connection() as conn:
        conn.execute(
            "DELETE FROM transactions WHERE id = ?",
            (transaction_id,),
        )
        conn.commit()


def get_transaction(transaction_id):
    """Return one transaction by ID."""
    with get_connection() as conn:
        return conn.execute(
            "SELECT * FROM transactions WHERE id = ?",
            (transaction_id,),
        ).fetchone()


def search_transactions(search_text="", transaction_type="All", date_filter=""):
    """
    Search and filter transactions.

    Search text checks reference digits, date, type, and notes.
    transaction_type can be All, Cash-In, or Cash-Out / Withdrawal.
    date_filter expects YYYY-MM-DD or blank.
    """
    conditions = []
    params = []

    if search_text.strip():
        search = f"%{search_text.strip()}%"
        conditions.append(
            """
            (
                reference_last_digits LIKE ?
                OR transaction_date LIKE ?
                OR transaction_type LIKE ?
                OR notes LIKE ?
            )
            """
        )
        params.extend([search, search, search, search])

    if transaction_type and transaction_type != "All":
        conditions.append("transaction_type = ?")
        params.append(transaction_type)

    if date_filter.strip():
        conditions.append("transaction_date = ?")
        params.append(date_filter.strip())

    where_clause = ""
    if conditions:
        where_clause = "WHERE " + " AND ".join(conditions)

    query = f"""
        SELECT id, transaction_type, amount, transaction_date,
               transaction_time, reference_last_digits, notes, created_at,
               transfer_fee
        FROM transactions
        {where_clause}
        ORDER BY transaction_date DESC, transaction_time DESC, id DESC
    """

    with get_connection() as conn:
        return conn.execute(query, params).fetchall()


def get_dashboard_totals():
    """Return totals and counts for all transactions."""
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT
                COALESCE(SUM(CASE
                    WHEN transaction_type = 'Cash-In' THEN amount
                    ELSE 0
                END), 0) AS total_cash_in,

                COALESCE(SUM(CASE
                    WHEN transaction_type = 'Cash-Out / Withdrawal' THEN amount
                    ELSE 0
                END), 0) AS total_cash_out,

                SUM(CASE
                    WHEN transaction_type = 'Cash-In' THEN 1
                    ELSE 0
                END) AS cash_in_count,

                SUM(CASE
                    WHEN transaction_type = 'Cash-Out / Withdrawal' THEN 1
                    ELSE 0
                END) AS cash_out_count,

                COALESCE(SUM(transfer_fee), 0) AS total_transfer_fees

            FROM transactions
            """
        ).fetchone()

    total_cash_in = float(row["total_cash_in"] or 0)
    total_cash_out = float(row["total_cash_out"] or 0)
    cash_in_count = int(row["cash_in_count"] or 0)
    cash_out_count = int(row["cash_out_count"] or 0)
    total_transfer_fees = float(row["total_transfer_fees"] or 0)

    return {
        "total_cash_in": total_cash_in,
        "total_cash_out": total_cash_out,
        "cash_in_count": cash_in_count,
        "cash_out_count": cash_out_count,
        "balance_difference": total_cash_in - total_cash_out,
        "total_transfer_fees": total_transfer_fees,
    }


# --------------------------------------------------------------------------
# Daily / weekly / monthly period tracking
# --------------------------------------------------------------------------
def _as_date(value):
    """Accept a date object or a 'YYYY-MM-DD' string and return a date."""
    if isinstance(value, str):
        return datetime.strptime(value, "%Y-%m-%d").date()
    return value

def _period_range(period, reference_date=None):
    """
    Return (start_date, end_date, label) for the period ('daily', 'weekly',
    or 'monthly') that contains reference_date (defaults to today).
    start_date / end_date are 'YYYY-MM-DD' strings; label is for display.
    """
    ref = _as_date(reference_date) if reference_date else date.today()

    if period == "daily":
        start = end = ref
        label = start.strftime("%A, %d %B %Y")
    elif period == "weekly":
        start = ref - timedelta(days=ref.weekday())  # Monday
        end = start + timedelta(days=6)               # Sunday
        label = f"{start.strftime('%d %b')} – {end.strftime('%d %b %Y')}"
    elif period == "monthly":
        start = ref.replace(day=1)
        last_day = calendar.monthrange(start.year, start.month)[1]
        end = start.replace(day=last_day)
        label = start.strftime("%B %Y")
    else:
        raise ValueError(f"Unknown period: {period!r}")

    return start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d"), label


def shift_period(reference_date, period, direction):
    """
    Move reference_date forward (direction=1) or backward (direction=-1)
    by one period unit. Returns a date object.
    """
    ref = _as_date(reference_date)

    if period == "Daily":
        return ref + timedelta(days=direction)
    if period == "Weekly":
        return ref + timedelta(weeks=direction)
    if period == "Monthly":
        month_index = ref.month - 1 + direction
        year = ref.year + month_index // 12
        month = month_index % 12 + 1
        day = min(ref.day, calendar.monthrange(year, month)[1])
        return ref.replace(year=year, month=month, day=day)
    raise ValueError(f"Unknown period: {period!r}")


def get_period_totals(period="Daily", reference_date=None):
    """
    Return cash-in / cash-out / transfer-fee totals for a single daily,
    weekly, or monthly period containing reference_date (default: today).
    Shape matches get_dashboard_totals(), plus start_date/end_date/label.
    """
    start_date, end_date, label = _period_range(period, reference_date)

    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT
                COALESCE(SUM(CASE
                    WHEN transaction_type = 'Cash-In' THEN amount
                    ELSE 0
                END), 0) AS total_cash_in,

                COALESCE(SUM(CASE
                    WHEN transaction_type = 'Cash-Out / Withdrawal' THEN amount
                    ELSE 0
                END), 0) AS total_cash_out,

                SUM(CASE
                    WHEN transaction_type = 'Cash-In' THEN 1
                    ELSE 0
                END) AS cash_in_count,

                SUM(CASE
                    WHEN transaction_type = 'Cash-Out / Withdrawal' THEN 1
                    ELSE 0
                END) AS cash_out_count,

                COALESCE(SUM(transfer_fee), 0) AS total_transfer_fees

            FROM transactions
            WHERE transaction_date BETWEEN ? AND ?
            """,
            (start_date, end_date),
        ).fetchone()

    total_cash_in = float(row["total_cash_in"] or 0)
    total_cash_out = float(row["total_cash_out"] or 0)

    return {
        "period": period,
        "start_date": start_date,
        "end_date": end_date,
        "label": label,
        "total_cash_in": total_cash_in,
        "total_cash_out": total_cash_out,
        "cash_in_count": int(row["cash_in_count"] or 0),
        "cash_out_count": int(row["cash_out_count"] or 0),
        "balance_difference": total_cash_in - total_cash_out,
        "total_transfer_fees": float(row["total_transfer_fees"] or 0),
    }


# --------------------------------------------------------------------------
# CSV export / import (for backups and moving data into a new install)
# --------------------------------------------------------------------------
CSV_FIELDS = [
    "id", "transaction_type", "amount", "transaction_date", "transaction_time",
    "reference_last_digits", "notes", "created_at", "transfer_fee",
]


def export_transactions_csv(filepath):
    """Write every transaction to a CSV file. Returns the number of rows written."""
    with get_connection() as conn:
        rows = conn.execute("SELECT * FROM transactions ORDER BY id").fetchall()

    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row[field] for field in CSV_FIELDS})

    return len(rows)


def import_transactions_csv(filepath):
    """
    Import transactions from a CSV file produced by export_transactions_csv
    (or any CSV with matching column headers).

    Rows whose reference_last_digits already exist in this database are
    skipped instead of raising an error, so re-running an import is safe.

    Returns (imported_count, skipped_rows), where skipped_rows is a list of
    (row_number, reason) tuples. row_number counts the header as row 1.
    """
    imported = 0
    skipped = []

    with open(filepath, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        required = (
            "transaction_type", "amount", "transaction_date",
            "transaction_time", "reference_last_digits",
        )
        missing = [c for c in required if c not in (reader.fieldnames or [])]
        if missing:
            raise ValueError(
                f"CSV is missing required column(s): {', '.join(missing)}"
            )

        for row_number, row in enumerate(reader, start=2):
            reference = (row.get("reference_last_digits") or "").strip()
            transaction_type = (row.get("transaction_type") or "").strip()

            if not reference or transaction_type not in (
                "Cash-In", "Cash-Out / Withdrawal"
            ):
                skipped.append((row_number, "Missing or invalid required field."))
                continue

            try:
                amount = float(row.get("amount") or 0)
            except ValueError:
                skipped.append((row_number, "Invalid amount."))
                continue

            try:
                transfer_fee = float(row.get("transfer_fee") or 0)
            except ValueError:
                transfer_fee = 0.0

            created_at = row.get("created_at") or datetime.now().strftime(
                "%Y-%m-%d %H:%M:%S"
            )

            try:
                add_transaction(
                    transaction_type,
                    amount,
                    row.get("transaction_date", ""),
                    row.get("transaction_time", ""),
                    reference,
                    row.get("notes", ""),
                    created_at,
                    transfer_fee=transfer_fee,
                )
                imported += 1
            except ValueError:
                skipped.append((row_number, "Duplicate reference number."))
            except Exception as exc:
                skipped.append((row_number, str(exc)))

    return imported, skipped