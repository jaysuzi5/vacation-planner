# Vacation Planner — Project Roadmap

Tracks setup progress and planned features.
Credentials and secrets are **not** stored here — see k8s SealedSecrets and local `.env`.

---

## Phase 1: Project Foundation ✅

- [x] Create project directory structure
- [x] Create `.claudeignore`, `.vscode/tasks.json`, `CLAUDE.md`
- [x] Initialize `pyproject.toml` with all dependencies (Django 6, allauth, OpenTelemetry, etc.)
- [x] Create `manage.py`, `.python-version`
- [x] Configure `config/settings.py` — PostgreSQL, allauth, WhiteNoise, OTEL, logging
- [x] Configure `config/urls.py`, `config/wsgi.py`, `config/asgi.py`
- [x] Configure `config/middleware.py` — JSON request/response logging with user context
- [x] Configure `config/logging_utils.py`, `config/otel_config.py`
- [x] Create `.env.example` (safe to commit — no real credentials)
- [x] Create `.env` (gitignored — contains real local dev credentials)
- [x] Create `.gitignore`

## Phase 2: Planner Application ✅

- [x] Create `planner/` Django app
- [x] Define models:
  - `Vacation` — user-scoped trip with location, dates, status (review/booked/taken), trip notes, budget/actual per category
  - `Day` — daily itinerary entry (lodging, excursion, daily notes) linked to a Vacation
  - `Expense` — line-item spending (description, category dropdown, amount) linked to a Day
- [x] Budget/actual categories: airfare, lodging, meals, excursions, gas, miscellaneous
- [x] Trip status choices: In Review, Booked, Taken
- [x] Computed properties: total_budget, total_actual, variance per category and overall
- [x] Create views:
  - `DashboardView` — list user's own vacations (paginated, status-filtered)
  - `VacationCreateView` — create new vacation
  - `VacationDetailView` — full trip detail: budget summary, days, expenses
  - `VacationEditView` — edit trip metadata, dates, budget/actual fields, trip notes
  - `VacationDeleteView` — soft-delete confirmation
  - `DayCreateView` / `DayEditView` / `DayDeleteView` — manage daily itinerary
  - `ExpenseCreateView` / `ExpenseEditView` / `ExpenseDeleteView` — manage line-item expenses
- [x] All views enforce `LoginRequired` and `user == vacation.user` ownership check
- [x] Create `planner/urls.py`
- [x] Create `planner/forms.py` — VacationForm, DayForm, ExpenseForm
- [x] Create `planner/admin.py` — admin with inline Days and Expenses

## Phase 3: Templates & Design ✅

- [x] Create `templates/base.html` — navbar, footer, Bootstrap 5, Google Fonts
- [x] Create `planner/dashboard.html` — vacation cards grid with status badges and budget summary
- [x] Create `planner/vacation_detail.html` — budget vs. actual table, day-by-day itinerary, expense log
- [x] Create `planner/vacation_form.html` — create/edit vacation with all fields
- [x] Create `planner/day_form.html` — add/edit daily itinerary entry
- [x] Create `planner/expense_form.html` — add/edit line-item expense
- [x] Create `planner/confirm_delete.html` — reusable delete confirmation
- [x] Create auth templates — login, signup styled with Google OAuth button
- [x] Create `static/css/site.css` — clean design matching unscripted-living style

## Phase 4: Database ✅

- [x] Create `vacation_planner` database in k8s PostgreSQL (192.168.86.201:30004) — user `jcurtis`, password in SealedSecret
- [x] Install dependencies: `uv sync`
- [x] Run Django migrations — runs automatically via init container on every deployment
- [x] Create superuser: `kubectl exec -n vacation-planner -it <pod> -- uv run python manage.py createsuperuser`
- [x] Verify database tables in pgAdmin

## Phase 5: Kubernetes Secrets ✅

