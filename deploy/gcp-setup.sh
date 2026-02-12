#!/usr/bin/env bash
set -euo pipefail

#
# GCP Cloud Run Production Environment Setup
# Usage: bash deploy/gcp-setup.sh [--help]
#

# ============================================================
# Configuration (override via environment variables)
# ============================================================
PROJECT_ID="${GCP_PROJECT_ID:?GCP_PROJECT_ID must be set}"
REGION="${GCP_REGION:-asia-northeast1}"
SERVICE_NAME="${SERVICE_NAME:-serena}"
REPO_NAME="${REPO_NAME:-serena-repo}"
SA_NAME="${SA_NAME:-serena-sa}"
WIF_POOL="${WIF_POOL:-github-pool}"
WIF_PROVIDER="${WIF_PROVIDER:-github-provider}"
GITHUB_REPO="${GITHUB_REPO:?GITHUB_REPO must be set (e.g. owner/repo)}"

# Cloud SQL
SQL_INSTANCE_NAME="${SQL_INSTANCE_NAME:-serena-db}"
SQL_TIER="${SQL_TIER:-db-f1-micro}"
SQL_DB_NAME="${SQL_DB_NAME:-serena}"
SQL_USER="${SQL_USER:-serena}"

# Cloud Storage
GCS_BUCKET="${GCS_BUCKET:-${PROJECT_ID}-media}"
GCS_LIFECYCLE_DAYS="${GCS_LIFECYCLE_DAYS:-365}"

# VPC Connector
VPC_CONNECTOR_NAME="${VPC_CONNECTOR_NAME:-serena-connector}"
VPC_CONNECTOR_RANGE="${VPC_CONNECTOR_RANGE:-10.8.0.0/28}"

# Cloud Armor
ARMOR_POLICY_NAME="${ARMOR_POLICY_NAME:-serena-security-policy}"

# ============================================================
# Help
# ============================================================
if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
  cat <<'HELP'
GCP Cloud Run Production Environment Setup

Required environment variables:
  GCP_PROJECT_ID        GCP project ID
  GITHUB_REPO           GitHub repository (owner/repo)

Optional environment variables:
  GCP_REGION            Region (default: asia-northeast1)
  SERVICE_NAME          Cloud Run service name (default: serena)
  REPO_NAME             Artifact Registry repo name (default: serena-repo)
  SA_NAME               Service account name (default: serena-sa)
  WIF_POOL              Workload Identity Federation pool (default: github-pool)
  WIF_PROVIDER          WIF provider name (default: github-provider)

  SQL_INSTANCE_NAME     Cloud SQL instance name (default: serena-db)
  SQL_TIER              Cloud SQL machine tier (default: db-f1-micro)
  SQL_DB_NAME           Database name (default: serena)
  SQL_USER              Database user (default: serena)

  GCS_BUCKET            Cloud Storage bucket name (default: ${PROJECT_ID}-media)
  GCS_LIFECYCLE_DAYS    Object lifecycle in days (default: 365)

  VPC_CONNECTOR_NAME    VPC connector name (default: serena-connector)
  VPC_CONNECTOR_RANGE   VPC connector IP range (default: 10.8.0.0/28)

  ARMOR_POLICY_NAME     Cloud Armor policy name (default: serena-security-policy)
HELP
  exit 0
fi

# Create secure temporary directory for config files (cleaned up on exit)
_TMPDIR=$(mktemp -d)
trap 'rm -rf "${_TMPDIR}"' EXIT

echo "==> Setting project to ${PROJECT_ID}"
gcloud config set project "${PROJECT_ID}"

# ============================================================
# 1. Enable APIs
# ============================================================
echo "==> Enabling required APIs..."
gcloud services enable \
  run.googleapis.com \
  artifactregistry.googleapis.com \
  secretmanager.googleapis.com \
  iamcredentials.googleapis.com \
  sqladmin.googleapis.com \
  vpcaccess.googleapis.com \
  compute.googleapis.com \
  storage.googleapis.com

# ============================================================
# 2. Artifact Registry
# ============================================================
echo "==> Creating Artifact Registry repository..."
if ! gcloud artifacts repositories describe "${REPO_NAME}" --location="${REGION}" &>/dev/null; then
  gcloud artifacts repositories create "${REPO_NAME}" \
    --repository-format=docker \
    --location="${REGION}" \
    --description="Docker images for ${SERVICE_NAME}"
else
  echo "    Repository ${REPO_NAME} already exists, skipping."
fi

