"""
templates.py - every piece of HTML used by app.py.

All templates are string.Template objects, so placeholders look like $name.
(string.Template is used instead of str.format so CSS braces need no escaping.)
"""
from string import Template

# --------------------------------------------------------------------------
# Page layout
# --------------------------------------------------------------------------
LAYOUT = Template("""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>$title - FinanceDB</title>
<style>
  * { box-sizing: border-box; }
  body { margin: 0; font-family: "Segoe UI", Arial, sans-serif; background: #f3f5f9; color: #1f2937; display: flex; min-height: 100vh; }
  aside { width: 230px; background: #111827; color: #e5e7eb; padding: 18px 0; flex-shrink: 0; }
  aside .brand { font-size: 20px; font-weight: 700; padding: 0 20px 14px; color: #fff; border-bottom: 1px solid #374151; }
  aside .nav-section { font-size: 11px; text-transform: uppercase; letter-spacing: .08em; color: #9ca3af; padding: 16px 20px 6px; }
  aside a { display: block; padding: 7px 20px; color: #d1d5db; text-decoration: none; font-size: 14px; }
  aside a:hover { background: #1f2937; color: #fff; }
  aside a.active { background: #2563eb; color: #fff; }
  main { flex: 1; padding: 26px 34px; min-width: 0; }
  h1 { margin: 0 0 18px; font-size: 26px; }
  h2 { margin: 0 0 14px; font-size: 17px; }
  .card { background: #fff; border-radius: 10px; padding: 20px; box-shadow: 0 1px 3px rgba(0,0,0,.08); margin-bottom: 20px; }
  .card.narrow { max-width: 520px; }
  .grid { display: grid; grid-template-columns: 320px 1fr; gap: 20px; align-items: start; }
  @media (max-width: 1000px) { .grid { grid-template-columns: 1fr; } }
  .form label { display: block; font-size: 13px; font-weight: 600; margin-bottom: 12px; }
  .form input, .form select { display: block; width: 100%; margin-top: 4px; padding: 8px 10px; border: 1px solid #d1d5db; border-radius: 6px; font-size: 14px; background: #fff; }
  .form input:focus, .form select:focus { outline: 2px solid #93c5fd; border-color: #2563eb; }
  .filter { display: flex; flex-wrap: wrap; gap: 14px; align-items: flex-end; margin-bottom: 16px; }
  .filter label { margin: 0; min-width: 200px; }
  .filter .actions { margin: 0 0 1px; }
  .req { color: #dc2626; margin-left: 2px; }
  .hint { display: block; font-weight: 400; color: #6b7280; margin-top: 3px; }
  .actions { display: flex; gap: 8px; margin-top: 6px; }
  button, .btn { background: #2563eb; color: #fff; border: 0; border-radius: 6px; padding: 8px 16px; font-size: 14px; cursor: pointer; text-decoration: none; display: inline-block; }
  button:hover, .btn:hover { background: #1d4ed8; }
  .btn.secondary { background: #e5e7eb; color: #111827; }
  .small { padding: 4px 10px; font-size: 12px; }
  .danger { background: #dc2626; }
  .danger:hover { background: #b91c1c; }
  form.inline { display: inline; }
  .table-wrap { overflow-x: auto; }
  table { width: 100%; border-collapse: collapse; font-size: 14px; }
  th, td { text-align: left; padding: 9px 10px; border-bottom: 1px solid #e5e7eb; white-space: nowrap; }
  th { background: #f9fafb; font-size: 12px; text-transform: uppercase; letter-spacing: .04em; color: #4b5563; }
  tr:hover td { background: #f9fafb; }
  td.row-actions { display: flex; gap: 6px; }
  td.empty { text-align: center; color: #6b7280; padding: 22px; }
  .count { background: #e0e7ff; color: #3730a3; border-radius: 999px; padding: 2px 9px; font-size: 12px; margin-left: 6px; }
  .msg { padding: 11px 14px; border-radius: 8px; margin-bottom: 18px; font-size: 14px; }
  .msg.ok { background: #dcfce7; color: #166534; border: 1px solid #86efac; }
  .msg.err { background: #fee2e2; color: #991b1b; border: 1px solid #fca5a5; }
  .lead { color: #4b5563; margin-top: -8px; }
  .muted { color: #6b7280; margin-top: -6px; }
  .cards { display: grid; grid-template-columns: repeat(auto-fill, minmax(170px, 1fr)); gap: 16px; }
  .stat { background: #fff; border-radius: 10px; padding: 18px; text-decoration: none; color: inherit; box-shadow: 0 1px 3px rgba(0,0,0,.08); border-top: 4px solid #2563eb; }
  .stat:hover { box-shadow: 0 4px 12px rgba(0,0,0,.12); }
  .stat .num { display: block; font-size: 30px; font-weight: 700; color: #1e3a8a; }
  .stat .lbl { color: #4b5563; font-size: 14px; }
  .tabs { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 16px; }
  .tab { padding: 7px 14px; border-radius: 999px; background: #e5e7eb; color: #111827; text-decoration: none; font-size: 14px; }
  .tab.active { background: #2563eb; color: #fff; }
</style>
</head>
<body>
<aside>
  <div class="brand">FinanceDB</div>
  $nav
</aside>
<main>
  <h1>$title</h1>
  $message
  $content
</main>
</body>
</html>
""")

