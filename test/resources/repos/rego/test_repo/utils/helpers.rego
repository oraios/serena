package utils

# User validation
is_valid_user(user) if {
	user.id != ""
	user.email != ""
}

# Email validation
is_valid_email(email) if {
	contains(email, "@")
	contains(email, ".")
}

# Username validation
is_valid_username(username) if {
	count(username) >= 3
	count(username) <= 32
}

# Check if string is empty
is_empty(str) if {
	str == ""
}

# Check if array contains element
array_contains(arr, elem) if {
	arr[_] == elem
}
