"""
app.py - FinanceDB web server (Python standard library only).

Run:  python app.py      then open http://localhost:8000

Routes
  GET  /                      dashboard showing a record count for every table
  GET  /<entity>              list all records + "add new" form
  GET  /<entity>/edit?pk=..   edit form for one record
  POST /<entity>/create       INSERT
  POST /<entity>/update       UPDATE
  POST /<entity>/delete       DELETE
  GET  /reports?r=<name>      read-only reports (some take your input, e.g. a date range)

Every query runs through mysql.exe using subprocess.
"""
import os
import html
import subprocess
from datetime import date
from decimal import Decimal, InvalidOperation
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse, urlencode

import templates as T

# Load local .env file if present (without external packages)
_env_file = os.path.join(os.path.dirname(__file__), ".env")
if os.path.exists(_env_file):
    with open(_env_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

MYSQL_PATH = os.environ.get("MYSQL_PATH", r"C:\Program Files\MySQL\MySQL Server 8.0\bin\mysql.exe")
DB_PASS = os.environ.get("DB_PASS", "")
DB_NAME = os.environ.get("DB_NAME", "Financedb")
HOST, PORT = "localhost", 8000


# ==========================================================================
# Database access
# ==========================================================================
class DBError(Exception):
    pass


FRIENDLY_ERRORS = {
    "1062": "Duplicate value: a record with this unique value already exists.",
    "1451": "Cannot delete/update: other records still depend on this one.",
    "1452": "Invalid reference: the selected related record does not exist.",
    "3819": "A CHECK constraint was violated (e.g. negative amount).",
    "1146": "Table not found - did you run setup_db.py?",
    "1049": f"Database '{DB_NAME}' not found - did you run setup_db.py?",
    "1045": "MySQL access denied - check DB_PASS in app.py.",
}


def _unescape_batch(value):
    """Undo the escaping that mysql -B applies (\\t, \\n, \\\\)."""
    if "\\" not in value:
        return value
    out, i = [], 0
    while i < len(value):
        ch = value[i]
        if ch == "\\" and i + 1 < len(value):
            nxt = value[i + 1]
            out.append({"t": "\t", "n": "\n", "0": "\0", "\\": "\\"}.get(nxt, nxt))
            i += 2
        else:
            out.append(ch)
            i += 1
    return "".join(out)


def run_sql(sql, fetch=False):
    """Run SQL through mysql.exe. With fetch=True, returns rows as lists (NULL -> None)."""
    flags = "-N -B " if fetch else ""
    cmd = f'"{MYSQL_PATH}" -u root -p"{DB_PASS}" {flags}-e "USE {DB_NAME}; {sql}"'
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True,
                            encoding="utf-8", errors="replace")
    errors = [line for line in result.stderr.splitlines()
              if line.strip() and "Using a password" not in line]
    if result.returncode != 0:
        raw = " ".join(errors) or "Unknown MySQL error."
        for code, friendly in FRIENDLY_ERRORS.items():
            if f"ERROR {code}" in raw:
                raw = f"{friendly} ({raw})"
                break
        raise DBError(raw)
    if not fetch:
        return []
    return [[None if v == "NULL" else _unescape_batch(v) for v in line.split("\t")]
            for line in result.stdout.splitlines()]


def sql_str(value):
    """Turn user text into a safe SQL string literal for the command line.
    Double quotes and newlines are removed (they would break the shell command);
    backslashes and single quotes are escaped for MySQL."""
    value = value.replace('"', "").replace("\r", " ").replace("\n", " ")
    value = value.replace("\\", "\\\\").replace("'", "''")
    return f"'{value}'"


def esc(value):
    return html.escape("" if value is None else str(value), quote=True)


# ==========================================================================
# Entity configuration (one entry per table in the ER diagram)
# ==========================================================================
def F(name, label, kind="text", required=True, **opts):
    """Describe a form field. kind: text | int | decimal | date | choice | fk"""
    return dict(name=name, label=label, kind=kind, required=required, **opts)


