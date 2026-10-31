# CommonGround

**Shared resources, accountable access.**

CommonGround helps one campus makerspace share valuable tools, workspaces and specialist equipment without leaving safety, fair access or accountability to chance. Members can see what is available and what training is required; resource staff remain in charge of approval and handover.

> **Product owner:** Isaac Shiloah Herbert V · **ISAAC.INCOGNITO007**  
> **Contact:** [isaac.incognito007@gmail.com](mailto:isaac.incognito007@gmail.com)

## What it does

- A searchable, category-filtered resource catalogue with location, availability, owner, training prerequisites and clear use conditions.
- Account sign-in, role-based access, administrator-reviewed campus membership and independently assigned training credentials.
- Server-validated booking requests, India Standard Time date rules, date-conflict checks and protection against duplicate submits.
- Owner/manager approval, reasoned rejection, cancellation and an explainable waiting list.
- A group limit of two active requests per resource. Competing requests wait; the queue prioritizes fewer completed usage days in the preceding 30 days, then earlier request time. Managers can review each decision.
- A transaction record from approval to collection, before/after condition notes, borrower return, staff confirmation, extensions and incident reporting/resolution.
- Account-specific history and in-app notifications/reminders, with access to each record limited to its borrower and authorized resource staff.
- Responsive layouts, keyboard-visible focus, labelled inputs, reduced-motion support, accessible date errors and native keyboard-operable dialogs.

## The people and the problem

Campus makerspaces can own costly equipment that is idle between projects, while a student or researcher may need a particular camera, room or tool for only a day. A calendar alone does not check whether the borrower is trained, protect a resource owner’s decision, record handover condition, or resolve competing requests fairly.

CommonGround focuses on a **single campus makerspace**. Its core user is a campus member who needs short-term access. The owner, authorized manager and campus administrator provide distinct, reviewable checks. A booking stays a **request** until a person with resource authority approves it; training or software flags never authorize hazardous access by themselves.

## Architecture

| Layer | Implementation | Why |
|---|---|---|
| Browser interface | Semantic HTML shell, vanilla JavaScript and responsive CSS | Small footprint, readable source, no build chain or runtime framework required |
| HTTP application | Python 3.11+ standard library and JSON endpoints | A solo maintainer can run and inspect the service without installing a web framework |
| Persistent records | SQLite locally; PostgreSQL on Vercel through Psycopg 3, with WAL/foreign-key/index/transaction protections appropriate to each backend | Local data stays easy to inspect; managed PostgreSQL provides durable shared storage for serverless instances |
| Account security | OpenSSL-backed `hashlib.scrypt`, random opaque server-side session, eight-hour expiry, hashed session lookup, `HttpOnly`/`SameSite=Strict` cookie, CSRF token and same-origin checks | No password or privilege token in browser storage |
| Deployment | Vercel Python WSGI function with managed PostgreSQL, or Docker Compose with a persistent volume and Caddy | Vercel stores data outside disposable functions; the local/Docker SQLite setup remains available |
| Browser QA | Chromium driven through the Chrome DevTools Protocol by a small standard-library test harness | Runs a real browser without a JavaScript automation dependency |

**Data model:** `users` holds identity, role, campus group and reviewed credentials; `sessions` holds the hash of a random session token, CSRF value and expiry; `resources` holds owner, manager, use conditions, training and availability; `bookings` holds borrower, dates, purpose, status, reason and condition/handover notes; `incidents` holds an incident and staff resolution; `activity` is append-only at the SQL trigger layer; and `notifications` stores per-account messages. Foreign keys and indexes support record integrity and calendar-conflict queries. A database write transaction serializes competing decisions. The unique `(user_id, idempotency)` constraint prevents a replay from creating another booking.

## Booking and safety flow

1. A signed-in member searches and filters resources, reads the rules and views eligibility gaps.
2. The member selects a collection date and a later return date, states the purpose and accepts conditions.
3. The browser checks the dates for quick feedback; the server repeats validation independently using plain ISO dates and the `Asia/Kolkata` business date. Same-day collection is allowed, the return date is later and exclusive, and the loan may not exceed seven days.
4. The service saves a `Pending` or `Waitlisted` request and an audit event in one transaction. An overlapping request is queued; a duplicate request/key is rejected or returns the original saved record.
5. The authorized resource owner or assigned manager verifies eligibility and considers conflicts, group limits and queue priority. Approval requires current membership and required training.
6. Only an approved borrower can record collection during the approved dates. Both collection and return ask for a condition note. Staff confirm the return; an open incident must be reviewed first.
7. Borrower and authorized staff can follow the record, condition notes, actions, actor, reason and timestamp.

## Run locally

Requirements for local use: CPython 3.11 or newer, SQLite enabled and a terminal. The local SQLite path needs no pip packages. Vercel installs Psycopg 3.3.6 from `requirements.txt` for managed PostgreSQL. No Node installation, AI API key or external font download is required.

```bash
cd commonground
python3 start.py
```

