package testrepo

// #BuildGreeting is a template/closure: given a #Person under `for_`, it produces a #Greeting
// under `result`. Used by main.cue to build the canonical greeting.
#BuildGreeting: {
	for_: #Person
	result: #Greeting & {
		recipient: for_
		message:   "Hello, \(for_.name)!"
	}
}

// locales enumerates the locales the greeter supports; defaultLocale (schema.cue) must be one of them.
locales: [...string] & [
	"en-US",
	"en-GB",
	"de-DE",
]
