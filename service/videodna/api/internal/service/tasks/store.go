// Package tasks provides bounded, concurrency-safe analysis progress state.
package tasks

import (
	"sync"
	"time"
)

// Log is one user-facing progress record.
type Log struct {
	Time    string `json:"t"`
	Stage   string `json:"stage"`
	Percent int    `json:"pct"`
	Message string `json:"msg"`
}

// State is the API snapshot for one analysis task.
type State struct {
	SessionID string `json:"session_id"`
	Stage     string `json:"stage"`
	Percent   int    `json:"pct"`
	Logs      []Log  `json:"logs"`
	Error     string `json:"error,omitempty"`
	Done      bool   `json:"done"`
	updatedAt time.Time
}

// Store retains progress only; completed DNA stays on disk.
type Store struct {
	mu      sync.RWMutex
	states  map[string]*State
	ttl     time.Duration
	maxLogs int
}

// NewStore creates a progress store.
func NewStore(ttl time.Duration, maxLogs int) *Store {
	if ttl <= 0 {
		ttl = 24 * time.Hour
	}
	if maxLogs <= 0 {
		maxLogs = 200
	}
	return &Store{states: make(map[string]*State), ttl: ttl, maxLogs: maxLogs}
}

// Create starts a new uploaded task.
func (s *Store) Create(sessionID, message string) {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.pruneLocked()
	now := time.Now()
	s.states[sessionID] = &State{
		SessionID: sessionID, Stage: "uploaded", Percent: 1, updatedAt: now,
		Logs: []Log{{Time: now.Format("15:04:05"), Stage: "upload", Percent: 1, Message: message}},
	}
}

// Report advances progress monotonically.
func (s *Store) Report(sessionID, stage string, percent int, message string) {
	s.mu.Lock()
	defer s.mu.Unlock()
	state := s.states[sessionID]
	if state == nil {
		state = &State{SessionID: sessionID}
		s.states[sessionID] = state
	}
	percent = min(100, max(0, percent))
	state.Stage = stage
	state.Percent = max(state.Percent, percent)
	state.updatedAt = time.Now()
	state.Logs = append(state.Logs, Log{Time: state.updatedAt.Format("15:04:05"), Stage: stage, Percent: percent, Message: message})
	if len(state.Logs) > s.maxLogs {
		state.Logs = append([]Log(nil), state.Logs[len(state.Logs)-s.maxLogs:]...)
	}
}

// Finish marks a task successful.
func (s *Store) Finish(sessionID string) {
	s.Report(sessionID, "done", 100, "分析完成，结果已保存")
}

// Fail marks a task failed without retaining a result in memory.
func (s *Store) Fail(sessionID string, err error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	state := s.states[sessionID]
	if state == nil {
		state = &State{SessionID: sessionID}
		s.states[sessionID] = state
	}
	state.Stage, state.Percent, state.Error, state.Done = "error", 100, err.Error(), true
	state.updatedAt = time.Now()
	state.Logs = append(state.Logs, Log{Time: state.updatedAt.Format("15:04:05"), Stage: "error", Percent: 100, Message: "分析失败: " + err.Error()})
	if len(state.Logs) > s.maxLogs {
		state.Logs = append([]Log(nil), state.Logs[len(state.Logs)-s.maxLogs:]...)
	}
}

// Get returns an immutable snapshot.
func (s *Store) Get(sessionID string) (State, bool) {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.pruneLocked()
	state := s.states[sessionID]
	if state == nil {
		return State{}, false
	}
	snapshot := *state
	snapshot.Logs = append([]Log(nil), state.Logs...)
	snapshot.Done = snapshot.Stage == "done" || snapshot.Stage == "error" || snapshot.Stage == "cancelled"
	return snapshot, true
}

// Remove deletes one state.
func (s *Store) Remove(sessionID string) {
	s.mu.Lock()
	defer s.mu.Unlock()
	delete(s.states, sessionID)
}

// IsActive reports whether deletion must be blocked.
func (s *Store) IsActive(sessionID string) bool {
	s.mu.RLock()
	defer s.mu.RUnlock()
	state := s.states[sessionID]
	return state != nil && state.Stage != "done" && state.Stage != "error" && state.Stage != "cancelled"
}

// ActiveIDs returns a set suitable for history cleanup.
func (s *Store) ActiveIDs() map[string]bool {
	s.mu.RLock()
	defer s.mu.RUnlock()
	result := make(map[string]bool)
	for sessionID, state := range s.states {
		if state.Stage != "done" && state.Stage != "error" && state.Stage != "cancelled" {
			result[sessionID] = true
		}
	}
	return result
}

// ClearCompleted removes terminal states after history is cleared.
func (s *Store) ClearCompleted() {
	s.mu.Lock()
	defer s.mu.Unlock()
	for sessionID, state := range s.states {
		if state.Stage == "done" || state.Stage == "error" || state.Stage == "cancelled" {
			delete(s.states, sessionID)
		}
	}
}

func (s *Store) pruneLocked() {
	cutoff := time.Now().Add(-s.ttl)
	for sessionID, state := range s.states {
		if state.updatedAt.Before(cutoff) {
			delete(s.states, sessionID)
		}
	}
}
