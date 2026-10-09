package analyzer

import (
	"context"
	"errors"
	"fmt"
	"path/filepath"
	"sync"

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
	pending chan struct{}
	mu      sync.Mutex
	cancels map[string]context.CancelFunc
}

// NewManager creates a bounded analysis worker pool.
func NewManager(engine *Service, storageService *storage.Service, taskStore *tasks.Store, workers int) *Manager {
	if workers < 1 {
		workers = 1
	}
	return &Manager{
		engine: engine, storage: storageService, tasks: taskStore,
		slots: make(chan struct{}, workers), pending: make(chan struct{}, workers*2),
		cancels: make(map[string]context.CancelFunc),
	}
}

// Start submits a background job.
func (m *Manager) Start(job Job) error {
	select {
	case m.pending <- struct{}{}:
	default:
		return errors.New("分析队列已满，请等待当前任务完成后重试")
	}
	ctx, cancel := context.WithCancel(context.Background())
	m.mu.Lock()
	if _, exists := m.cancels[job.SessionID]; exists {
		m.mu.Unlock()
		cancel()
		<-m.pending
		return errors.New("会话已在分析中")
	}
	m.cancels[job.SessionID] = cancel
	m.mu.Unlock()
	go func() {
		defer func() {
			m.mu.Lock()
			delete(m.cancels, job.SessionID)
			m.mu.Unlock()
			<-m.pending
		}()
		if _, err := m.Run(ctx, job); err != nil && !errors.Is(err, context.Canceled) {
			logx.Errorf("analysis failed session=%s err=%v", job.SessionID, err)
		}
	}()
	return nil
}

// Cancel stops an asynchronous task. It is safe to call repeatedly.
func (m *Manager) Cancel(sessionID string) bool {
	m.mu.Lock()
	cancel, ok := m.cancels[sessionID]
	m.mu.Unlock()
	if !ok {
		return false
	}
	if !m.tasks.Cancel(sessionID) {
		return false
	}
	cancel()
	return true
}

// Run executes one job and waits for its result.
func (m *Manager) Run(ctx context.Context, job Job) (*domain.DNA, error) {
	select {
	case m.slots <- struct{}{}:
		defer func() { <-m.slots }()
	case <-ctx.Done():
		m.tasks.Cancel(job.SessionID)
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
		if cancellationErr := ctx.Err(); cancellationErr != nil || errors.Is(err, context.Canceled) {
			_, _ = m.storage.DeleteSession(job.SessionID)
			m.tasks.Cancel(job.SessionID)
			if cancellationErr != nil {
				return nil, cancellationErr
			}
			return nil, err
		}
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
