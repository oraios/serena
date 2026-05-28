package testrepo

// alice is a concrete #Person value; used to build the canonical greeting below.
alice: #Person & {
	name:  "Alice"
	age:   30
	email: "alice@example.com"
}

// greetingForAlice references both #Greeting (from schema.cue) and #BuildGreeting (from lib.cue).
greetingForAlice: (#BuildGreeting & {for_: alice}).result

// locale pins the output locale; validated against locales defined in lib.cue.
locale: defaultLocale
