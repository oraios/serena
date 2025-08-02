#!/bin/bash

# Configuration script for project setup

# Environment variables
export PROJECT_NAME="bash-test-project"
export PROJECT_VERSION="1.0.0"
export LOG_LEVEL="INFO"
export CONFIG_DIR="./config"

# Default settings
DEFAULT_TIMEOUT=30
DEFAULT_RETRIES=3
DEFAULT_PORT=8080

# Configuration arrays
declare -A ENVIRONMENTS=(
    ["dev"]="development"
    ["prod"]="production"
    ["test"]="testing"
)

declare -A DATABASE_CONFIGS=(
    ["host"]="localhost"
    ["port"]="5432"
    ["name"]="myapp_db"
    ["user"]="dbuser"
)

# Function to load configuration
load_config() {
    local env="${1:-dev}"
    local config_file="${CONFIG_DIR}/${env}.conf"
    
    if [[ -f "$config_file" ]]; then
        echo "Loading configuration from $config_file"
        source "$config_file"
    else
        echo "Warning: Configuration file $config_file not found, using defaults"
    fi
}

# Function to validate configuration
validate_config() {
    local errors=0
    
    if [[ -z "$PROJECT_NAME" ]]; then
        echo "Error: PROJECT_NAME is not set" >&2
        ((errors++))
    fi
    
    if [[ -z "$PROJECT_VERSION" ]]; then
        echo "Error: PROJECT_VERSION is not set" >&2
        ((errors++))
    fi
    
    if [[ $DEFAULT_PORT -lt 1024 || $DEFAULT_PORT -gt 65535 ]]; then
        echo "Error: Invalid port number $DEFAULT_PORT" >&2
        ((errors++))
    fi
    
    return $errors
}

# Function to print configuration
print_config() {
    echo "=== Current Configuration ==="
    echo "Project Name: $PROJECT_NAME"
    echo "Version: $PROJECT_VERSION"
    echo "Log Level: $LOG_LEVEL"
    echo "Default Port: $DEFAULT_PORT"
    echo "Default Timeout: $DEFAULT_TIMEOUT"
    echo "Default Retries: $DEFAULT_RETRIES"
    
    echo "\n=== Environments ==="
    for env in "${!ENVIRONMENTS[@]}"; do
        echo "  $env: ${ENVIRONMENTS[$env]}"
    done
    
    echo "\n=== Database Configuration ==="
    for key in "${!DATABASE_CONFIGS[@]}"; do
        echo "  $key: ${DATABASE_CONFIGS[$key]}"
    done
}

# Initialize configuration if this script is run directly
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    load_config "$1"
    validate_config
    print_config
fi
