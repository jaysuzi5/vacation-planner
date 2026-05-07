# Vacation Planner

Private per-user vacation planning and expense tracking app. Plan trips, set budgets by category, build daily itineraries, and log expenses — actuals roll up automatically from what you spend each day.

## Features

- **Google OAuth login** — sign in with Google; each user sees only their own data
- **Trip lifecycle** — In Review → Booked → Taken
- **Budget vs. actual** — set budgets by category (airfare, lodging, meals, excursions, gas, cruise, car rental, misc); actuals computed from logged daily expenses
- **Daily itinerary** — per-day lodging, excursion notes, and line-item expenses
- **Rating** — score In Review trips 1–10 to prioritize what to book next
- **Dashboard** — Booked trips as cards; In Review and Taken as sortable tables
- **Dark mode** — toggle in navbar, persists via localStorage

## Stack

- Python 3.12 / Django 6.0
- PostgreSQL (shared k8s cluster)
- django-allauth (Google OAuth)
- Bootstrap 5.3 + custom CSS
- WhiteNoise (static files)
- OpenTelemetry (OTLP traces/metrics/logs)
- Docker + Kubernetes (`vacation-planner` namespace)
- uv (package manager)

## Local Development

```bash
# Install dependencies
uv sync

# Copy and fill in environment variables
cp .env.example .env

# Run migrations
uv run python manage.py migrate

# Create superuser
uv run python manage.py createsuperuser

# Start dev server
uv run python manage.py runserver
```

Environment variables are in `.env` (gitignored). See `.env.example` for required keys. The PostgreSQL instance is at `192.168.86.201:30004` (k8s NodePort).

## Production Deployment

```bash
# Build and push multi-arch image
docker buildx build --platform linux/amd64,linux/arm64 -t jaysuzi5/vacation-planner:latest --push .

# Apply k8s manifests
kubectl apply -f k8s/secrets.yaml
kubectl apply -f k8s/deployment.yaml
kubectl apply -f k8s/backup-pvc.yaml
kubectl apply -f k8s/cronjob-backup.yaml

# Restart deployment
kubectl rollout restart deployment vacation-planner -n vacation-planner

# Check status
kubectl get all -n vacation-planner
```

**Live URL:** https://vacations.jaycurtis.org  
**Namespace:** `vacation-planner`  
**Secrets:** Managed as SealedSecrets in `k8s/secrets.yaml` — never commit plain-text credentials.

## Project Structure

```
config/         Django project config (settings, urls, wsgi, middleware)
planner/        Application (models, views, forms, urls, admin, migrations)
templates/      HTML templates (base + planner/ + account/)
static/css/     site.css — custom styles + dark mode
k8s/            Kubernetes manifests
documents/      Project docs and roadmap
```

## Data Model

- **Vacation** — trip with location, dates, status, budget per category, rating, notes
- **Day** — daily itinerary entry (lodging, excursion, notes) linked to a Vacation
- **Expense** — line-item spend (description, category, amount) linked to a Day

All views enforce `request.user == vacation.user` — no cross-user data access.
