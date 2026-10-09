package analyzer

import (
	"context"
	"fmt"
	"path/filepath"

	"github.com/jsjj2598-bit/video-dna/service/videodna/api/internal/domain"
	"github.com/jsjj2598-bit/video-dna/service/videodna/api/internal/service/storage"
	"github.com/jsjj2598-bit/video-dna/service/videodna/api/internal/service/tasks"
	"github.com/zeromicro/go-zero/core/logx"
)

// Job is one uploaded analysis request.
type Job struct {
	SessionID  string
	SourcePath string
	SourceName string
	Options    Options
}

// Manager limits heavy jobs and persists their results.
type Manager struct {
	engine  *Service
	storage *storage.Service
	tasks   *tasks.Store
	slots   chan struct{}
}

// NewManager creates a bounded analysis worker pool.
func NewManager(engine *Service, storageService *storage.Service, taskStore *tasks.Store, workers int) *Manager {
	if workers < 1 {
		workers = 1
	}
	return &Manager{engine: engine, storage: storageService, tasks: taskStore, slots: make(chan struct{}, workers)}
}

// Start submits a background job.
func (m *Manager) Start(job Job) {
	go func() {
		if _, err := m.Run(context.Background(), job); err != nil {
			logx.Errorf("analysis failed session=%s err=%v", job.SessionID, err)
		}
	}()
}

// Run executes one job and waits for its result.
func (m *Manager) Run(ctx context.Context, job Job) (*domain.DNA, error) {
	select {
	case m.slots <- struct{}{}:
		defer func() { <-m.slots }()
	case <-ctx.Done():
		return nil, ctx.Err()
	}
	m.tasks.Report(job.SessionID, "queued", 2, "任务进入分析工作池")
	sessionDir, err := m.storage.SessionDir(job.SessionID)
	if err != nil {
		_, _ = m.storage.DeleteSession(job.SessionID)
		m.tasks.Fail(job.SessionID, err)
		return nil, err
	}
	result, err := m.engine.Analyze(ctx, job.SourcePath, sessionDir, job.Options, func(stage string, percent int, message string) {
		m.tasks.Report(job.SessionID, stage, percent, message)
	})
	if err != nil {
		m.tasks.Fail(job.SessionID, err)
		return nil, err
	}
	if err := m.storage.SaveResult(job.SessionID, result, filepath.Base(job.SourceName)); err != nil {
		_, _ = m.storage.DeleteSession(job.SessionID)
		m.tasks.Fail(job.SessionID, err)
		return nil, fmt.Errorf("保存分析结果失败: %w", err)
	}
	if _, err := m.storage.CleanupHistory(job.SessionID); err != nil {
		logx.Errorf("history cleanup failed: %v", err)
	}
	m.tasks.Finish(job.SessionID)
	return result, nil
}
