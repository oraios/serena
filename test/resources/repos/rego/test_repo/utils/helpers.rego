package utils.helpers

# User validation
is_valid_user(user) {
	user.id != ""
	user.email != ""
}

# Email validation
is_valid_email(email) {
	contains(email, "@")
	contains(email, ".")
}

# Username validation
is_valid_username(username) {
	count(username) >= 3
	count(username) <= 32
}

# Check if string is empty
is_empty(str) {
	str == ""
}

# Check if array contains element
array_contains(arr, elem) {
	arr[_] == elem
}
