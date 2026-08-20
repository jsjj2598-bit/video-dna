// Code scaffolded by goctl. Safe to edit.
// goctl 1.9.2

package config

import (
	"os"
	"strconv"

	"github.com/jsjj2598-bit/video-dna/internal/platform"
	"github.com/zeromicro/go-zero/rest"
)

// Default returns a standalone desktop configuration; YAML may override it.
func Default() Config {
	var c Config
	c.Name, c.Host, c.Port = "VideoDNA", "127.0.0.1", 8000
	c.Timeout, c.MaxBytes = 1_800_000, 2*1024*1024*1024
	c.Limits.MaxUploadBytes = 2 * 1024 * 1024 * 1024
	c.Limits.MaxHistoryBytes = 8 * 1024 * 1024 * 1024
	c.Limits.TaskTTLSeconds = 86_400
	c.Limits.PluginBytes = 50 * 1024 * 1024
	c.Analysis.Workers = 1
	c.Analysis.SceneThreshold = .27
	c.Analysis.AdaptiveThreshold = .18
	c.Analysis.MinShotSeconds = .25
	return c
}

type Config struct {
	rest.RestConf
	DataDir string
	Auth    struct {
		Token string
	}
	FFmpeg struct {
		Binary string
		Probe  string
	}
	Limits struct {
		MaxUploadBytes  int64
		MaxHistoryBytes int64
		TaskTTLSeconds  int64
		PluginBytes     int64
	}
	Analysis struct {
		Workers           int
		SceneThreshold    float64
		AdaptiveThreshold float64
		MinShotSeconds    float64
	}
}

// Normalize applies desktop environment overrides after YAML loading.
func Normalize(c *Config) error {
	if value := os.Getenv("VIDEODNA_HOST"); value != "" {
		c.Host = value
	}
	if value := os.Getenv("VIDEODNA_PORT"); value != "" {
		if port, err := strconv.Atoi(value); err == nil && port > 0 && port <= 65535 {
			c.Port = port
		}
	}
	if value := os.Getenv("VIDEODNA_API_TOKEN"); value != "" {
		c.Auth.Token = value
	}
	if value := os.Getenv("VIDEODNA_DATA_DIR"); value != "" {
		c.DataDir = value
	}
	if c.DataDir == "" {
		dataDir, err := platform.DataDir()
		if err != nil {
			return err
		}
		c.DataDir = dataDir
	}
	if c.Analysis.Workers < 1 {
		c.Analysis.Workers = 1
	}
	if c.Analysis.SceneThreshold <= 0 {
		c.Analysis.SceneThreshold = 0.27
	}
	if c.Analysis.AdaptiveThreshold <= 0 {
		c.Analysis.AdaptiveThreshold = 0.18
	}
	if c.Analysis.MinShotSeconds <= 0 {
		c.Analysis.MinShotSeconds = 0.25
	}
	return nil
}