On a new database, the setup asks you to choose one private password (minimum 12 characters) for five fictional, local accounts. Use the generated data to walk through the workflow. All local accounts share the password you set, but retain separate server-enforced roles. **Never expose these convenience accounts to the internet.** The login names are:

| Role | Account |
|---|---|
| Member | `member@campus.example` |
| Member awaiting verification | `newcomer@campus.example` |
| Resource owner | `owner@campus.example` |
| Assigned resource manager | `manager@campus.example` |
| Administrator | `admin@campus.example` |

The terminal prints the local URL (default `http://127.0.0.1:8000`). To select another port: `python3 server.py --port 8001`. The app creates `data/commonground.sqlite3` on first run; it is ignored by Git. There is no preconfigured password.

### Provision accounts for an institution

The sample dataset is not for production. On the service host, create real accounts using the trusted local operator command; it asks interactively for a password and does not put credentials in a shell argument:

```bash
python3 manage.py create-user \
  --name "Campus Administrator" \
  --email administrator@example.edu \
  --role admin \
  --group "Campus Services" \
  --verified
```

Repeat for staff and members, assigning their approved role, institutional group and verified training only after checking the institution’s records. Administrator membership and training changes are reviewed on the **Verification** screen. To reset a password and revoke existing sessions:

```bash
python3 manage.py reset-password --email member@example.edu
```

Create a consistent SQLite backup before upgrades or deployment changes:

```bash
mkdir -p backups
python3 manage.py backup "backups/commonground-$(date +%F-%H%M%S).sqlite3"
```

A backup contains account and booking data; protect it as sensitive information. Never copy an existing backup over another backup.

## Verification Workflow

CommonGround includes a comprehensive verification system for users and resources:

### User Verification
- **Members** can request ID verification for themselves via `/api/verification/request`
- **Managers/Admins** view pending requests via `/api/admin/verifications`
- **Managers/Admins** approve or reject requests via `PATCH /api/admin/verify`
- State machine: unverified → pending → verified/rejected
- Self-verification is blocked (403 if user tries to verify themselves)

### Resource Verification
- **Owners** can request resource verification
- **Managers/Admins** can approve/reject resource verification (but not their own)
- Verification resets to 'unverified' if material edits are made to a verified resource

### API Endpoints
- `POST /api/verification/request` - Request verification (user on self, resource on owner)
- `GET /api/admin/verifications` - Queue for managers/admins (filter by status)
- `PATCH /api/admin/verify` - Approve/reject with reason (required for reject)
- `GET /api/verification/history?target_type=user&target_id=xxx` - Audit trail
- `GET /api/notifications` - List own notifications with unread count
- `POST /api/notifications/read` - Mark notifications as read

### Demo Mode

Set `CG_DEMO_MODE=1` for a demo deployment with pre-seeded accounts:

| Role | Account | Password |
|---|---|---|
| Member | `member@campus.example` | demo-password-123 |
| Owner | `owner@campus.example` | demo-password-123 |
| Manager | `manager@campus.example` | demo-password-123 |

For the judge deployment, set:
```bash
export CG_DEMO_MODE=1
```

This seeds demo accounts and resources in various verification states for testing.

## Configure a deployment

Docker, Docker Compose and a DNS hostname pointing to the host are needed for the supplied single-instance deployment. Caddy terminates TLS; Compose keeps the Python service private and stores SQLite in the persistent `ground-data` volume. Set the two environment values through a deployment secret/environment manager, not source control:

```bash
export CG_DOMAIN='resources.example.edu'
export CG_ORIGIN='https://resources.example.edu'
docker compose up -d --build
```

Provision the initial administrator through the local container console. This prompts for a password; create no default account or password:

```bash
docker compose exec app python manage.py create-user \
  --name "Campus Administrator" --email administrator@example.edu \
  --role admin --group "Campus Services" --verified
```

Repeat for approved owners/managers/members. Seed fictional sample accounts only for local exploration, not a public deployment. Review and adjust the institution’s privacy, safety, retention, incident, access-review and backup procedures before real use.

For a directly managed HTTPS reverse proxy, set `CG_HOST=0.0.0.0`, `PORT`, `CG_DB` (durable absolute path), `CG_ORIGIN` to the exact public `https://` origin and `CG_SECURE_COOKIE=1` before starting `python3 server.py`. Restrict the application to the reverse-proxy network; do not expose the Python HTTP port directly. `.env.example` documents supported variables; Python does not read `.env` automatically. For local shell configuration, `set -a; . ./.env; set +a` applies its values.

## Deploy on Vercel

The repository includes `api/index.py` and `vercel.json`. Vercel's Python runtime invokes the existing service through a WSGI adapter; the rewrites route the app shell, its local assets and `/api/*` requests to that function. **Vercel requires managed PostgreSQL. Do not use SQLite there:** function filesystems are temporary and separate function instances do not share a local database.

