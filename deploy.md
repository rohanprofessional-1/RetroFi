RetroFi ATL — GCP Deployment Plan
Deploy the RetroFi ATL application to Google Cloud Platform using Cloud Run (backend), Firebase Hosting (frontend), Vertex AI (LLM), and Cloud Build (CI/CD).

Architecture Overview
User Browser
Firebase Hosting(React SPA + CDN)
Cloud Run(FastAPI Backend)
Managed Qwen API(e.g., Together AI)
Secret Manager(API Keys)
External APIs(RentCast, Google Solar/Maps)
GitHub Repo
Cloud Build(CI/CD Trigger)
User Review Required
IMPORTANT

API Keys in Production: Your .env currently has raw API keys for GOOGLE_API_KEY and RENTCAST_API_KEY. These will be moved to GCP Secret Manager alongside your new Managed Qwen API Key.

WARNING

Database: You're currently using a local SQLite file (database.db). SQLite does not work in Cloud Run because the container filesystem is ephemeral — data is lost on every cold start. See Open Questions below for options.

CAUTION

ChromaDB: You have a local ChromaDB vector store in backend/data/chroma/. This also won't persist in Cloud Run. If this is critical to your app's functionality, it will need a persistent solution.

Open Questions
Database persistence — Your SQLite DB and ChromaDB store won't survive Cloud Run restarts. Options:

Cloud SQL (Postgres) — ~$7-10/mo for the smallest instance. Best for production.
Cloud Storage — Upload/download the SQLite file on startup/shutdown. Hacky but cheap.
Skip it for now — If the DB is just development scaffolding and not critical to the deployed app.
Custom domain — Do you have a domain name (e.g., retrofi-atl.com)? Firebase Hosting and Cloud Run both support custom domains with free SSL.

Authentication — Is this app publicly accessible, or do you want to gate it behind user login eventually?

Region — I'll default to us-east1 (South Carolina) since your target audience is Atlanta. Sound right?

Phase 1: GCP Project Setup
1.1 Create or select a GCP project
bash

# Install gcloud CLI if not already installed
# https://cloud.google.com/sdk/docs/install
# Login and set project
gcloud auth login
gcloud projects create retrofi-atl --name="RetroFi ATL"
gcloud config set project retrofi-atl
1.2 Enable billing
Link a billing account via the GCP Console.

1.3 Enable required APIs
bash

gcloud services enable \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  artifactregistry.googleapis.com \
  aiplatform.googleapis.com \
  secretmanager.googleapis.com \
  firebasehosting.googleapis.com
1.4 Create an Artifact Registry repository
bash

gcloud artifacts repositories create retrofi-atl \
  --repository-format=docker \
  --location=us-east1 \
  --description="RetroFi ATL Docker images"
Phase 2: Switch LLM to Managed Qwen API
To use Qwen in production without running it yourself on Cloud Run, we will point your existing LLM integration to a managed provider (like Together AI or DeepInfra) that hosts the model via an OpenAI-compatible API.

2.1 Update the LLM summary service
We will update the _call_local_llm function to support an Authorization header so it can authenticate with external providers.

[MODIFY] 
llm_summary.py
Add support for LLM_API_KEY:

python

headers = {
        "Content-Type": "application/json",
    }
    
    api_key, _ = _config_value("LLM_API_KEY")
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
        
    request = Request(
        endpoint,
        data=json.dumps(body).encode("utf-8"),
        headers=headers,
        method="POST",
    )
No new dependencies are required because you are already using Python's built-in urllib to make the HTTP requests!

Phase 3: Backend — Dockerize & Deploy to Cloud Run
3.1 Create the Dockerfile
[NEW] backend/Dockerfile
dockerfile

FROM python:3.11-slim
WORKDIR /app
# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
# Copy application code
COPY . .
# Cloud Run injects PORT env var (default 8080)
ENV PORT=8080
# Run with uvicorn (no --reload in production)
CMD exec uvicorn main:app --host 0.0.0.0 --port ${PORT} --workers 2
3.2 Create .dockerignore
[NEW] backend/.dockerignore

venv/
__pycache__/
.env
*.db
data/chroma/
.pytest_cache/
tests/
3.3 Store secrets in Secret Manager
bash

# Store your API keys as secrets
echo -n "AIzaSyAtiSST5Yr3EAXhqe1m65mQeWqPMbiYNqw" | \
  gcloud secrets create google-api-key --data-file=-
echo -n "9bc3f8bba5304757ae2e4fa272e847b5" | \
  gcloud secrets create rentcast-api-key --data-file=-
echo -n "YOUR_QWEN_API_KEY" | \
  gcloud secrets create qwen-api-key --data-file=-
# Grant the service account access to read secrets
gcloud secrets add-iam-policy-binding google-api-key \
  --member="serviceAccount:retrofi-backend@retrofi-atl.iam.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor"
gcloud secrets add-iam-policy-binding rentcast-api-key \
  --member="serviceAccount:retrofi-backend@retrofi-atl.iam.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor"