# Dropdown options for foreign-key fields: each query returns (id, display text).
FK_SOURCES = {
    "household": "SELECT household_Id, name FROM household ORDER BY name",
    "company": "SELECT Company_Id, name FROM company ORDER BY name",
    "user": "SELECT user_Id, CONCAT(name, ' (#', user_Id, ')') FROM `user` ORDER BY name",
    "share": ("SELECT s.share_Id, CONCAT(c.name, ' - Share #', s.share_Id, ' @ ', s.mkt_price) "
              "FROM shares s JOIN company c ON c.Company_Id = s.Company_Id ORDER BY c.name, s.share_Id"),
    "bank": "SELECT Bank_Id, CONCAT(Name, ' (', Branch_Code, ')') FROM bank ORDER BY Name",
    "account": ("SELECT a.Acc_Id, CONCAT('#', a.Acc_Id, ' ', a.Account_type, ' - ', "
                "COALESCE(u.name, c.name, 'N/A')) FROM account a "
                "LEFT JOIN `user` u ON u.user_Id = a.user_Id "
                "LEFT JOIN company c ON c.Company_Id = a.Company_Id ORDER BY a.Acc_Id"),
    "category": "SELECT category_Id, name FROM category ORDER BY name",
}

ACCOUNT_TYPES = ["Savings", "Current", "Salary", "Fixed Deposit", "Business"]
BILL_CYCLES = ["Weekly", "Monthly", "Quarterly", "Yearly"]
TXN_TYPES = ["Credit", "Debit"]


def validate_account(values):
    has_user = values["user_Id"] != "NULL"
    has_company = values["Company_Id"] != "NULL"
    if has_user == has_company:
        raise ValueError("An account must belong to exactly one owner: pick a User OR a Company.")


