// Package xerr defines HTTP-aware application errors without leaking internals.
package xerr

import "fmt"

// Error is safe to expose through the local API.
type Error struct {
	Status  int
	Message string
	Cause   error
}

func (e *Error) Error() string { return e.Message }
func (e *Error) Unwrap() error { return e.Cause }

// New creates a public API error.
func New(status int, message string) error { return &Error{Status: status, Message: message} }

// Wrap attaches an internal cause while retaining a public message.
func Wrap(status int, message string, cause error) error {
	if cause == nil {
		return New(status, message)
	}
	return &Error{Status: status, Message: fmt.Sprintf("%s: %v", message, cause), Cause: cause}
}
