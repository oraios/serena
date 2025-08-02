#!/bin/bash

# Utility functions for bash scripting

# String manipulation functions
function to_uppercase() {
    echo "${1^^}"
}

function to_lowercase() {
    echo "${1,,}"
}

function trim_whitespace() {
    local var="$1"
    var="${var#"${var%%[![:space:]]*}"}"
    var="${var%"${var##*[![:space:]]}"}"   
    echo "$var"
}

# File operations
function backup_file() {
    local file="$1"
    local backup_dir="${2:-./backups}"
    
    if [[ ! -f "$file" ]]; then
        echo "Error: File '$file' does not exist" >&2
        return 1
    fi
    
    mkdir -p "$backup_dir"
    cp "$file" "${backup_dir}/$(basename "$file").$(date +%Y%m%d_%H%M%S).bak"
    echo "Backup created for $file"
}

# Array operations
function contains_element() {
    local element="$1"
    shift
    local array=("$@")
    
    for item in "${array[@]}"; do
        if [[ "$item" == "$element" ]]; then
            return 0
        fi
    done
    return 1
}

# Logging functions
function log_message() {
    local level="$1"
    local message="$2"
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    
    case "$level" in
        "ERROR")
            echo "[$timestamp] ERROR: $message" >&2
            ;;
        "WARN")
            echo "[$timestamp] WARN: $message" >&2
            ;;
        "INFO")
            echo "[$timestamp] INFO: $message"
            ;;
        "DEBUG")
            [[ "${DEBUG:-false}" == "true" ]] && echo "[$timestamp] DEBUG: $message"
            ;;
        *)
            echo "[$timestamp] $message"
            ;;
    esac
}

# Validation functions
function is_valid_email() {
    local email="$1"
    [[ "$email" =~ ^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$ ]]
}

function is_number() {
    [[ $1 =~ ^[0-9]+$ ]]
}