ENTITIES = {
    # ---------------- People ----------------
    "household": dict(
        group="People", title="Households", singular="Household", table="household",
        pk=["household_Id"], auto_pk=True, editable=True,
        fields=[F("name", "Household Name", maxlength=100)],
        headers=["ID", "Name", "Members"],
        list_sql=("SELECT h.household_Id, h.name, COUNT(u.user_Id) FROM household h "
                  "LEFT JOIN `user` u ON u.household_Id = h.household_Id "
                  "GROUP BY h.household_Id, h.name ORDER BY h.household_Id"),
    ),
    "user": dict(
        group="People", title="Users", singular="User", table="user",
        pk=["user_Id"], auto_pk=True, editable=True,
        fields=[
            F("name", "Full Name", maxlength=100),
            F("DOB", "Date of Birth", "date", not_future=True, hint="Age is calculated automatically."),
            F("household_Id", "Household (lives in)", "fk", required=False, ref="household"),
            F("Company_Id", "Employer (employed by)", "fk", required=False, ref="company"),
        ],
        headers=["ID", "Name", "DOB", "Age", "Household", "Employer"],
        list_sql=("SELECT user_Id, name, DOB, age, household_name, company_name "
                  "FROM user_details ORDER BY user_Id"),
    ),
    # ---------------- Market ----------------
    "company": dict(
        group="Market", title="Companies", singular="Company", table="company",
        pk=["Company_Id"], auto_pk=True, editable=True,
        fields=[
            F("name", "Company Name", maxlength=100),
            F("industry", "Industry", required=False, maxlength=100),
        ],
        headers=["ID", "Name", "Industry", "Employees", "Listed Shares"],
        list_sql=("SELECT c.Company_Id, c.name, c.industry, "
                  "(SELECT COUNT(*) FROM `user` u WHERE u.Company_Id = c.Company_Id), "
                  "(SELECT COUNT(*) FROM shares s WHERE s.Company_Id = c.Company_Id) "
                  "FROM company c ORDER BY c.Company_Id"),
    ),
    "shares": dict(
        group="Market", title="Shares", singular="Share", table="shares",
        pk=["share_Id"], auto_pk=True, editable=True,
        fields=[
            F("Company_Id", "Listed by Company", "fk", ref="company"),
            F("mkt_price", "Market Price", "decimal", min="0"),
        ],
        headers=["Share ID", "Company", "Market Price", "Owners"],
        list_sql=("SELECT s.share_Id, c.name, s.mkt_price, "
                  "(SELECT COUNT(*) FROM owns o WHERE o.share_Id = s.share_Id) "
                  "FROM shares s JOIN company c ON c.Company_Id = s.Company_Id ORDER BY s.share_Id"),
    ),
    "owns": dict(
        group="Market", title="Share Ownership", singular="Ownership", table="owns",
        pk=["user_Id", "share_Id"], auto_pk=False, editable=False,   # junction table: create/delete only
        fields=[
            F("user_Id", "User", "fk", ref="user"),
            F("share_Id", "Share", "fk", ref="share"),
        ],
        headers=["User ID", "Share ID", "User", "Company", "Market Price"],
        list_sql=("SELECT o.user_Id, o.share_Id, u.name, c.name, s.mkt_price FROM owns o "
                  "JOIN `user` u ON u.user_Id = o.user_Id "
                  "JOIN shares s ON s.share_Id = o.share_Id "
                  "JOIN company c ON c.Company_Id = s.Company_Id ORDER BY o.user_Id, o.share_Id"),
    ),
    # ---------------- Banking ----------------
    "bank": dict(
        group="Banking", title="Banks", singular="Bank", table="bank",
        pk=["Bank_Id"], auto_pk=True, editable=True,
        fields=[
            F("Name", "Bank Name", maxlength=100),
            F("Branch_Code", "Branch Code", maxlength=20),
        ],
        headers=["ID", "Name", "Branch Code", "Accounts"],
        list_sql=("SELECT b.Bank_Id, b.Name, b.Branch_Code, "
                  "(SELECT COUNT(*) FROM account a WHERE a.Bank_Id = b.Bank_Id) "
                  "FROM bank b ORDER BY b.Bank_Id"),
    ),
    "account": dict(
        group="Banking", title="Accounts", singular="Account", table="account",
        pk=["Acc_Id"], auto_pk=True, editable=True, validate=validate_account,
        fields=[
            F("Account_type", "Account Type", "choice", choices=ACCOUNT_TYPES),
            F("balance", "Balance", "decimal"),
            F("user_Id", "Owner: User", "fk", required=False, ref="user",
              hint="Choose either a User or a Company."),
            F("Company_Id", "Owner: Company", "fk", required=False, ref="company",
              hint="A company can have only one account (1:1)."),
            F("Bank_Id", "Managed by Bank", "fk", ref="bank"),
        ],
        headers=["Acc ID", "Type", "Balance", "Owner", "Owner Type", "Bank"],
        list_sql=("SELECT a.Acc_Id, a.Account_type, a.balance, COALESCE(u.name, c.name), "
                  "CASE WHEN a.user_Id IS NOT NULL THEN 'User' ELSE 'Company' END, "
                  "CONCAT(b.Name, ' (', b.Branch_Code, ')') FROM account a "
                  "LEFT JOIN `user` u ON u.user_Id = a.user_Id "
                  "LEFT JOIN company c ON c.Company_Id = a.Company_Id "
                  "JOIN bank b ON b.Bank_Id = a.Bank_Id ORDER BY a.Acc_Id"),
    ),
    "subscription": dict(
        group="Banking", title="Subscriptions", singular="Subscription", table="subscription",
        pk=["Sub_Id"], auto_pk=True, editable=True,
        fields=[
            F("Name", "Service Name", maxlength=100),
            F("Amount", "Amount", "decimal", min="0"),
            F("Bill_Cycle", "Billing Cycle", "choice", choices=BILL_CYCLES),
            F("Acc_Id", "Billed to Account", "fk", ref="account"),
        ],
        headers=["Sub ID", "Name", "Amount", "Bill Cycle", "Billed To"],
        list_sql=("SELECT s.Sub_Id, s.Name, s.Amount, s.Bill_Cycle, "
                  "CONCAT('#', a.Acc_Id, ' ', a.Account_type) FROM subscription s "
                  "JOIN account a ON a.Acc_Id = s.Acc_Id ORDER BY s.Sub_Id"),
    ),
    # ---------------- Money ----------------
    "category": dict(
        group="Money", title="Categories", singular="Category", table="category",
        pk=["category_Id"], auto_pk=True, editable=True,
        fields=[F("name", "Category Name", maxlength=50)],
        headers=["ID", "Name", "Transactions", "Goals"],
        list_sql=("SELECT c.category_Id, c.name, "
                  "(SELECT COUNT(*) FROM `transaction` t WHERE t.category_Id = c.category_Id), "
                  "(SELECT COUNT(*) FROM goal g WHERE g.category_Id = c.category_Id) "
                  "FROM category c ORDER BY c.category_Id"),
    ),
    "transaction": dict(
        group="Money", title="Transactions", singular="Transaction", table="transaction",
        pk=["transaction_Id"], auto_pk=True, editable=True,
        fields=[
            F("Date", "Date", "date"),
            F("type", "Type", "choice", choices=TXN_TYPES),
            F("amount", "Amount", "decimal", min="0.01"),
            F("Acc_Id", "Records to Account", "fk", ref="account"),
            F("category_Id", "Category", "fk", required=False, ref="category"),
        ],
        headers=["Txn ID", "Date", "Type", "Amount", "Account", "Category"],
        list_sql=("SELECT t.transaction_Id, t.`Date`, t.`type`, t.amount, "
                  "CONCAT('#', a.Acc_Id, ' ', a.Account_type), c.name FROM `transaction` t "
                  "JOIN account a ON a.Acc_Id = t.Acc_Id "
                  "LEFT JOIN category c ON c.category_Id = t.category_Id "
                  "ORDER BY t.`Date` DESC, t.transaction_Id DESC"),
    ),
    "goal": dict(
        group="Money", title="Savings Goals", singular="Goal", table="goal",
        pk=["Goal_Id"], auto_pk=True, editable=True,
        fields=[
            F("target_amt", "Target Amount", "decimal", min="0.01"),
            F("current_amt", "Current Amount", "decimal", min="0"),
            F("Acc_Id", "Saving for Account", "fk", ref="account"),
            F("category_Id", "Category", "fk", required=False, ref="category"),
        ],
        headers=["Goal ID", "Account", "Category", "Current", "Target", "Progress (%)"],
        list_sql=("SELECT g.Goal_Id, CONCAT('#', a.Acc_Id, ' ', a.Account_type), c.name, "
                  "g.current_amt, g.target_amt, ROUND(g.current_amt / g.target_amt * 100, 1) "
                  "FROM goal g JOIN account a ON a.Acc_Id = g.Acc_Id "
                  "LEFT JOIN category c ON c.category_Id = g.category_Id ORDER BY g.Goal_Id"),
    ),
}


