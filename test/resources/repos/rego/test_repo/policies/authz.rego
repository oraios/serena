package authz

import data.utils.helpers

# Default deny
default allow := false

# Admin access rule
allow {
	input.user.role == "admin"
	helpers.is_valid_user(input.user)
}

# Read access for authenticated users
allow_read {
	input.action == "read"
	input.user.authenticated
}

# User roles list
admin_roles := ["admin", "superuser"]

# Helper function to check if user is admin
is_admin(user) {
	admin_roles[_] == user.role
}

# Check if action is allowed for user
check_permission(user, action) {
	user.role == "admin"
	allowed_actions := ["read", "write", "delete"]
	allowed_actions[_] == action
}
