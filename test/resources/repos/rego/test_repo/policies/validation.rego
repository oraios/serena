package validation

import data.authz
import data.utils.helpers

# Validate user input
validate_user_input {
	helpers.is_valid_user(input.user)
	helpers.is_valid_email(input.user.email)
}

# Check if user has valid credentials
has_valid_credentials(user) {
	user.username != ""
	user.password != ""
	helpers.is_valid_email(user.email)
}

# Validate request
validate_request {
	input.user.authenticated
	authz.allow
}
