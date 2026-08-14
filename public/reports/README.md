# public/reports

Checked into git — unlike `local/reports/` (gitignored, see its own README), this folder is meant
to hold only **stable, never-refreshed** workbooks, since Power Query embeds the actual fetched
result set inside an `.xlsx` on every refresh, and a file that changes size on every save bloats
git history (git can't meaningfully diff/delta zip-based formats).

`sample.xlsx` is a fixed example wired up to the `quant-data-tunnel` ODBC DSN, kept as-is
deliberately — never refresh-and-resave it. If you want a live, actively-refreshed dashboard,
build it under `local/reports/` instead.
