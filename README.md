# FinanceDB

A personal-finance web app built with **only the Python standard library** and **MySQL**.
It manages households, users, companies, shares, banks, accounts, subscriptions,
categories, transactions and savings goals. All SQL runs through the local `mysql.exe`
client via `subprocess`.

## Requirements

- Python 3.8+ (no `pip install` needed)
- MySQL Server 8.0 with `mysql.exe` at
  `C:\Program Files\MySQL\MySQL Server 8.0\bin\mysql.exe`
- MySQL `root` user with the password set in the scripts (default `student`)

If your setup differs, edit `MYSQL_PATH`, `DB_PASS` and `DB_NAME` at the top of both
`setup_db.py` and `app.py`.

## Quick start

```powershell
python setup_db.py   # one time: creates database Financedb, tables, keys, view
python app.py        # starts the server
```

Then open <http://localhost:8000>.

`setup_db.py` asks for confirmation before dropping and recreating the project's tables,
and offers to load sample data. It only touches the tables listed below.

## Project structure

| File | Purpose |
|------|---------|
| `setup_db.py` | Creates the `Financedb` database, tables (`CREATE TABLE`), foreign keys (`ALTER TABLE`), the `user_details` view and optional sample data |
| `app.py` | HTTP server (`BaseHTTPRequestHandler`): routing, CRUD for every table, reports, input validation |
| `templates.py` | All HTML (layout, forms, tables, reports) as Python string templates |

## Database schema

Tables: `household`, `company`, `user`, `shares`, `owns`, `bank`, `account`,
`subscription`, `category`, `transaction`, `goal`, plus the view `user_details`.

| Relationship | Type | On delete |
|--------------|------|-----------|
| User lives in Household | N:1 | user's link set to NULL |
| User employed by Company | N:1 | user's link set to NULL |
| Shares listed by Company | N:1 | shares deleted |
| User owns Shares (`owns`) | M:N | ownership rows deleted |
| Account belongs to User | N:1 | account deleted |
| Account belongs to Company | 1:1 (`UNIQUE`) | account deleted |
| Account managed by Bank | N:1 | **blocked** while accounts exist |
| Subscription billed to Account (weak entity) | N:1 | subscription deleted |
| Transaction / Goal records to Account | N:1 | deleted with the account |
| Transaction / Goal has Category | N:1 | category link set to NULL |

Notes:
- **Age is never stored.** The `user_details` view calculates it from `DOB`.
- An account must belong to exactly one owner, a User or a Company (checked by the app).
- Amounts must be non-negative, goal targets and transaction amounts must be positive, and a date of birth cannot be in the future.

## Features

- Sidebar navigation: Households, Users, Companies, Shares, Share Ownership, Banks,
  Accounts, Subscriptions, Categories, Transactions, Savings Goals.
- Add, list, edit and delete records, with dropdowns for foreign keys and plain-language error messages.
- Reports: net worth per user, household summary, spending by category (date range),
  monthly subscription cost per account, and an account statement.

## Limitations

- Double quotes in typed text are removed, because queries are passed through `mysql.exe -e "..."`.
- Adding a transaction does not update the account balance.
- No login or authentication; intended for local, educational use only. Do not expose it to a network.

