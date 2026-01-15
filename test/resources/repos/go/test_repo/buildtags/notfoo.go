//go:build !foo
// +build !foo

package buildtags

type XNotFoo struct {
	Value int
}
