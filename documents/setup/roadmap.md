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

## Offline Support Options

Goal: view trips and log expenses with no internet; sync automatically when connectivity returns.

---

### Option A — Progressive Web App (PWA) ⭐ Recommended starting point

Convert the existing Django app into an installable PWA. No separate app store. Works in Chrome on Android (and iOS Safari).

**What's involved:**
- Add a `manifest.json` (app name, icon, theme color) — tells Chrome it's installable
- Add a service worker that caches the app shell (HTML, CSS, JS, Bootstrap) so pages load offline
- Use the browser's **IndexedDB** to queue new expense entries while offline
- On reconnect, a background sync job POSTs the queued expenses to Django
- Add a Django REST endpoint (or a few AJAX views) to accept the synced data

**Pros:**
- No app store, no build toolchain — just JS added to existing project
- "Add to Home Screen" on Android makes it feel like a native app
- Same codebase, same backend, same auth

**Cons:**
- Background sync not guaranteed on all Android versions/battery states
- Read-only offline (viewing cached pages) is easy; write-offline (queuing expenses) requires IndexedDB logic
- Service workers are tricky to debug; cache invalidation requires care
- iOS support is limited (no background sync at all on Safari)

**Effort estimate:** Medium — 1–2 weeks for a solid implementation

---

#### Option A Implementation Plan

##### Step 1 — Make it Installable (PWA Shell)

**Files to create:**
- `static/manifest.json` — PWA manifest declaring app name, icons, theme color, `display: "standalone"`
- `static/icons/` — app icon at 192×192 and 512×512 (PNG)
- `static/sw.js` — service worker (initially empty; registers and caches shell)

**Changes to `templates/base.html`:**
- Add `<link rel="manifest" href="/static/manifest.json">`
- Add `<meta name="theme-color" content="#2563eb">`
- Add `<meta name="apple-mobile-web-app-capable" content="yes">` (iOS)
- Register the service worker in a `<script>` block at bottom

**Milestone:** User can tap "Add to Home Screen" in Chrome → app launches full-screen, no browser chrome.

---

##### Step 2 — Offline Shell Caching (Read-Only Offline)

**Service worker strategy (Cache-First for assets, Network-First for pages):**

```
sw.js
  ├─ CACHE_NAME = "vp-v1"
  ├─ PRECACHE on install:
  │    /static/css/site.css
  │    /static/manifest.json
  │    Bootstrap CSS/JS CDN URLs
  │    /  (dashboard — so it loads if offline)
  ├─ fetch handler:
  │    static assets → Cache-First (serve from cache, update in background)
  │    navigation (HTML pages) → Network-First with cache fallback
  │    /api/* → Network-Only (never cache)
  └─ activate: delete old cache versions
```

**Django change:** Add a `Cache-Control: no-store` header to POST responses so forms don't cache.

**Milestone:** User with a loaded trip detail page can go offline and still read the itinerary.

---

##### Step 3 — Offline Write Queue (Expense Entry While Offline)

This is the core offline feature. When the user adds an expense with no connectivity:

**New file: `static/js/offline-queue.js`**
- Opens an IndexedDB database `vp-offline` with an object store `pending_expenses`
- `queueExpense(dayPk, data)` — writes `{dayPk, description, category, amount, timestamp}` to IndexedDB
- `flushQueue()` — iterates pending entries, POSTs each to `/api/expenses/` (new endpoint), deletes on success
- `getQueueCount()` — returns count of pending entries for UI badge

**New file: `static/js/sync.js`**
- Listens for `online` event → calls `flushQueue()`
- On service worker background sync event (`sync` event name: `flush-expenses`) → calls `flushQueue()`

**New Django endpoint: `planner/views.py`**
- `ExpenseCreateApiView` — accepts POST `{day_pk, description, category, amount}`, returns JSON `{id, status}`
- Requires `LoginRequiredMixin`; validates `day.vacation.user == request.user`

**New file: `planner/api_urls.py`** — wires up `/api/expenses/`

**Changes to `templates/planner/vacation_detail.html`:**
- Intercept the "Add Expense" form submission with JS
- If `navigator.onLine` → submit normally (existing flow)
- If offline → call `queueExpense()`, show toast "Saved offline — will sync when connected"

**Offline status indicator in `base.html`:**
- Small badge in navbar: "● Offline — N pending" when offline with queued items
- Clears once flushed

---

##### Step 4 — Sync Status & Conflict Handling

**Sync on reconnect:**
- `window.addEventListener('online', flushQueue)` handles the simple case
- Service worker Background Sync API (`SyncManager`) retries even if the app is closed — register `sync` tag `flush-expenses` when queuing

**Conflict model (kept simple):**
- Expenses are append-only — no conflict possible on create
- If the day was deleted while offline, the POST returns 404 → show error toast, keep entry in queue for manual review
- No multi-device edit conflicts (each expense is a new row)

**Milestone:** User logs expenses on a cruise with no signal. App shows "3 pending". When docked and WiFi restored, expenses sync automatically — or on next app open.

---