# ============================================================
# 3. Service Accounts & IAM
# ============================================================
DEPLOY_SA_NAME="${SA_NAME}-deploy"
BACKEND_SA_NAME="${SA_NAME}-backend"
FRONTEND_SA_NAME="${SA_NAME}-frontend"
DEPLOY_SA_EMAIL="${DEPLOY_SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"
BACKEND_SA_EMAIL="${BACKEND_SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"
FRONTEND_SA_EMAIL="${FRONTEND_SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"

# -- Deploy SA: used by GitHub Actions to deploy services
echo "==> Creating deploy service account..."
if ! gcloud iam service-accounts describe "${DEPLOY_SA_EMAIL}" &>/dev/null; then
  gcloud iam service-accounts create "${DEPLOY_SA_NAME}" \
    --display-name="${SERVICE_NAME} deploy service account"
else
  echo "    Service account ${DEPLOY_SA_EMAIL} already exists, skipping."
fi

echo "==> Granting deploy SA roles..."
DEPLOY_ROLES=(
  roles/run.admin
  roles/artifactregistry.writer
  roles/iam.serviceAccountUser
)
for role in "${DEPLOY_ROLES[@]}"; do
  gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
    --member="serviceAccount:${DEPLOY_SA_EMAIL}" \
    --role="${role}" \
    --condition=None \
    --quiet
done

# -- Backend runtime SA: used by Cloud Run backend at runtime
echo "==> Creating backend runtime service account..."
if ! gcloud iam service-accounts describe "${BACKEND_SA_EMAIL}" &>/dev/null; then
  gcloud iam service-accounts create "${BACKEND_SA_NAME}" \
    --display-name="${SERVICE_NAME} backend runtime service account"
else
  echo "    Service account ${BACKEND_SA_EMAIL} already exists, skipping."
fi

echo "==> Granting backend runtime SA roles..."
BACKEND_ROLES=(
  roles/cloudsql.client
  roles/storage.objectAdmin
  roles/secretmanager.secretAccessor
)
for role in "${BACKEND_ROLES[@]}"; do
  gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
    --member="serviceAccount:${BACKEND_SA_EMAIL}" \
    --role="${role}" \
    --condition=None \
    --quiet
done

# -- Frontend runtime SA: minimal permissions for serving static content
echo "==> Creating frontend runtime service account..."
if ! gcloud iam service-accounts describe "${FRONTEND_SA_EMAIL}" &>/dev/null; then
  gcloud iam service-accounts create "${FRONTEND_SA_NAME}" \
    --display-name="${SERVICE_NAME} frontend runtime service account"
else
  echo "    Service account ${FRONTEND_SA_EMAIL} already exists, skipping."
fi

echo "==> Granting frontend runtime SA roles..."
FRONTEND_ROLES=(
  roles/storage.objectViewer
  roles/secretmanager.secretAccessor
)
for role in "${FRONTEND_ROLES[@]}"; do
  gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
    --member="serviceAccount:${FRONTEND_SA_EMAIL}" \
    --role="${role}" \
    --condition=None \
    --quiet
done

# ============================================================
# 4. Workload Identity Federation (GitHub Actions)
# ============================================================
echo "==> Setting up Workload Identity Federation..."
if ! gcloud iam workload-identity-pools describe "${WIF_POOL}" --location=global &>/dev/null; then
  gcloud iam workload-identity-pools create "${WIF_POOL}" \
    --location=global \
    --display-name="GitHub Actions Pool"
else
  echo "    WIF pool ${WIF_POOL} already exists, skipping."
fi

if ! gcloud iam workload-identity-pools providers describe "${WIF_PROVIDER}" \
    --workload-identity-pool="${WIF_POOL}" --location=global &>/dev/null; then
  gcloud iam workload-identity-pools providers create-oidc "${WIF_PROVIDER}" \
    --location=global \
    --workload-identity-pool="${WIF_POOL}" \
    --display-name="GitHub Provider" \
    --attribute-mapping="google.subject=assertion.sub,attribute.repository=assertion.repository" \
    --issuer-uri="https://token.actions.githubusercontent.com"
else
  echo "    WIF provider ${WIF_PROVIDER} already exists, skipping."
fi

gcloud iam service-accounts add-iam-policy-binding "${DEPLOY_SA_EMAIL}" \
  --role="roles/iam.workloadIdentityUser" \
  --member="principalSet://iam.googleapis.com/projects/$(gcloud projects describe ${PROJECT_ID} --format='value(projectNumber)')/locations/global/workloadIdentityPools/${WIF_POOL}/attribute.repository/${GITHUB_REPO}" \
  --quiet

