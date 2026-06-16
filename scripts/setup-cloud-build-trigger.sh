#!/usr/bin/env bash
# One-time setup: permissions + Cloud Build trigger for push/merge to main.
set -euo pipefail

PROJECT_ID="${PROJECT_ID:-retrofi-atl}"
REGION="${REGION:-us-east1}"
REPO_OWNER="${REPO_OWNER:-rohanprofessional-1}"
REPO_NAME="${REPO_NAME:-RetroFi}"
TRIGGER_NAME="${TRIGGER_NAME:-deploy-retrofi-main}"

echo "Project:  $PROJECT_ID"
echo "Region:   $REGION"
echo "Repo:     $REPO_OWNER/$REPO_NAME"
echo "Trigger:  $TRIGGER_NAME (branch: main)"
echo

PROJECT_NUMBER="$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')"
CLOUD_BUILD_SA="${PROJECT_NUMBER}@cloudbuild.gserviceaccount.com"
RUN_SA="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"

echo "==> Enabling APIs"
gcloud services enable cloudbuild.googleapis.com run.googleapis.com \
  artifactregistry.googleapis.com secretmanager.googleapis.com \
  firebasehosting.googleapis.com --project="$PROJECT_ID"

echo "==> Granting Cloud Build permissions"
for ROLE in roles/run.developer roles/artifactregistry.writer roles/secretmanager.secretAccessor; do
  gcloud projects add-iam-policy-binding "$PROJECT_ID" \
    --member="serviceAccount:${CLOUD_BUILD_SA}" \
    --role="$ROLE" \
    --quiet >/dev/null
done

gcloud iam service-accounts add-iam-policy-binding "$RUN_SA" \
  --member="serviceAccount:${CLOUD_BUILD_SA}" \
  --role="roles/iam.serviceAccountUser" \
  --project="$PROJECT_ID" \
  --quiet >/dev/null

if ! gcloud secrets describe firebase-token --project="$PROJECT_ID" >/dev/null 2>&1; then
  echo
  echo "WARNING: Secret 'firebase-token' not found."
  echo "Run: firebase login:ci"
  echo "Then: echo -n \"YOUR_TOKEN\" | gcloud secrets create firebase-token --data-file=- --project=$PROJECT_ID"
  echo
fi

echo "==> Connecting GitHub (if needed)"
echo "If trigger creation fails, connect the repo first:"
echo "  https://console.cloud.google.com/cloud-build/triggers;region=$REGION/connect?project=$PROJECT_ID"
echo "  Install the Cloud Build GitHub App for $REPO_OWNER/$REPO_NAME"
echo

if gcloud builds triggers describe "$TRIGGER_NAME" --region="$REGION" --project="$PROJECT_ID" >/dev/null 2>&1; then
  echo "Trigger '$TRIGGER_NAME' already exists. Updating branch pattern..."
  gcloud builds triggers update github "$TRIGGER_NAME" \
    --region="$REGION" \
    --project="$PROJECT_ID" \
    --branch-pattern="^main$" \
    --build-config=cloudbuild.yaml
else
  echo "==> Creating trigger (fires on every push/merge to main)"
  gcloud builds triggers create github \
    --name="$TRIGGER_NAME" \
    --repo-name="$REPO_NAME" \
    --repo-owner="$REPO_OWNER" \
    --branch-pattern="^main$" \
    --build-config=cloudbuild.yaml \
    --region="$REGION" \
    --project="$PROJECT_ID" \
    --description="Deploy backend + frontend on push to main"
fi

echo
echo "Done. Push to main to deploy:"
echo "  git push origin main"
echo
echo "Manual run:"
echo "  gcloud builds submit --config=cloudbuild.yaml --region=$REGION --project=$PROJECT_ID ."
