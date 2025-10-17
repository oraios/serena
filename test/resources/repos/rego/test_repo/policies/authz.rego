package policies

import data.utils

# Default deny
default allow := false

# Admin access rule
allow if {
	input.user.role == "admin"
	utils.is_valid_user(input.user)
}

# Read access for authenticated users
allow_read if {
	input.action == "read"
	input.user.authenticated
}

# User roles list
admin_roles := ["admin", "superuser"]

# Helper function to check if user is admin
is_admin(user) if {
	admin_roles[_] == user.role
}

# Check if action is allowed for user
check_permission(user, action) if {
	user.role == "admin"
	allowed_actions := ["read", "write", "delete"]
	allowed_actions[_] == action
}