- [x] Create `k8s/temp.yaml` (gitignored plain-text secret) with all credentials
- [x] Seal: `kubeseal --format yaml < k8s/temp.yaml > k8s/secrets.yaml`
- [x] Delete `k8s/temp.yaml` after sealing
- [x] Apply: `kubectl apply -f k8s/secrets.yaml`
- [x] Added `google_client_id`, `google_client_secret` to sealed secret
- [x] Added `aws_access_key_id`, `aws_secret_access_key` to sealed secret (pulled from unscripted-living namespace)

## Phase 6: Docker & Kubernetes Deployment ✅

- [x] Create `Dockerfile` (uv-based, OpenTelemetry + gunicorn)
  - Fixed: added `curl` install via apt before uv install script (`python:3.12-slim` lacks curl)
- [x] Create `k8s/deployment.yaml` (namespace: `vacation-planner`, init container for migrations)
  - Fixed: moved `POSTGRES_USER` / `POSTGRES_PASSWORD` env vars before `DATABASE_URL` so `$(VAR)` interpolation works
- [x] Create `k8s/backup-pvc.yaml`
- [x] Build and push multi-arch Docker image: `jaysuzi5/vacation-planner:latest`
- [x] Applied: namespace, SealedSecret, deployment, service — pod Running

## Phase 7: Cloudflare Tunnel ✅

- [x] Added tunnel route: `vacations.jaycurtis.org` → `vacation-planner.vacation-planner.svc.cluster.local:80`
- [x] Verified at: https://vacations.jaycurtis.org/

## Phase 8: Authentication Setup ✅

- [x] Google Cloud Console OAuth 2.0 Client ID created
  - Authorized redirect URIs include `https://vacations.jaycurtis.org/accounts/google/login/callback/`
- [x] `google_client_id` and `google_client_secret` sealed into `k8s/secrets.yaml`
- [x] Django admin → Social Applications → Add Google provider with Client ID + Secret, assign production site
- [x] Test Google login; verify user isolation

## Phase 9: Database Backups ✅

- [x] `k8s/cronjob-backup.yaml` — 4 CronJobs applied:
  - Local pg_dump to PVC every 6 hours (7-day retention)
  - Daily S3 upload at 2am
  - Monthly S3 upload on 1st at 3am
  - Yearly S3 upload on Jan 1st at 4am
- [x] `k8s/backup-pvc.yaml` fixed: added `storageClassName: nfs-client` (required — no default SC in cluster)
- [x] PVC `vacation-planner-backup` — Bound (5Gi, nfs-client)
- [x] All 4 CronJobs created
- [x] Added `aws_access_key_id` + `aws_secret_access_key` to sealed secret (shared with unscripted-living, same `jay-curtis-backup` S3 bucket)
- [x] Test local backup: `kubectl create job --from=cronjob/vacation-planner-backup-local test-backup -n vacation-planner`

---

## Future Enhancements

### Sharing & Collaboration
- [ ] Read-only share link — generate a UUID-based public URL to share a single trip itinerary (no login required)
- [ ] Collaborator invites — allow another registered user to co-edit a vacation (read-write access without seeing all vacations)

### Budgeting & Reporting
- [ ] Currency selection per vacation — store and display with currency symbol
- [ ] Budget vs. actual chart — Chart.js bar chart per category on the vacation detail page
- [ ] Spending summary PDF export — printable trip report with budget, actual, itinerary, and expenses
- [ ] Multi-currency expenses — record expenses in local currency, convert to home currency using stored rate

### Planning Helpers
- [ ] Packing list — per-vacation checklist items (description, packed status)
- [ ] Document attachments — upload/link confirmation emails, hotel bookings, flight itineraries per vacation
- [ ] Reservation tracker — separate model for lodging/flight/car rental confirmations (confirmation #, dates, amount)
- [ ] Countdown widget — days-until-departure shown on dashboard and detail page

### UX & Polish
- [ ] Dashboard filter/sort — sort by date, status, or budget; filter by status or year
- [ ] Search across vacations — by destination, trip name, or expense description
- [ ] Duplicate vacation — copy an existing trip as a new planning template
- [ ] Mobile-optimized expense entry — quick-add expense from vacation detail without full form page
- [x] Dark mode toggle — matching unscripted-living implementation