NAV_SECTION = Template('<div class="nav-section">$label</div>')
NAV_ITEM = Template('<a href="$href" class="$cls">$label</a>')

MSG_OK = Template('<div class="msg ok">$text</div>')
MSG_ERR = Template('<div class="msg err">$text</div>')

# --------------------------------------------------------------------------
# Home / dashboard
# --------------------------------------------------------------------------
HOME = Template("""
<p class="lead">Personal finance database: households, users, employers, shares, bank accounts,
subscriptions, transactions and savings goals. Pick a table from the menu to manage its records.</p>
<div class="cards">$cards</div>
""")

HOME_CARD = Template(
    '<a class="stat" href="$href"><span class="num">$count</span><span class="lbl">$label</span></a>')

# --------------------------------------------------------------------------
# Entity (table) management pages
# --------------------------------------------------------------------------
ENTITY_PAGE = Template("""
<div class="grid">
  <section class="card">
    <h2>Add $singular</h2>
    $form
  </section>
  <section class="card">
    <h2>All Records <span class="count">$count</span></h2>
    $table
  </section>
</div>
""")

EDIT_PAGE = Template("""
<section class="card narrow">
  <h2>Edit $singular #$ident</h2>
  $form
</section>
""")

FORM = Template("""
<form method="POST" action="$action" class="form">
  $hidden
  $fields
  <div class="actions"><button type="submit">$submit</button>$cancel</div>
</form>
""")

FIELD_INPUT = Template(
    '<label>$label<input type="$type" name="$name" value="$value" $attrs>$hint</label>')
FIELD_SELECT = Template(
    '<label>$label<select name="$name" $attrs>$options</select>$hint</label>')
OPTION = Template('<option value="$value" $selected>$text</option>')
HIDDEN = Template('<input type="hidden" name="$name" value="$value">')
HINT = Template('<small class="hint">$text</small>')
REQUIRED_MARK = '<span class="req">*</span>'
CANCEL_LINK = Template('<a class="btn secondary" href="$href">Cancel</a>')

# --------------------------------------------------------------------------
# Tables
# --------------------------------------------------------------------------
TABLE = Template("""
<div class="table-wrap">
<table>
  <thead><tr>$headers</tr></thead>
  <tbody>$rows</tbody>
</table>
</div>
""")
TH = Template('<th>$text</th>')
TD = Template('<td>$text</td>')
TR = Template('<tr>$cells</tr>')
EMPTY_ROW = Template('<tr><td colspan="$span" class="empty">No records found.</td></tr>')
NULL_CELL = '<span style="color:#9ca3af">&mdash;</span>'

ACTIONS_CELL = Template('<td class="row-actions">$edit$delete</td>')
EDIT_LINK = Template('<a class="btn small" href="$href">Edit</a>')
DELETE_FORM = Template(
    '<form method="POST" action="$action" class="inline" '
    'onsubmit="return confirm(\'Delete this record? Dependent records may also be removed (cascade).\');">'
    '$hidden<button class="small danger" type="submit">Delete</button></form>')

# --------------------------------------------------------------------------
# Reports
# --------------------------------------------------------------------------
REPORTS_PAGE = Template("""
<div class="tabs">$tabs</div>
<section class="card">
  <h2>$title</h2>
  <p class="muted">$description</p>
  $filter
  $table
</section>
""")
REPORT_TAB = Template('<a class="tab $cls" href="$href">$label</a>')
FILTER_FORM = Template("""
<form method="GET" action="/reports" class="form filter">
  <input type="hidden" name="r" value="$report">
  $fields
  <div class="actions"><button type="submit">Run Report</button></div>
</form>
""")

NOT_FOUND = '<section class="card"><p>The page you requested does not exist.</p><a class="btn" href="/">Go Home</a></section>'

