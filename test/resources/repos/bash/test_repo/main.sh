#!/bin/bash

# Main script demonstrating various bash features

# Global variables
readonly SCRIPT_NAME="Main Script"
COUNTER=0
declare -a ITEMS=("item1" "item2" "item3")

# Function definitions
function greet_user() {
    local username="$1"
    local greeting_type="${2:-default}"
    
    case "$greeting_type" in
        "formal")
            echo "Good day, ${username}!"
            ;;
        "casual")
            echo "Hey ${username}!"
            ;;
        *)
            echo "Hello, ${username}!"
            ;;
    esac
}

function process_items() {
    local -n items_ref=$1
    local operation="$2"
    
    for item in "${items_ref[@]}"; do
        case "$operation" in
            "count")
                ((COUNTER++))
                echo "Processing item $COUNTER: $item"
                ;;
            "uppercase")
                echo "${item^^}"
                ;;
            *)
                echo "Unknown operation: $operation"
                return 1
                ;;
        esac
    done
}

# Main execution
main() {
    echo "Starting $SCRIPT_NAME"
    
    if [[ $# -eq 0 ]]; then
        echo "Usage: $0 <username> [greeting_type]"
        exit 1
    fi
    
    local user="$1"
    local greeting="${2:-default}"
    
    greet_user "$user" "$greeting"
    
    echo "Processing items..."
    process_items ITEMS "count"
    
    echo "Script completed successfully"
}

# Run main function with all arguments
main "$@"
