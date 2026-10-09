// Package platform resolves per-user data and bundled tool locations.
package platform

import (
	"errors"
	"os"
	"path/filepath"
	"runtime"
)

const (
	AppName = "Video DNA Analyzer"
	AppSlug = "video-dna-analyzer"
	Version = "0.4.0"
)

// DataDir follows the platform convention and accepts VIDEODNA_DATA_DIR.
func DataDir() (string, error) {
	if value := os.Getenv("VIDEODNA_DATA_DIR"); value != "" {
		return filepath.Abs(value)
	}
	home, err := os.UserHomeDir()
	if err != nil {
		return "", err
	}
	switch runtime.GOOS {
	case "windows":
		root := os.Getenv("LOCALAPPDATA")
		if root == "" {
			root = os.Getenv("APPDATA")
		}
		if root == "" {
			root = home
		}
		return filepath.Join(root, AppName), nil
	case "darwin":
		return filepath.Join(home, "Library", "Application Support", AppName), nil
	default:
		root := os.Getenv("XDG_DATA_HOME")
		if root == "" {
			root = filepath.Join(home, ".local", "share")
		}
		return filepath.Join(root, AppSlug), nil
	}
}

// ExecutableDir returns the directory containing the current backend binary.
func ExecutableDir() (string, error) {
	executable, err := os.Executable()
	if err != nil {
		return "", err
	}
	resolved, err := filepath.EvalSymlinks(executable)
	if err != nil && !errors.Is(err, os.ErrNotExist) {
		return "", err
	}
	if resolved != "" {
		executable = resolved
	}
	return filepath.Dir(executable), nil
}
