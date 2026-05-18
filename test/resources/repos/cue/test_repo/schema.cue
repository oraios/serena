package testrepo

// #Person is the schema for a person record used by main.cue and lib.cue.
#Person: {
	name!: string
	age?:  int & >=0
	email: string
}

// #Greeting describes a greeting message addressed to a #Person.
#Greeting: {
	recipient: #Person
	message:   string
}

// defaultLocale is the fallback locale used when no locale is set on a greeting.
defaultLocale: "en-US"
