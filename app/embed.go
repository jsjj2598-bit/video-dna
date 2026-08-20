// Package app embeds the desktop web UI into the Go backend executable.
package app

import (
	"embed"
	"io/fs"
)

//go:embed static
var assets embed.FS

// Static returns the embedded static directory.
func Static() fs.FS {
	root, err := fs.Sub(assets, "static")
	if err != nil {
		panic(err)
	}
	return root
}