# ==========================================================================
# Reports (read-only queries; some take custom input)
# ==========================================================================
def _date_filter(column, p):
    parts = []
    if p.get("from", "NULL") != "NULL":
        parts.append(f"{column} >= {p['from']}")
    if p.get("to", "NULL") != "NULL":
        parts.append(f"{column} <= {p['to']}")
    return "".join(f" AND {x}" for x in parts)


DATE_PARAMS = [F("from", "From Date", "date", required=False),
               F("to", "To Date", "date", required=False)]

REPORTS = {
    "networth": dict(
        label="Net Worth", title="User Net Worth",
        description="Bank balance total plus the market value of owned shares, for each user.",
        params=[],
        headers=["User ID", "Name", "Age", "Household", "Bank Balance", "Share Value", "Net Worth"],
        sql=lambda p: (
            "SELECT x.user_Id, x.name, x.age, x.household, x.bank_total, x.share_total, "
            "x.bank_total + x.share_total AS net FROM (SELECT d.user_Id, d.name, d.age, "
            "COALESCE(d.household_name, '-') AS household, "
            "(SELECT COALESCE(SUM(a.balance), 0) FROM account a WHERE a.user_Id = d.user_Id) AS bank_total, "
            "(SELECT COALESCE(SUM(s.mkt_price), 0) FROM owns o JOIN shares s ON s.share_Id = o.share_Id "
            "WHERE o.user_Id = d.user_Id) AS share_total FROM user_details d) x ORDER BY net DESC"),
    ),
    "household": dict(
        label="Households", title="Household Summary",
        description="Number of members and total bank balance held by each household.",
        params=[],
        headers=["Household ID", "Household", "Members", "Accounts", "Total Balance"],
        sql=lambda p: (
            "SELECT h.household_Id, h.name, COUNT(DISTINCT u.user_Id), COUNT(a.Acc_Id), "
            "COALESCE(SUM(a.balance), 0) FROM household h "
            "LEFT JOIN `user` u ON u.household_Id = h.household_Id "
            "LEFT JOIN account a ON a.user_Id = u.user_Id "
            "GROUP BY h.household_Id, h.name ORDER BY h.household_Id"),
    ),
    "spending": dict(
        label="By Category", title="Spending by Category",
        description="Debit and credit totals per category. Leave the dates empty to include every transaction.",
        params=DATE_PARAMS,
        headers=["Category", "Transactions", "Total Debit", "Total Credit"],
        sql=lambda p: (
            "SELECT COALESCE(c.name, 'Uncategorised'), COUNT(*), "
            "SUM(CASE WHEN t.`type` = 'Debit' THEN t.amount ELSE 0 END) AS debit, "
            "SUM(CASE WHEN t.`type` = 'Credit' THEN t.amount ELSE 0 END) "
            "FROM `transaction` t LEFT JOIN category c ON c.category_Id = t.category_Id "
            "WHERE 1 = 1" + _date_filter("t.`Date`", p) +
            " GROUP BY c.category_Id, c.name ORDER BY debit DESC"),
    ),
    "subscriptions": dict(
        label="Subscription Cost", title="Monthly Subscription Cost per Account",
        description="Every billing cycle converted to a monthly figure (weekly x 52 / 12, quarterly / 3, yearly / 12).",
        params=[],
        headers=["Acc ID", "Owner", "Subscriptions", "Monthly Cost", "Yearly Cost"],
        sql=lambda p: (
            "SELECT x.Acc_Id, x.owner, x.cnt, ROUND(x.monthly, 2), ROUND(x.monthly * 12, 2) FROM ("
            "SELECT a.Acc_Id, COALESCE(u.name, c.name) AS owner, COUNT(s.Sub_Id) AS cnt, "
            "SUM(CASE s.Bill_Cycle WHEN 'Weekly' THEN s.Amount * 52 / 12 WHEN 'Monthly' THEN s.Amount "
            "WHEN 'Quarterly' THEN s.Amount / 3 ELSE s.Amount / 12 END) AS monthly "
            "FROM subscription s JOIN account a ON a.Acc_Id = s.Acc_Id "
            "LEFT JOIN `user` u ON u.user_Id = a.user_Id "
            "LEFT JOIN company c ON c.Company_Id = a.Company_Id "
            "GROUP BY a.Acc_Id, u.name, c.name) x ORDER BY x.monthly DESC"),
    ),
    "statement": dict(
        label="Account Statement", title="Account Statement",
        description="Choose an account and, if you want, a date range. Credits show as positive and debits as negative.",
        params=[F("acc", "Account", "fk", ref="account")] + DATE_PARAMS,
        headers=["Txn ID", "Date", "Type", "Category", "Signed Amount"],
        sql=lambda p: (
            "SELECT t.transaction_Id, t.`Date`, t.`type`, COALESCE(c.name, '-'), "
            "CASE WHEN t.`type` = 'Credit' THEN t.amount ELSE -t.amount END "
            "FROM `transaction` t LEFT JOIN category c ON c.category_Id = t.category_Id "
            f"WHERE t.Acc_Id = {p['acc']}" + _date_filter("t.`Date`", p) +
            " ORDER BY t.`Date`, t.transaction_Id"),
    ),
}


