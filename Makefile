.PHONY: help gcp-setup gcp-sql-proxy gcp-storage-sync gcp-storage-sync-dry-run

# Default variables
GCP_PROJECT_ID ?= $(shell gcloud config get-value project 2>/dev/null)
GCP_REGION ?= asia-northeast1
SQL_INSTANCE_NAME ?= serena-db
GCS_BUCKET ?= $(GCP_PROJECT_ID)-media
SQL_PROXY_PORT ?= 5432

help: ## Show this help message
	@echo "Usage: make [target]"
	@echo ""
	@echo "GCP Targets:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-25s\033[0m %s\n", $$1, $$2}'
	@echo ""
	@echo "Prerequisites:"
	@echo "  gcp-sql-proxy:       Requires 'cloud-sql-proxy' CLI installed."
	@echo "                       If using --auto-iam-authn, Cloud SQL instance must have"
	@echo "                       IAM database authentication enabled:"
	@echo "                         gcloud sql instances patch $(SQL_INSTANCE_NAME) \\"
	@echo "                           --database-flags=cloudsql.iam_authentication=on"
	@echo "  gcp-storage-sync:    Requires 'gsutil' CLI installed."

gcp-setup: ## Run GCP initial setup script
	bash deploy/gcp-setup.sh

gcp-sql-proxy: ## Start Cloud SQL Auth Proxy for local development (requires IAM DB auth)
	@echo "Starting Cloud SQL Auth Proxy on port $(SQL_PROXY_PORT)..."
	@echo "NOTE: --auto-iam-authn requires IAM database authentication to be enabled on the Cloud SQL instance."
	@echo "      To enable: gcloud sql instances patch $(SQL_INSTANCE_NAME) --database-flags=cloudsql.iam_authentication=on"
	@echo "Connection string: postgresql://USER:PASS@localhost:$(SQL_PROXY_PORT)/serena"
	cloud-sql-proxy $(GCP_PROJECT_ID):$(GCP_REGION):$(SQL_INSTANCE_NAME) \
		--port=$(SQL_PROXY_PORT) \
		--auto-iam-authn

gcp-storage-sync-dry-run: ## Preview sync changes without applying (recommended before gcp-storage-sync)
	@echo "Dry-run: previewing changes for uploads/ -> gs://$(GCS_BUCKET)/uploads/"
	gsutil -m rsync -r -d -n uploads/ gs://$(GCS_BUCKET)/uploads/

gcp-storage-sync: ## Sync local uploads to GCS media bucket (WARNING: deletes remote files not present locally)
	@echo "WARNING: This will delete remote files not present in local uploads/ directory."
	@echo "TIP: Run 'make gcp-storage-sync-dry-run' first to preview changes."
	@echo ""
	@echo "Syncing uploads/ to gs://$(GCS_BUCKET)/..."
	gsutil -m rsync -r -d uploads/ gs://$(GCS_BUCKET)/uploads/
	@echo "Sync complete."