# ============================================================
# 5. Secret Manager
# ============================================================
echo "==> Creating secrets (if not exist)..."
for secret in DATABASE_URL SECRET_KEY GCS_BUCKET; do
  if ! gcloud secrets describe "${secret}" &>/dev/null; then
    echo "    Creating secret: ${secret}"
    printf "CHANGE_ME" | gcloud secrets create "${secret}" --data-file=-
  else
    echo "    Secret ${secret} already exists, skipping."
  fi
done

# ============================================================
# 6. Cloud SQL (PostgreSQL)
# ============================================================
echo "==> Setting up Cloud SQL instance..."
CLOUD_SQL_CONNECTION_NAME="${PROJECT_ID}:${REGION}:${SQL_INSTANCE_NAME}"

if ! gcloud sql instances describe "${SQL_INSTANCE_NAME}" &>/dev/null; then
  echo "    Creating Cloud SQL instance ${SQL_INSTANCE_NAME} (this may take several minutes)..."
  # NOTE: --backup-start-time is in UTC. 18:00 UTC = 03:00 JST (next day).
  gcloud sql instances create "${SQL_INSTANCE_NAME}" \
    --database-version=POSTGRES_15 \
    --tier="${SQL_TIER}" \
    --region="${REGION}" \
    --storage-auto-increase \
    --backup-start-time=18:00 \
    --availability-type=zonal \
    --storage-type=SSD \
    --database-flags=log_checkpoints=on,log_connections=on,log_disconnections=on

  echo "    Creating database ${SQL_DB_NAME}..."
  gcloud sql databases create "${SQL_DB_NAME}" \
    --instance="${SQL_INSTANCE_NAME}"

  echo "    Creating user ${SQL_USER}..."
  SQL_PASSWORD=$(openssl rand -hex 24)
  gcloud sql users create "${SQL_USER}" \
    --instance="${SQL_INSTANCE_NAME}" \
    --password="${SQL_PASSWORD}"

  # Store DATABASE_URL in Secret Manager
  DATABASE_URL="postgresql://${SQL_USER}:${SQL_PASSWORD}@//cloudsql/${CLOUD_SQL_CONNECTION_NAME}/${SQL_DB_NAME}"
  printf "%s" "${DATABASE_URL}" | gcloud secrets versions add DATABASE_URL --data-file=-
  echo "    DATABASE_URL stored in Secret Manager."
else
  echo "    Cloud SQL instance ${SQL_INSTANCE_NAME} already exists, skipping."
fi

# ============================================================
# 7. Cloud Storage (Media Bucket)
# ============================================================
echo "==> Setting up Cloud Storage bucket..."
if ! gsutil ls -b "gs://${GCS_BUCKET}" &>/dev/null; then
  gsutil mb -l "${REGION}" -p "${PROJECT_ID}" "gs://${GCS_BUCKET}"

  # Set lifecycle rule
  cat > ${_TMPDIR}/lifecycle.json <<EOF
{
  "rule": [
    {
      "action": {"type": "Delete"},
      "condition": {"age": ${GCS_LIFECYCLE_DAYS}}
    }
  ]
}
EOF
  gsutil lifecycle set ${_TMPDIR}/lifecycle.json "gs://${GCS_BUCKET}"

  # Enable uniform bucket-level access
  gsutil uniformbucketlevelaccess set on "gs://${GCS_BUCKET}"

  # Set CORS for web access
  cat > ${_TMPDIR}/cors.json <<EOF
[
  {
    "origin": ["*"],
    "method": ["GET", "HEAD"],
    "responseHeader": ["Content-Type"],
    "maxAgeSeconds": 3600
  }
]
EOF
  gsutil cors set ${_TMPDIR}/cors.json "gs://${GCS_BUCKET}"

  # Store bucket name in Secret Manager
  printf "%s" "${GCS_BUCKET}" | gcloud secrets versions add GCS_BUCKET --data-file=-
  echo "    GCS_BUCKET stored in Secret Manager."
else
  echo "    Bucket gs://${GCS_BUCKET} already exists, skipping."
fi

# ============================================================
# 8. VPC Connector (for Cloud SQL access)
# ============================================================
echo "==> Setting up Serverless VPC Access connector..."
# NOTE: --min-instances=2 is the minimum for production stability.
# For dev/staging environments, consider using --min-instances=2 --max-instances=3
# to minimize cost. For production, increase --max-instances as needed (e.g. 10).
# Each instance costs ~$0.01/hr. Adjust VPC_CONNECTOR_MIN/MAX_INSTANCES env vars.
VPC_MIN_INSTANCES="${VPC_CONNECTOR_MIN_INSTANCES:-2}"
VPC_MAX_INSTANCES="${VPC_CONNECTOR_MAX_INSTANCES:-3}"
if ! gcloud compute networks vpc-access connectors describe "${VPC_CONNECTOR_NAME}" \
    --region="${REGION}" &>/dev/null; then
  gcloud compute networks vpc-access connectors create "${VPC_CONNECTOR_NAME}" \
    --region="${REGION}" \
    --range="${VPC_CONNECTOR_RANGE}" \
    --min-instances="${VPC_MIN_INSTANCES}" \
    --max-instances="${VPC_MAX_INSTANCES}"