# ==========================================================================
# Input conversion / validation (user input -> SQL literal)
# ==========================================================================
def convert(field, raw):
    raw = (raw or "").strip()
    label = field["label"]
    if raw == "":
        if field["required"]:
            raise ValueError(f"'{label}' is required.")
        return "NULL"
    kind = field["kind"]
    if kind == "text":
        if len(raw) > field.get("maxlength", 255):
            raise ValueError(f"'{label}' must be at most {field.get('maxlength', 255)} characters.")
        return sql_str(raw)
    if kind == "choice":
        if raw not in field["choices"]:
            raise ValueError(f"'{label}' has an invalid option.")
        return sql_str(raw)
    if kind in ("int", "fk"):
        try:
            return str(int(raw))
        except ValueError:
            raise ValueError(f"'{label}' must be a whole number.")
    if kind == "decimal":
        try:
            num = Decimal(raw)
        except InvalidOperation:
            raise ValueError(f"'{label}' must be a number.")
        if not num.is_finite():
            raise ValueError(f"'{label}' must be a number.")
        if "min" in field and num < Decimal(field["min"]):
            raise ValueError(f"'{label}' must be at least {field['min']}.")
        return str(num.quantize(Decimal("0.01")))
    if kind == "date":
        try:
            d = date.fromisoformat(raw)
        except ValueError:
            raise ValueError(f"'{label}' must be a valid date (YYYY-MM-DD).")
        if field.get("not_future") and d > date.today():
            raise ValueError(f"'{label}' cannot be in the future.")
        return f"'{d.isoformat()}'"
    raise ValueError(f"Unknown field type for '{label}'.")