##### Step 5 — Offline Trip Detail Caching

Make trip detail pages readable offline (not just the dashboard):

**Service worker `fetch` handler:**
- On successful navigation to `/trips/<pk>/` → cache the response under key `vp-trips-<pk>`
- Cache-First with 24-hour max-age for trip detail pages
- Cache is refreshed on every successful online load

**Explicit "Save for Offline" button on trip detail:**
- `<button id="save-offline">Save for Offline</button>`
- On click: fetches the page again and writes to cache; shows confirmation toast

---

##### Step 6 — iOS Workarounds

Background Sync API is not available on iOS Safari. Workarounds:

- On `window.addEventListener('online')`, immediately call `flushQueue()` — this works when the app is open
- Show "Connect to sync" prompt if user opens app with pending items and connectivity
- Accept that background sync (app closed, reconnects) will not fire on iOS — document this limitation

---

##### Implementation Checklist

- [ ] Create `static/manifest.json` and app icons
- [ ] Register service worker in `base.html`
- [ ] Write `static/sw.js` — precache shell, network-first navigation
- [ ] Add `page` logger and `offline-queue.js` with IndexedDB queue
- [ ] Add `ExpenseCreateApiView` at `/api/expenses/` with JSON response
- [ ] Intercept Add Expense form submission — offline path queues, online path submits normally
- [ ] Offline status badge in navbar
- [ ] Background sync registration (`SyncManager`) in service worker
- [ ] Trip detail page caching + "Save for Offline" button
- [ ] Test on Android Chrome: install, go airplane mode, log expense, reconnect, verify sync
- [ ] Document iOS limitation in roadmap

---

### Option B — Capacitor Wrapper (Web → Android APK)

Use [Capacitor](https://capacitorjs.com/) (by Ionic) to wrap the existing web frontend into a native Android APK. The app runs in a WebView but has access to native device APIs.

**What's involved:**
- Install Capacitor, point it at the production URL or a local bundle
- Bundle static assets into the APK so the shell loads offline
- Use Capacitor's SQLite plugin for local storage instead of IndexedDB
- Sync logic is the same as PWA but runs inside the native container

**Pros:**
- Ships as a real APK — can sideload or publish to Play Store
- More reliable offline storage than browser IndexedDB (SQLite)
- Can add push notifications, camera (receipt photos), etc. later

**Cons:**
- Adds a build step: Android SDK, Java, Gradle required
- WebView-based apps feel slightly less native than React Native
- Auth (Google OAuth) requires extra Capacitor plugin configuration

**Effort estimate:** Medium-High — 2–3 weeks; most time is Capacitor setup and auth wiring

---

### Option C — React Native / Expo App (Full Native)

Rewrite the frontend as a React Native app backed by the same Django API (add Django REST Framework). True native UI, best performance.

**What's involved:**
- Add `djangorestframework` + token/JWT auth to the backend
- Expose REST endpoints: trips, days, expenses (CRUD)
- Build React Native app with Expo; use SQLite (via `expo-sqlite`) as local DB
- Sync layer: on login/reconnect, pull server state; on expense add, write local then push when online
- Conflict resolution needed if data is edited on multiple devices

**Pros:**
- Best UX — native components, smooth animations
- Full offline: local SQLite mirrors server, full read/write capability
- Can publish to Play Store and App Store

**Cons:**
- Largest effort — essentially building a second app
- Requires maintaining both the Django web app and the RN app
- Conflict resolution (offline edits vs. server state) is genuinely complex

**Effort estimate:** High — 4–6+ weeks

---

### Option D — Offline-First with Dexie.js (Enhanced PWA)

Same as Option A but use [Dexie.js](https://dexie.org/) as a structured IndexedDB wrapper instead of raw service worker caching. Dexie makes offline-first patterns much cleaner.

**What's involved:**
- Service worker caches pages/assets
- Dexie.js manages a local trip/expense store in the browser
- All writes go to Dexie first, then sync to Django via a simple sync API
- A sync status indicator shows pending/synced state per expense

**Pros:**
- Cleaner code than raw IndexedDB; good documentation
- Full offline read and write
- Still just a web app — no build toolchain

**Cons:**
- Still browser-based; same iOS/background-sync limitations as Option A
- Sync logic (handling deletes, edits, and conflicts) adds complexity

**Effort estimate:** Medium — 2–3 weeks

---

### Recommendation

| Option | Effort | Android feel | iOS | App Store |
|--------|--------|-------------|-----|-----------|
| A — PWA | Low-Med | Good (installable) | Partial | No |
| B — Capacitor | Med-High | Good (native container) | Yes | Optional |
| C — React Native | High | Excellent | Yes | Yes |
| D — Dexie PWA | Medium | Good | Partial | No |

**Start with Option A (PWA).** It delivers 80% of the offline value for 20% of the effort — installable on Android home screen, service worker caches pages, IndexedDB queues expenses. If the PWA offline limitations become a real pain point (especially iOS), Option B (Capacitor) is the natural upgrade path since it reuses all the existing HTML/CSS/JS.

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