else
  echo "    VPC connector ${VPC_CONNECTOR_NAME} already exists, skipping."
fi

# ============================================================
# 9. Cloud Armor Security Policy
# ============================================================
echo "==> Setting up Cloud Armor security policy..."
if ! gcloud compute security-policies describe "${ARMOR_POLICY_NAME}" &>/dev/null; then
  gcloud compute security-policies create "${ARMOR_POLICY_NAME}" \
    --description="Security policy for ${SERVICE_NAME}"

  # General rate limiting: 300 requests per minute per IP
  gcloud compute security-policies rules create 900 \
    --security-policy="${ARMOR_POLICY_NAME}" \
    --expression="true" \
    --action=throttle \
    --rate-limit-threshold-count=300 \
    --rate-limit-threshold-interval-sec=60 \
    --conform-action=allow \
    --exceed-action=deny-429 \
    --enforce-on-key=IP

  # API rate limiting: 60 requests per minute per IP
  gcloud compute security-policies rules create 1000 \
    --security-policy="${ARMOR_POLICY_NAME}" \
    --expression="request.path.matches('/api/.*')" \
    --action=throttle \
    --rate-limit-threshold-count=60 \
    --rate-limit-threshold-interval-sec=60 \
    --conform-action=allow \
    --exceed-action=deny-429 \
    --enforce-on-key=IP

  # SQLi protection rule
  gcloud compute security-policies rules create 2000 \
    --security-policy="${ARMOR_POLICY_NAME}" \
    --expression="evaluatePreconfiguredExpr('sqli-v33-stable')" \
    --action=deny-403 \
    --description="Block SQL injection attacks"

  # XSS protection rule
  gcloud compute security-policies rules create 2001 \
    --security-policy="${ARMOR_POLICY_NAME}" \
    --expression="evaluatePreconfiguredExpr('xss-v33-stable')" \
    --action=deny-403 \
    --description="Block XSS attacks"

  # LFI protection rule
  gcloud compute security-policies rules create 2002 \
    --security-policy="${ARMOR_POLICY_NAME}" \
    --expression="evaluatePreconfiguredExpr('lfi-v33-stable')" \
    --action=deny-403 \
    --description="Block local file inclusion attacks"

  # RFI protection rule
  gcloud compute security-policies rules create 2003 \
    --security-policy="${ARMOR_POLICY_NAME}" \
    --expression="evaluatePreconfiguredExpr('rfi-v33-stable')" \
    --action=deny-403 \
    --description="Block remote file inclusion attacks"

  echo "    Cloud Armor policy ${ARMOR_POLICY_NAME} created with rate limiting and WAF rules."
else
  echo "    Cloud Armor policy ${ARMOR_POLICY_NAME} already exists, skipping."
fi

# ============================================================
# Summary
# ============================================================
echo ""
echo "============================================"
echo "  GCP Setup Complete"
echo "============================================"
echo "Project:              ${PROJECT_ID}"
echo "Region:               ${REGION}"
echo "Deploy SA:            ${DEPLOY_SA_EMAIL}"
echo "Backend Runtime SA:   ${BACKEND_SA_EMAIL}"
echo "Frontend Runtime SA:  ${FRONTEND_SA_EMAIL}"
echo "Artifact Registry:    ${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO_NAME}"
echo "Cloud SQL Instance:   ${CLOUD_SQL_CONNECTION_NAME}"
echo "Cloud SQL Database:   ${SQL_DB_NAME}"
echo "GCS Bucket:           gs://${GCS_BUCKET}"
echo "VPC Connector:        projects/${PROJECT_ID}/locations/${REGION}/connectors/${VPC_CONNECTOR_NAME}"
echo "Cloud Armor Policy:   ${ARMOR_POLICY_NAME}"
echo ""
echo "Next steps:"
echo "  1. Update SECRET_KEY secret with a secure random value"
echo "  2. Configure GitHub repository secrets for CD pipeline:"
echo "       DEPLOY_SA_EMAIL=${DEPLOY_SA_EMAIL}"
echo "       BACKEND_RUNTIME_SA_EMAIL=${BACKEND_SA_EMAIL}"
echo "       FRONTEND_RUNTIME_SA_EMAIL=${FRONTEND_SA_EMAIL}"
echo "  3. Run your first deployment via GitHub Actions"
echo "============================================"