def pk_where(entity, data):
    parts = []
    for col in entity["pk"]:
        try:
            parts.append(f"`{col}` = {int(data.get(col, ''))}")
        except ValueError:
            raise ValueError("Missing or invalid record identifier.")
    return " AND ".join(parts)


# ==========================================================================
# HTML building helpers
# ==========================================================================
class FKCache:
    """Loads each FK dropdown at most once per request."""
    def __init__(self):
        self._cache = {}

    def get(self, ref):
        if ref not in self._cache:
            self._cache[ref] = [(r[0], r[1]) for r in run_sql(FK_SOURCES[ref], fetch=True)]
        return self._cache[ref]


def build_field(field, value, fk):
    value = "" if value is None else str(value)
    label = esc(field["label"]) + (T.REQUIRED_MARK if field["required"] else "")
    attrs = "required" if field["required"] else ""
    hint = T.HINT.substitute(text=esc(field["hint"])) if field.get("hint") else ""
    kind = field["kind"]

    if kind in ("choice", "fk"):
        options = [("", "-- select --" if field["required"] else "-- none --")]
        if kind == "choice":
            options += [(c, c) for c in field["choices"]]
        else:
            options += fk.get(field["ref"])
        opts_html = "".join(
            T.OPTION.substitute(value=esc(v), text=esc(t),
                                selected="selected" if str(v) == value else "")
            for v, t in options)
        return T.FIELD_SELECT.substitute(label=label, name=esc(field["name"]),
                                         attrs=attrs, options=opts_html, hint=hint)

    input_type = "text"
    if kind == "text":
        attrs += f' maxlength="{field.get("maxlength", 255)}"'
    elif kind == "int":
        input_type = "number"
        attrs += ' step="1"'
    elif kind == "decimal":
        input_type = "number"
        attrs += ' step="0.01"'
        if "min" in field:
            attrs += f' min="{field["min"]}"'
    elif kind == "date":
        input_type = "date"
        if field.get("not_future"):
            attrs += f' max="{date.today().isoformat()}"'
    return T.FIELD_INPUT.substitute(label=label, type=input_type, name=esc(field["name"]),
                                    value=esc(value), attrs=attrs, hint=hint)


def build_table(headers, rows, row_actions=None):
    head = "".join(T.TH.substitute(text=esc(h)) for h in headers)
    if row_actions:
        head += T.TH.substitute(text="Actions")
    body = []
    for row in rows:
        cells = "".join(T.TD.substitute(text=T.NULL_CELL if v is None else esc(v)) for v in row)
        if row_actions:
            cells += row_actions(row)
        body.append(T.TR.substitute(cells=cells))
    if not body:
        body.append(T.EMPTY_ROW.substitute(span=len(headers) + (1 if row_actions else 0)))
    return T.TABLE.substitute(headers=head, rows="".join(body))


def build_nav(active):
    items = [T.NAV_SECTION.substitute(label="Overview"),
             T.NAV_ITEM.substitute(href="/", label="Dashboard", cls="active" if active == "home" else "")]
    group = None
    for slug, ent in ENTITIES.items():
        if ent["group"] != group:
            group = ent["group"]
            items.append(T.NAV_SECTION.substitute(label=esc(group)))
        items.append(T.NAV_ITEM.substitute(href=f"/{slug}", label=esc(ent["title"]),
                                           cls="active" if active == slug else ""))
    items.append(T.NAV_SECTION.substitute(label="Analysis"))
    items.append(T.NAV_ITEM.substitute(href="/reports", label="Reports",
                                       cls="active" if active == "reports" else ""))
    return "".join(items)