1. Upload the contents of this project folder to GitHub. In Vercel, import that repository and set the project root to the folder containing `vercel.json`, `requirements.txt`, `api/`, `server.py` and `web/`.
2. Provision a managed PostgreSQL database reachable from the function. Set `DATABASE_URL` or `POSTGRES_URL` as an encrypted Vercel environment variable for Production (and Preview if needed). Do not commit the connection string.
3. Set `CG_SECURE_COOKIE=1` and `CG_ORIGIN` to the exact public origin, such as `https://your-project.vercel.app` (or your custom HTTPS domain). Vercel itself supplies the `VERCEL` marker.
4. Deploy with the standard Vercel Python runtime. There is no frontend build command. The first request initializes the schema; without a persistent PostgreSQL URL, the function returns a storage-unavailable response instead of silently saving to ephemeral SQLite.
5. Create the initial administrator from a trusted operator environment that has Psycopg installed and the same database URL configured securely. Run `python3 manage.py create-user` with the arguments shown under account provisioning. Do not use the local fictional seed accounts in production.

The CLI command prompts for the account password. Put the database URL into a trusted secret manager or protected process environment; do not place it in source control, a shell command line, or terminal history. Database backups, migrations, monitoring and access to the Vercel/PostgreSQL projects remain operator responsibilities.

## Test

```bash
# API/date/auth/fairness/lifecycle regression tests
python3 -m unittest discover -s tests -p 'test_service.py' -v

# WSGI adapter, rewrites, static assets, health, login and session tests
python3 -m unittest discover -s tests -p 'test_vercel_wsgi.py' -v

# JavaScript parse check (optional Node.js)
node --check web/app.js

# Full Chromium user journey and 390 / 768 / 1440 px width checks
python3 tests/browser_check.py
```

The browser journey requires `chromium` (or `google-chrome`); set `CHROMIUM=/path/to/chromium` when necessary. It tests session persistence on refresh, a genuine backend-created booking, confirmation, history, human approval, check-in, return and owner confirmation. Browser output includes screenshots when the runner is started in a workspace with `output/` enabled.

In an isolated runner where TCP loopback is unavailable, the included optional `CG_TEST_TRANSPORT=socketpair` test adapter sends real HTTP messages over a local socket pair to the **same `BaseHTTPRequestHandler` and SQLite service**. The browser test additionally needs the local Chromium executable. Ordinary developer machines use TCP by default.

## Interface and privacy

Product records contain names, institutional emails, groups, booking purposes, condition notes and staff decisions. Store only what an institution needs, inform account holders of retention, limit file-system and operator access, run backups, and provide an institution-approved deletion/retention process. The app avoids collecting identity-document uploads and does not disclose another member’s booking details in the public resource catalogue. Notifications are in-app and generated when a user opens or refreshes the workspace; **there is no email/SMS or background reminder service**.

There is no runtime AI scoring or automated safety decision. Access depends on verified account records and accountable human review. Data displayed in the browser is escaped; application operations are parameterized SQL; unexpected internal errors are logged server-side rather than returned as a stack trace. Session cookies are `HttpOnly` and `SameSite=Strict`; `Secure` plus HSTS applies when secure cookie mode is enabled. No third-party script or analytics service is loaded.

## License and attribution

The original application code, UI and tests are released under the [MIT License](LICENSE). See [NOTICE](NOTICE) for runtime/deployment software and license notes. No competitor source, open-source application template, logo, icon package, photography or font binary was copied or bundled. Public product pages informed feature research; the interface and code are original. The code and design were created with significant AI assistance; no AI service is called by the running application.

## Important scope and operational limits

- The product is scoped to one campus, not a multi-tenant identity service. Local SQLite/Docker remains a single-instance setup; Vercel mode uses shared managed PostgreSQL for durable data across serverless instances.
- The included server uses Python’s small standard-library HTTP server. Caddy and TLS are part of the sample deployment, but independent security review, load testing, monitoring, security response plans and production incident procedures remain the operator’s responsibility.
- Institutional identity-provider login, email/password-recovery, invitation flow and external e-signature are not integrated. Accounts and role changes are operator/administrator managed.
- Before/after records are text notes rather than photos or signatures. The service cannot inspect a tool or confirm that physical measurements are truthful.
- Notifications are in-app only and depend on a user opening or refreshing the app; reminders are not delivered in the background.
- Login rate limiting is in-process and resets when a function instance restarts; it is not a global abuse-control system. A production Vercel deployment should add shared rate limiting or a suitable edge/WAF policy, plus managed migrations and scheduled backups.
- Audit events cannot be changed through application SQL, but an operator with filesystem/database access can alter the database. Export/replicate audit records to separately controlled, append-only storage before treating them as forensic evidence.
- Membership and training are as reliable as the records reviewed by a human administrator. No OCR, external identity proof, hazard detection or automated penalty feature is included.
- A new owner may list a resource through the catalogue form. A verified administrator/owner assigns a manager from a booking record after it exists; account creation and initial role/group assignment use the trusted operator utility.

## Product owner

**Isaac Shiloah Herbert V**  
**ISAAC.INCOGNITO007**  
[isaac.incognito007@gmail.com](mailto:isaac.incognito007@gmail.com)