gcloud secrets add-iam-policy-binding qwen-api-key \
  --member="serviceAccount:retrofi-backend@retrofi-atl.iam.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor"
WARNING

Rotate your API keys before deploying to production. Your current keys have been exposed in the .env file and conversation history. Generate new keys for Google API and RentCast after deployment.

3.4 Update CORS for production
[MODIFY] 
main.py
Update the CORS origins to include your production frontend URL:

diff

app.add_middleware(
     CORSMiddleware,
     allow_origins=[
         "http://127.0.0.1:5173",
         "http://localhost:5173",
         "http://localhost:5174",
+        os.getenv("FRONTEND_URL", ""),         # e.g., https://retrofi-atl.web.app
     ],
     allow_credentials=True,
     allow_methods=["*"],
     allow_headers=["*"],
 )
3.5 Deploy to Cloud Run
bash

cd backend
# Build and deploy in one command
gcloud run deploy retrofi-backend \
  --source . \
  --region us-east1 \
  --service-account retrofi-backend@retrofi-atl.iam.gserviceaccount.com \
  --allow-unauthenticated \
  --set-secrets "GOOGLE_API_KEY=google-api-key:latest,RENTCAST_API_KEY=rentcast-api-key:latest,LLM_API_KEY=qwen-api-key:latest" \
  --set-env-vars "LLM_PROVIDER=managed_qwen,LOCAL_LLM_BASE_URL=https://api.together.xyz,LOCAL_LLM_MODEL=Qwen/Qwen2.5-7B-Instruct,GCP_PROJECT_ID=retrofi-atl,FRONTEND_URL=https://retrofi-atl.web.app" \
  --memory 512Mi \
  --cpu 1 \
  --min-instances 0 \
  --max-instances 5 \
  --timeout 60
After deployment, Cloud Run gives you a URL like https://retrofi-backend-xxxxx-ue.a.run.app. Save this — the frontend needs it.

Phase 4: Frontend — Build & Deploy to Firebase Hosting
Firebase Hosting is the simplest option for an SPA — it handles CDN, SSL, and SPA routing (rewrites) out of the box.

4.1 Install Firebase CLI
bash

npm install -g firebase-tools
firebase login
4.2 Initialize Firebase in the project root
bash

cd /Users/rohannair/Desktop/Shenanigans/retrofi-atl
firebase init hosting
When prompted:

Project: Select your retrofi-atl GCP project
Public directory: frontend/dist
Single-page app: Yes (rewrites all URLs to /index.html)
GitHub deploys: Skip for now (we'll use Cloud Build)
This creates a firebase.json in the project root.

4.3 Configure the API base URL for production
[NEW] frontend/.env.production

VITE_API_BASE_URL=https://retrofi-backend-xxxxx-ue.a.run.app
NOTE

Replace the URL above with the actual Cloud Run service URL from Phase 3.5. The frontend's 
api.js
 already reads VITE_API_BASE_URL and falls back to http://127.0.0.1:8000 for local dev — no code changes needed.

4.4 Build and deploy
bash

cd frontend
npm run build     # Creates dist/
cd ..
firebase deploy --only hosting
Your app is now live at https://retrofi-atl.web.app (or your custom domain).

Phase 5: CI/CD with Cloud Build + GitHub
5.1 Connect your GitHub repo
bash

# In the GCP Console: Cloud Build > Repositories > Connect Repository
# Or use the CLI:
gcloud builds repositories create retrofi-atl-repo \
  --remote-uri=https://github.com/YOUR_USERNAME/retrofi-atl \
  --connection=github-connection \
  --region=us-east1
Alternatively, use the Cloud Build console UI — it's easier for the initial GitHub app installation.

5.2 Create the Cloud Build config
[NEW] cloudbuild.yaml (project root)
yaml

steps:
  # ── Backend: Build, push, deploy to Cloud Run ──
  - name: 'gcr.io/cloud-builders/docker'
    args:
      - 'build'
      - '-t'
      - 'us-east1-docker.pkg.dev/$PROJECT_ID/retrofi-atl/backend:$COMMIT_SHA'
      - '-f'
      - 'backend/Dockerfile'
      - 'backend'
    id: 'build-backend'
  - name: 'gcr.io/cloud-builders/docker'
    args:
      - 'push'
      - 'us-east1-docker.pkg.dev/$PROJECT_ID/retrofi-atl/backend:$COMMIT_SHA'
    id: 'push-backend'
    waitFor: ['build-backend']
  - name: 'gcr.io/cloud-builders/gcloud'
    args:
      - 'run'
      - 'deploy'
      - 'retrofi-backend'
      - '--image'
      - 'us-east1-docker.pkg.dev/$PROJECT_ID/retrofi-atl/backend:$COMMIT_SHA'
      - '--region'
      - 'us-east1'
      - '--allow-unauthenticated'
    id: 'deploy-backend'
    waitFor: ['push-backend']
  # ── Frontend: Install, build, deploy to Firebase ──
  - name: 'node:20'
    entrypoint: 'bash'
    args:
      - '-c'
      - |
        cd frontend
        npm ci
        npm run build
    id: 'build-frontend'
  - name: 'us-east1-docker.pkg.dev/$PROJECT_ID/retrofi-atl/firebase-deployer'
    entrypoint: 'bash'
    args:
      - '-c'
      - 'firebase deploy --only hosting --project $PROJECT_ID'
    id: 'deploy-frontend'
    waitFor: ['build-frontend']
options:
  logging: CLOUD_LOGGING_ONLY
NOTE

For the Firebase deploy step, you'll need a custom builder image with firebase-tools installed, or you can use the community builder gcr.io/cloud-builders/firebase. See Cloud Build community builders.

5.3 Create the trigger
bash

gcloud builds triggers create github \
  --name="deploy-retrofi-atl" \
  --repo-name="retrofi-atl" \
  --repo-owner="YOUR_GITHUB_USERNAME" \
  --branch-pattern="^main$" \
  --build-config="cloudbuild.yaml" \
  --region=us-east1
5.4 Grant Cloud Build permissions
bash

# Get the Cloud Build service account number
PROJECT_NUMBER=$(gcloud projects describe retrofi-atl --format='value(projectNumber)')
# Grant Cloud Run Developer
gcloud projects add-iam-policy-binding retrofi-atl \
  --member="serviceAccount:${PROJECT_NUMBER}@cloudbuild.gserviceaccount.com" \
  --role="roles/run.developer"
# Grant Artifact Registry Writer
gcloud projects add-iam-policy-binding retrofi-atl \
  --member="serviceAccount:${PROJECT_NUMBER}@cloudbuild.gserviceaccount.com" \
  --role="roles/artifactregistry.writer"
# Grant ability to act as the Cloud Run service account
gcloud iam service-accounts add-iam-policy-binding \
  retrofi-backend@retrofi-atl.iam.gserviceaccount.com \
  --member="serviceAccount:${PROJECT_NUMBER}@cloudbuild.gserviceaccount.com" \
  --role="roles/iam.serviceAccountUser"
Phase 6: Production Hardening
6.1 Environment variables summary
Variable	Where	Value
LLM_PROVIDER	Cloud Run env var	managed_qwen
LOCAL_LLM_BASE_URL	Cloud Run env var	https://api.together.xyz (example)
LOCAL_LLM_MODEL	Cloud Run env var	Qwen/Qwen2.5-7B-Instruct (example)
LLM_API_KEY	Secret Manager → Cloud Run	(your provider key)
GOOGLE_API_KEY	Secret Manager → Cloud Run	(your Google Maps/Solar key)
RENTCAST_API_KEY	Secret Manager → Cloud Run	(your RentCast key)
FRONTEND_URL	Cloud Run env var	https://retrofi-atl.web.app
VITE_API_BASE_URL	Frontend .env.production	Cloud Run service URL
6.2 Add health check endpoint
[MODIFY] 
main.py
python

@app.get("/health")
def health_check():
    return {"status": "healthy"}
Use this as the Cloud Run startup probe.

6.3 Data files
Your backend/data/ directory contains seed JSON files that the app needs at runtime. These are included in the Docker image via COPY . . in the Dockerfile, so they'll be available. However, the ChromaDB directory and SQLite database will not persist between container restarts.

Cost Estimate (Monthly)
Service	Estimated Cost
Cloud Run (backend)	$0–5 (generous free tier: 2M requests/mo free)
Firebase Hosting (frontend)	$0 (free tier: 10GB storage, 360MB/day transfer)
Vertex AI (Gemini 2.5 Flash)	$0–3 (pay per token, very cheap for short summaries)
Secret Manager	$0 (free tier: 10K access operations/mo)
Artifact Registry	$0–1 (0.10/GB storage)
Cloud Build	$0 (free tier: 120 build-minutes/day)
Total	~$0–10/mo at low-moderate traffic
Verification Plan
After Backend Deployment
bash

# Test the health endpoint
curl https://retrofi-backend-xxxxx-ue.a.run.app/health
# Test the root endpoint
curl https://retrofi-backend-xxxxx-ue.a.run.app/
# Check logs
gcloud run services logs read retrofi-backend --region us-east1 --limit 50
After Frontend Deployment
Visit https://retrofi-atl.web.app in browser
Enter an address and verify the full flow works end-to-end
Check browser dev tools Network tab to confirm API calls go to Cloud Run URL
After CI/CD Setup
Push a small commit to main and verify Cloud Build triggers automatically
Check build logs in GCP Console → Cloud Build → History
Execution Order Summary
GCP project setup — create project, enable APIs, create Artifact Registry
Secrets — store API keys in Secret Manager
Code changes — add Vertex AI provider, Dockerfile, .dockerignore, CORS update, health endpoint
Backend deploy — gcloud run deploy from backend/
Frontend config — create .env.production with Cloud Run URL
Frontend deploy — npm run build + firebase deploy
CI/CD — connect GitHub, create cloudbuild.yaml, create trigger
Verify — test all endpoints and the full user flow