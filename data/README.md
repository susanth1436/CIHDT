## Operator database

The console stores accounts, server-side sessions and the audit log in
`cihdt.sqlite3` in this directory. SQLite runs in WAL mode, so two companion
files (`-wal` and `-shm`) appear beside it while the server is running.

Nothing here is committed, because the database holds real email addresses
and PBKDF2 password hashes. It is created empty on first start, with the
schema applied through versioned migrations:

```bash
python run.py
```

Then open the console and use **Create one** on the sign-in page to register
the first operator. No default credential exists anywhere in the source tree.
