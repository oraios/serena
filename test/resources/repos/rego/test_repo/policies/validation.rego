package policies

import data.policies
import data.utils

# Validate user input
validate_user_input {
	utils.is_valid_user(input.user)
	utils.is_valid_email(input.user.email)
}

# Check if user has valid credentials
has_valid_credentials(user) {
	user.username != ""
	user.password != ""
	utils.is_valid_email(user.email)
}

# Validate request
validate_request {
	input.user.authenticated
	policies.allow
}
