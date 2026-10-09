// Code scaffolded by goctl. Safe to edit.
// goctl 1.9.2

package svc

import (
	"fmt"
	"time"

	"github.com/jsjj2598-bit/video-dna/pkg/xffmpeg"
	"github.com/jsjj2598-bit/video-dna/pkg/xwhisper"
	"github.com/jsjj2598-bit/video-dna/service/videodna/api/internal/config"
	"github.com/jsjj2598-bit/video-dna/service/videodna/api/internal/service/analyzer"
	"github.com/jsjj2598-bit/video-dna/service/videodna/api/internal/service/registry"
	"github.com/jsjj2598-bit/video-dna/service/videodna/api/internal/service/storage"
	"github.com/jsjj2598-bit/video-dna/service/videodna/api/internal/service/tasks"
)

type ServiceContext struct {
	Config   config.Config
	Tools    xffmpeg.Tools
	Storage  *storage.Service
	Tasks    *tasks.Store
	Registry *registry.Service
	Analyzer *analyzer.Manager
}

func NewServiceContext(c config.Config) (*ServiceContext, error) {
	tools, err := xffmpeg.Discover(c.FFmpeg.Binary, c.FFmpeg.Probe)
	if err != nil {
		return nil, err
	}
	storageService, err := storage.New(c.DataDir, c.Limits.MaxUploadBytes, c.Limits.MaxHistoryBytes)
	if err != nil {
		return nil, fmt.Errorf("初始化存储失败: %w", err)
	}
	ttl := time.Duration(c.Limits.TaskTTLSeconds) * time.Second
	taskStore := tasks.NewStore(ttl, 200)
	registryService := registry.New(storageService.DataDir, storageService.PluginsDir, c.Limits.PluginBytes)
	var asrRunner *xwhisper.Runner
	if c.ASR.Binary != "" && c.ASR.Model != "" {
		runner := xwhisper.Runner{Binary: c.ASR.Binary, Model: c.ASR.Model, Timeout: time.Duration(c.ASR.TimeoutSeconds) * time.Second}
		asrRunner = &runner
	}
	engine := analyzer.NewWithASR(tools, registryService, asrRunner, c.Analysis.SceneThreshold, c.Analysis.AdaptiveThreshold, c.Analysis.MinShotSeconds)
	return &ServiceContext{
		Config: c, Tools: tools, Storage: storageService, Tasks: taskStore,
		Registry: registryService, Analyzer: analyzer.NewManager(engine, storageService, taskStore, c.Analysis.Workers),
	}, nil
}
