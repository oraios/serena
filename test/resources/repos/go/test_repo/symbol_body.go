package main

// BodyStruct is a single type declaration used to verify that replace_symbol_body
// includes the leading `type` keyword in the symbol body and replacement range.
type BodyStruct struct {
	Value int
}

// NamedInt is a single defined-type declaration (non-struct).
type NamedInt int

// AliasInt is a type alias declaration.
type AliasInt = int

// GlobalCounter is a single package-level var declaration.
var GlobalCounter int = 0

// MaxItems is a single package-level const declaration.
const MaxItems = 100

// GroupedA and GroupedB are declared in a grouped var block, where the `var`
// keyword is on a separate line and must NOT be folded into either symbol body.
var (
	GroupedA int    = 1
	GroupedB string = "two"
)