def render_page(title, content, active="", msg="", err=""):
    message = ""
    if msg:
        message += T.MSG_OK.substitute(text=esc(msg))
    if err:
        message += T.MSG_ERR.substitute(text=esc(err))
    return T.LAYOUT.substitute(title=esc(title), nav=build_nav(active),
                               message=message, content=content)


# ==========================================================================
# Page builders
# ==========================================================================
def page_home(msg, err):
    slugs = list(ENTITIES)
    sql = "SELECT " + ", ".join(f"(SELECT COUNT(*) FROM `{ENTITIES[s]['table']}`)" for s in slugs)
    counts = run_sql(sql, fetch=True)[0]
    cards = "".join(T.HOME_CARD.substitute(href=f"/{s}", count=esc(c), label=esc(ENTITIES[s]["title"]))
                    for s, c in zip(slugs, counts))
    return render_page("Dashboard", T.HOME.substitute(cards=cards), "home", msg, err)


def page_entity(slug, msg, err):
    ent = ENTITIES[slug]
    fk = FKCache()
    rows = run_sql(ent["list_sql"], fetch=True)
    npk = len(ent["pk"])

    def actions(row):
        pk_vals = dict(zip(ent["pk"], row[:npk]))
        edit = ""
        if ent["editable"]:
            edit = T.EDIT_LINK.substitute(href=esc(f"/{slug}/edit?{urlencode(pk_vals)}"))
        hidden = "".join(T.HIDDEN.substitute(name=esc(k), value=esc(v)) for k, v in pk_vals.items())
        delete = T.DELETE_FORM.substitute(action=f"/{slug}/delete", hidden=hidden)
        return T.ACTIONS_CELL.substitute(edit=edit, delete=delete)

    form = T.FORM.substitute(
        action=f"/{slug}/create", hidden="",
        fields="".join(build_field(f, "", fk) for f in ent["fields"]),
        submit=f"Add {esc(ent['singular'])}", cancel="")
    content = T.ENTITY_PAGE.substitute(
        singular=esc(ent["singular"]), form=form, count=len(rows),
        table=build_table(ent["headers"], rows, actions))
    return render_page(ent["title"], content, slug, msg, err)


def page_edit(slug, query, msg, err):
    ent = ENTITIES[slug]
    where = pk_where(ent, query)
    cols = ", ".join(f"`{f['name']}`" for f in ent["fields"])
    rows = run_sql(f"SELECT {cols} FROM `{ent['table']}` WHERE {where}", fetch=True)
    if not rows:
        return render_page("Not Found", T.NOT_FOUND, slug, err=f"{ent['singular']} not found.")
    fk = FKCache()
    hidden = "".join(T.HIDDEN.substitute(name=esc(k), value=esc(query[k])) for k in ent["pk"])
    form = T.FORM.substitute(
        action=f"/{slug}/update", hidden=hidden,
        fields="".join(build_field(f, v, fk) for f, v in zip(ent["fields"], rows[0])),
        submit="Save Changes", cancel=T.CANCEL_LINK.substitute(href=f"/{slug}"))
    ident = esc(", ".join(query[k] for k in ent["pk"]))
    content = T.EDIT_PAGE.substitute(singular=esc(ent["singular"]), ident=ident, form=form)
    return render_page(f"Edit {ent['singular']}", content, slug, msg, err)


def page_reports(query, msg, err):
    key = query.get("r", "networth")
    if key not in REPORTS:
        key = "networth"
    rep = REPORTS[key]
    tabs = "".join(T.REPORT_TAB.substitute(href=f"/reports?r={k}", label=esc(r["label"]),
                                           cls="active" if k == key else "")
                   for k, r in REPORTS.items())
    filter_html, table_html = "", ""
    if rep["params"]:
        fk = FKCache()
        fields = "".join(build_field(f, query.get(f["name"], ""), fk) for f in rep["params"])
        filter_html = T.FILTER_FORM.substitute(report=esc(key), fields=fields)

    # Required inputs missing -> just show the filter form
    missing = [f for f in rep["params"] if f["required"] and not query.get(f["name"])]
    if missing:
        table_html = T.MSG_OK.substitute(text="Fill in the form above and click Run Report.")
    else:
        try:
            params = {f["name"]: convert(f, query.get(f["name"], "")) for f in rep["params"]}
            rows = run_sql(rep["sql"](params), fetch=True)
            table_html = build_table(rep["headers"], rows)
        except ValueError as e:
            err = str(e)
    content = T.REPORTS_PAGE.substitute(tabs=tabs, title=esc(rep["title"]),
                                        description=esc(rep["description"]),
                                        filter=filter_html, table=table_html)
    return render_page("Reports", content, "reports", msg, err)


