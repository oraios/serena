.PHONY: help gcp-setup gcp-sql-proxy gcp-storage-sync

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
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

gcp-setup: ## Run GCP initial setup script
	bash deploy/gcp-setup.sh

gcp-sql-proxy: ## Start Cloud SQL Auth Proxy for local development
	@echo "Starting Cloud SQL Auth Proxy on port $(SQL_PROXY_PORT)..."
	@echo "Connection string: postgresql://USER:PASS@localhost:$(SQL_PROXY_PORT)/serena"
	cloud-sql-proxy $(GCP_PROJECT_ID):$(GCP_REGION):$(SQL_INSTANCE_NAME) \
		--port=$(SQL_PROXY_PORT) \
		--auto-iam-authn

gcp-storage-sync: ## Sync local uploads directory to GCS media bucket
	@echo "Syncing uploads/ to gs://$(GCS_BUCKET)/..."
	gsutil -m rsync -r -d uploads/ gs://$(GCS_BUCKET)/uploads/
	@echo "Sync complete."
