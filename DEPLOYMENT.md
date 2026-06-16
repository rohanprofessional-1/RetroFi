# RetroFi — Public Deployment Guide

Deploy RetroFi publicly using **GCP Cloud Run** (backend) and **Firebase Hosting** (frontend).

## Architecture

```
Browser → Firebase Hosting (React SPA)
              ↓
         Cloud Run (FastAPI backend)
              ↓
    RentCast · Google Maps/Solar · Anthropic APIs
```

## Prerequisites

- [Google Cloud SDK](https://cloud.google.com/sdk/docs/install) (`gcloud`)
- [Docker](https://docs.docker.com/get-docker/) (for manual image builds)
- [Node.js 20+](https://nodejs.org/) and npm
- [Firebase CLI](https://firebase.google.com/docs/cli): `npm install -g firebase-tools`
- A GCP project with billing enabled
- API keys for RentCast, Google Maps/Solar, and Anthropic

## Set variables

Run these in your terminal and replace placeholders with your values:

```bash
export PROJECT_ID=your-gcp-project-id
export REGION=us-east1
export REPO=retrofi-atl
# Full Artifact Registry path (include :latest for deploy)
export BACKEND_IMAGE=us-east1-docker.pkg.dev/$PROJECT_ID/$REPO/backend:latest
```

---

## 1. One-time GCP setup

```bash
# Auth & project
gcloud auth login
gcloud config set project $PROJECT_ID

# Enable APIs
gcloud services enable \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  artifactregistry.googleapis.com \
  secretmanager.googleapis.com \
  firebase.googleapis.com \
  firebasehosting.googleapis.com

# Docker image registry
gcloud artifacts repositories create $REPO \
  --repository-format=docker \
  --location=$REGION \
  --description="RetroFi Docker images" \
  2>/dev/null || true

gcloud auth configure-docker us-east1-docker.pkg.dev
```

---

## 2. Store secrets (one time)

Store API keys in Secret Manager. **Never commit keys to git.**

```bash
echo -n "YOUR_RENTCAST_API_KEY" | gcloud secrets create rentcast-api-key --data-file=-
echo -n "YOUR_GOOGLE_API_KEY"   | gcloud secrets create google-api-key --data-file=-
echo -n "YOUR_ANTHROPIC_API_KEY" | gcloud secrets create anthropic-api-key --data-file=-
```

Optional (NREL utility rates):

```bash
echo -n "YOUR_NREL_API_KEY" | gcloud secrets create nrel-api-key --data-file=-
```

If a secret already exists, add a new version instead:

```bash
echo -n "YOUR_KEY" | gcloud secrets versions add SECRET_NAME --data-file=-
```

### Grant Cloud Run access to secrets

Cloud Run runs as a service account that must be allowed to read secrets. **Run this before the first deploy** (or you'll get `Permission denied on secret`).

```bash
# Default Cloud Run service account (replace with your project number)
export PROJECT_NUMBER=$(gcloud projects describe $PROJECT_ID --format='value(projectNumber)')
export RUN_SA="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"

# Grant access to each secret (use your actual secret names)
for SECRET in RENTCAST_API_KEY GOOGLE_API_KEY ANTHROPIC_API_KEY; do
  gcloud secrets add-iam-policy-binding "$SECRET" \
    --member="serviceAccount:${RUN_SA}" \
    --role="roles/secretmanager.secretAccessor"
done
```

Or grant access to all secrets in the project at once:

```bash
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:${RUN_SA}" \
  --role="roles/secretmanager.secretAccessor"
```

---

## 3. Deploy backend to Cloud Run

From the repository root.

### Option A — Build and push with Docker

```bash
# Cloud Run requires linux/amd64 (required on Apple Silicon Macs)
docker build --platform linux/amd64 -t $BACKEND_IMAGE ./backend
docker push $BACKEND_IMAGE

gcloud run deploy retrofi-backend \
  --image $BACKEND_IMAGE \
  --region $REGION \
  --allow-unauthenticated \
  --set-secrets "RENTCAST_API_KEY=RENTCAST_API_KEY:latest,GOOGLE_API_KEY=GOOGLE_API_KEY:latest,ANTHROPIC_API_KEY=ANTHROPIC_API_KEY:latest" \
  --set-env-vars "FRONTEND_URL=https://${PROJECT_ID}.web.app,ANTHROPIC_MODEL=claude-3-5-haiku-latest" \
  --memory 512Mi \
  --cpu 1 \
  --min-instances 0 \
  --max-instances 5 \
  --timeout 60
```

### Option B — Build and push with Docker Compose

Docker Compose can tag and push images to Artifact Registry when a service has an `image:` name pointing at your registry. Use `docker-compose.deploy.yml` (separate from the local dev `docker-compose.yml`).

```bash
# Authenticate Docker with Artifact Registry (one time)
gcloud auth configure-docker us-east1-docker.pkg.dev

# BACKEND_IMAGE must already be set (see "Set variables" above)

# Build and push only the backend service
docker compose -f docker-compose.deploy.yml build backend
docker compose -f docker-compose.deploy.yml push backend

# Deploy the pushed image to Cloud Run
gcloud run deploy retrofi-backend \
  --image $BACKEND_IMAGE \
  --region $REGION \
  --allow-unauthenticated \
  --set-secrets "RENTCAST_API_KEY=rentcast-api-key:latest,GOOGLE_API_KEY=google-api-key:latest,ANTHROPIC_API_KEY=anthropic-api-key:latest" \
  --set-env-vars "FRONTEND_URL=https://${PROJECT_ID}.web.app,ANTHROPIC_MODEL=claude-3-5-haiku-latest" \
  --memory 512Mi \
  --cpu 1 \
  --min-instances 0 \
  --max-instances 5 \
  --timeout 60
```

Optional: tag with a git commit SHA instead of `latest`:

```bash
export BACKEND_IMAGE=us-east1-docker.pkg.dev/$PROJECT_ID/$REPO/backend:$(git rev-parse --short HEAD)
docker compose -f docker-compose.deploy.yml build backend
docker compose -f docker-compose.deploy.yml push backend
```

> **Note:** `docker compose push` only uploads images — it does not deploy to Cloud Run. You still run `gcloud run deploy` afterward. The local dev stack (`docker compose up`) is unchanged; use `-f docker-compose.deploy.yml` only for registry pushes.

### Option C — Build from source (no local Docker push)

```bash
cd backend

gcloud run deploy retrofi-backend \
  --source . \
  --region $REGION \
  --allow-unauthenticated \
  --set-secrets "RENTCAST_API_KEY=rentcast-api-key:latest,GOOGLE_API_KEY=google-api-key:latest,ANTHROPIC_API_KEY=anthropic-api-key:latest" \
  --set-env-vars "FRONTEND_URL=https://${PROJECT_ID}.web.app,ANTHROPIC_MODEL=claude-3-5-haiku-latest" \
  --memory 512Mi \
  --cpu 1 \
  --timeout 60
```

### Save the backend URL

```bash
export BACKEND_URL=$(gcloud run services describe retrofi-backend \
  --region $REGION \
  --format='value(status.url)')

echo $BACKEND_URL
```

### Verify backend

```bash
curl "$BACKEND_URL/health"
curl "$BACKEND_URL/"
```

Expected health response:

```json
{"status":"healthy"}
```

---

## 4. Deploy frontend to Firebase Hosting

### Enable Firebase Hosting (one time)

Your GCP project must have a Firebase Hosting **site** before deploy works. If `firebase hosting:sites:list` shows an empty table, create one:

```bash
firebase hosting:sites:create $PROJECT_ID --project $PROJECT_ID
```

`firebase.json` includes `"site": "retrofi-atl"` (must match the site ID above).

### Build and deploy

```bash
firebase login

# From repository root — link GCP project (one time)
cp .firebaserc.example .firebaserc
# Edit .firebaserc and set "default" to your PROJECT_ID

# Point frontend at the public backend (committed for Cloud Build + production builds)
cp frontend/.env.production.example frontend/.env.production
# Edit VITE_API_BASE_URL if your Cloud Run URL differs, then commit .env.production

# Build and deploy
cd frontend
npm ci
npm run build
cd ..
firebase deploy --only hosting --project $PROJECT_ID
```

Public URL: **https://`$PROJECT_ID`.web.app**

---

## 5. Post-deploy verification

### Backend checks

```bash
curl "$BACKEND_URL/health"

curl -X POST "$BACKEND_URL/property-lookup" \
  -H "Content-Type: application/json" \
  -d '{"address":"123 Peachtree St NE, Atlanta, GA 30308"}'

gcloud run services logs read retrofi-backend --region $REGION --limit 30
```

### Frontend checks

1. Open `https://$PROJECT_ID.web.app`
2. Open browser DevTools → **Network**
3. Confirm API requests go to `$BACKEND_URL`
4. Walk through: address lookup → questionnaire → dashboard → action steps

### Common HTTP status codes

| Status | Endpoint | Likely cause |
|--------|----------|--------------|
| 502 | `/property-lookup` | RentCast API error (often invalid `RENTCAST_API_KEY`) |
| 404 | `/property-lookup` | Address not found, or `RENTCAST_API_KEY` not set |
| CORS error | Any | `FRONTEND_URL` on Cloud Run does not match your Firebase URL |

---

## 6. Fix CORS (if the browser blocks API calls)

The backend only allows browser requests from origins listed in `FRONTEND_URL` (plus localhost for dev). Firebase Hosting uses `https://PROJECT_ID.web.app`.

### Set the production frontend URL on Cloud Run

```bash
gcloud run services update retrofi-backend \
  --region $REGION \
  --project $PROJECT_ID \
  --set-env-vars "FRONTEND_URL=https://${PROJECT_ID}.web.app"
```

This also allows `https://${PROJECT_ID}.firebaseapp.com` automatically.

### Redeploy after CORS code changes

If you changed `backend/main.py`, redeploy the backend image (env vars alone are not enough until a new revision is running):

```bash
cd backend
gcloud run deploy retrofi-backend --source . --region $REGION --project $PROJECT_ID \
  --allow-unauthenticated \
  --set-secrets "RENTCAST_API_KEY=RENTCAST_API_KEY:latest,GOOGLE_API_KEY=GOOGLE_API_KEY:latest,ANTHROPIC_API_KEY=ANTHROPIC_API_KEY:latest" \
  --set-env-vars "FRONTEND_URL=https://${PROJECT_ID}.web.app,ANTHROPIC_MODEL=claude-3-5-haiku-latest"
```

### Verify CORS

```bash
curl -s -D - "https://YOUR_BACKEND_URL/config/google-maps" \
  -H "Origin: https://${PROJECT_ID}.web.app" -o /dev/null | grep -i access-control
```

You should see `access-control-allow-origin: https://PROJECT_ID.web.app`.

Then hard-refresh the browser (Cmd+Shift+R) on `https://${PROJECT_ID}.web.app`.

---

## 7. CI/CD with Cloud Build (auto-deploy on push to `main`)

`cloudbuild.yaml` runs automatically when code is **pushed or merged to `main`**, after you create the trigger once.

### What the pipeline does

Matches the manual deployment workflow:

1. **Backend** — `docker build` (linux/amd64) → push to Artifact Registry → `gcloud run deploy` with secrets + `FRONTEND_URL`
2. **Frontend** — `npm run build` (reads `frontend/.env.production`) → `firebase deploy --only hosting`

### Frontend env: `frontend/.env.production`

Cloud Build cannot read gitignored `frontend/.env`. Production builds use the **committed** file:

```bash
# frontend/.env.production (committed — public backend URL only)
VITE_API_BASE_URL=https://retrofi-backend-836379828951.us-east1.run.app
```

Vite loads `.env.production` automatically on `npm run build`. Update this file when your Cloud Run URL changes, then commit it.

Local dev continues to use gitignored `frontend/.env`.

### One-time setup

```bash
# 1. Firebase CI token for hosting deploys
firebase login:ci
echo -n "YOUR_FIREBASE_CI_TOKEN" | gcloud secrets create firebase-token --data-file=- --project=retrofi-atl

# 2. Create trigger + IAM permissions
./scripts/setup-cloud-build-trigger.sh
```

If trigger creation fails, connect GitHub first:
[Cloud Build → Connect repository](https://console.cloud.google.com/cloud-build/triggers;region=us-east1/connect?project=retrofi-atl)

### When it runs

| Event | Triggers deploy? |
|-------|------------------|
| Push to `main` | Yes |
| Merge PR into `main` | Yes (merge = push to main) |
| Push to other branches | No |
| Local commits only | No |

### Manual run (without pushing)

```bash
gcloud builds submit --config=cloudbuild.yaml --region=us-east1 --project=retrofi-atl .
```

---

## 8. Local development (Docker Compose)

For local testing before public deploy:

```bash
# Ensure backend/.env exists with your API keys
docker compose up --build
```

| Service  | URL |
|----------|-----|
| Frontend | http://localhost:5173 |
| Backend  | http://localhost:8000 |

---

## Environment variables reference

| Variable | Where | Purpose |
|----------|-------|---------|
| `RENTCAST_API_KEY` | Secret Manager → Cloud Run | Property lookup |
| `GOOGLE_API_KEY` | Secret Manager → Cloud Run | Maps, Solar API, contractors |
| `ANTHROPIC_API_KEY` | Secret Manager → Cloud Run | LLM summaries and action steps |
| `ANTHROPIC_MODEL` | Cloud Run env var | Anthropic model name |
| `FRONTEND_URL` | Cloud Run env var | CORS allowlist (Firebase URL) |
| `VITE_API_BASE_URL` | `frontend/.env.production` (committed) | Backend URL for production frontend builds + Cloud Build |

---

## Deployment order (summary)

1. GCP project, APIs, Artifact Registry
2. Secrets in Secret Manager
3. **Backend** → Cloud Run → save `$BACKEND_URL`
4. **Frontend** → build with `VITE_API_BASE_URL=$BACKEND_URL` → Firebase deploy
5. Smoke-test the public URL

---

## Troubleshooting

### `Permission denied on secret` on deploy

Cloud Run's service account cannot read Secret Manager values yet. Grant **Secret Accessor** (see [Grant Cloud Run access to secrets](#grant-cloud-run-access-to-secrets)), then redeploy:

```bash
gcloud run deploy retrofi-backend --image $BACKEND_IMAGE --region $REGION ...
```

### `403 The caller does not have permission` on `firebase hosting:sites:create`

The GCP project exists, but **Firebase is not fully enabled** on it, or your Google account lacks Hosting permissions.

**Fix via Firebase Console (easiest):**

1. Open [Firebase Console](https://console.firebase.google.com/)
2. Click **Add project** → choose **Add Firebase to an existing Google Cloud project**
3. Select `retrofi-atl` and finish setup
4. Go to **Build → Hosting → Get started** (this provisions the default site)

**Fix via CLI (project owner):**

```bash
gcloud services enable firebase.googleapis.com firebasehosting.googleapis.com --project=retrofi-atl

gcloud projects add-iam-policy-binding retrofi-atl \
  --member="user:YOUR_EMAIL@gmail.com" \
  --role="roles/firebase.admin"
```

Then re-auth and create the site:

```bash
firebase login --reauth
firebase hosting:sites:create retrofi-atl --project retrofi-atl
```

> Run commands **one at a time** — do not paste comment lines (`# ...`) into zsh.

### `no site name or target name` on `firebase deploy`

Firebase Hosting has no site provisioned for the project yet. Create one, then redeploy:

```bash
firebase hosting:sites:create $PROJECT_ID --project $PROJECT_ID
firebase deploy --only hosting --project $PROJECT_ID
```

### `must support amd64/linux` on deploy

You built the image on an **Apple Silicon Mac** (arm64). Cloud Run only runs **linux/amd64** images.

Rebuild and push with the correct platform, then redeploy:

```bash
docker build --platform linux/amd64 -t $BACKEND_IMAGE ./backend
docker push $BACKEND_IMAGE
gcloud run deploy retrofi-backend --image $BACKEND_IMAGE --region $REGION ...
```

Or with Docker Compose (`docker-compose.deploy.yml` sets `platform: linux/amd64`):

```bash
docker compose -f docker-compose.deploy.yml build backend
docker compose -f docker-compose.deploy.yml push backend
```

---

## Notes

- **SQLite / ChromaDB**: Cloud Run containers have ephemeral filesystems. Seed JSON in `backend/data/` is included in the Docker image; `database.db` and `backend/data/chroma/` do not persist across restarts.
- **Secrets**: Rotate any API keys that were ever committed to git or shared in chat.
- **Region**: Default is `us-east1` (close to Atlanta). Change `REGION` if you prefer another region.

## Related files

| File | Purpose |
|------|---------|
| `backend/Dockerfile` | Backend container image |
| `frontend/Dockerfile` | Optional nginx-based frontend image |
| `docker-compose.yml` | Local full-stack development |
| `docker-compose.deploy.yml` | Build and push images to Artifact Registry |
| `firebase.json` | Firebase Hosting SPA config |
| `.firebaserc.example` | Template for Firebase project link |
| `frontend/.env.production.example` | Template for production API URL |
| `cloudbuild.yaml` | CI/CD pipeline config |
| `scripts/setup-cloud-build-trigger.sh` | One-time trigger + IAM setup |