# ==========================================================================
# CRUD actions
# ==========================================================================
def collect_values(ent, data):
    values = {f["name"]: convert(f, data.get(f["name"], "")) for f in ent["fields"]}
    if ent.get("validate"):
        ent["validate"](values)
    return values


def do_create(ent, data):
    values = collect_values(ent, data)
    cols = ", ".join(f"`{c}`" for c in values)
    vals = ", ".join(values.values())
    run_sql(f"INSERT INTO `{ent['table']}` ({cols}) VALUES ({vals});")
    return f"{ent['singular']} added successfully."


def do_update(ent, data):
    where = pk_where(ent, data)
    values = collect_values(ent, data)
    assignments = ", ".join(f"`{c}` = {v}" for c, v in values.items())
    run_sql(f"UPDATE `{ent['table']}` SET {assignments} WHERE {where};")
    return f"{ent['singular']} updated successfully."


def do_delete(ent, data):
    where = pk_where(ent, data)
    run_sql(f"DELETE FROM `{ent['table']}` WHERE {where};")
    return f"{ent['singular']} deleted."


ACTIONS = {"create": do_create, "update": do_update, "delete": do_delete}


# ==========================================================================
# HTTP handler
# ==========================================================================
class FinanceHandler(BaseHTTPRequestHandler):

    def send_html(self, body, status=200):
        payload = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def redirect(self, location):
        self.send_response(303)          # Post/Redirect/Get: refreshing won't resubmit the form
        self.send_header("Location", location)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self):
        url = urlparse(self.path)
        parts = [p for p in url.path.split("/") if p]
        query = {k: v[0] for k, v in parse_qs(url.query).items()}
        msg, err = query.get("msg", ""), query.get("err", "")
        status = 200
        try:
            if not parts:
                page = page_home(msg, err)
            elif parts == ["reports"]:
                page = page_reports(query, msg, err)
            elif len(parts) == 1 and parts[0] in ENTITIES:
                page = page_entity(parts[0], msg, err)
            elif (len(parts) == 2 and parts[0] in ENTITIES and parts[1] == "edit"
                  and ENTITIES[parts[0]]["editable"]):
                page = page_edit(parts[0], query, msg, err)
            else:
                status = 404
                page = render_page("Not Found", T.NOT_FOUND)
        except (DBError, ValueError) as e:
            page = render_page("Error", "", err=str(e))
        self.send_html(page, status)

    def do_POST(self):
        parts = [p for p in urlparse(self.path).path.split("/") if p]
        if len(parts) != 2 or parts[0] not in ENTITIES or parts[1] not in ACTIONS:
            self.send_html(render_page("Not Found", T.NOT_FOUND), 404)
            return
        slug, action = parts
        ent = ENTITIES[slug]
        if action == "update" and not ent["editable"]:
            self.send_html(render_page("Not Found", T.NOT_FOUND), 404)
            return

        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length).decode("utf-8")
        data = {k: v[0] for k, v in parse_qs(body, keep_blank_values=True).items()}

        try:
            message = ACTIONS[action](ent, data)
            self.redirect(f"/{slug}?" + urlencode({"msg": message}))
        except (ValueError, DBError) as e:
            if action == "update":
                pk_vals = {k: data.get(k, "") for k in ent["pk"]}
                self.redirect(f"/{slug}/edit?" + urlencode({**pk_vals, "err": str(e)}))
            else:
                self.redirect(f"/{slug}?" + urlencode({"err": str(e)}))


if __name__ == "__main__":
    print(f"FinanceDB running at http://{HOST}:{PORT}  (Ctrl+C to stop)")
    try:
        HTTPServer((HOST, PORT), FinanceHandler).serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped.")

