// Package storage owns all mutable on-disk Video DNA data.
package storage

import (
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"io/fs"
	"os"
	"path/filepath"
	"regexp"
	"sort"
	"strings"
	"time"

	"github.com/google/uuid"
	"github.com/jsjj2598-bit/video-dna/service/videodna/api/internal/domain"
)

var sessionPattern = regexp.MustCompile(`^[A-Za-z0-9_-]+$`)

var allowedVideoSuffixes = map[string]bool{
	".mp4": true, ".mov": true, ".mkv": true, ".webm": true, ".avi": true,
	".m4v": true, ".ts": true, ".flv": true, ".wmv": true,
}

// Service stores uploads, results and exports beneath one platform data root.
type Service struct {
	DataDir         string
	UploadsDir      string
	PluginsDir      string
	DownloadsDir    string
	MaxUploadBytes  int64
	MaxHistoryBytes int64
}

// HistoryItem is a lightweight result summary.
type HistoryItem struct {
	SessionID  string  `json:"session_id"`
	Name       string  `json:"name"`
	Time       string  `json:"time"`
	TotalShots int     `json:"total_shots"`
	Duration   float64 `json:"duration"`
	BPM        float64 `json:"bpm,omitempty"`
	Summary    string  `json:"summary"`
	HasVideo   bool    `json:"has_video"`
	ShotCount  int     `json:"shot_count"`
}

// New creates the data directory tree.
func New(dataDir string, maxUploadBytes, maxHistoryBytes int64) (*Service, error) {
	absolute, err := filepath.Abs(dataDir)
	if err != nil {
		return nil, err
	}
	service := &Service{
		DataDir: absolute, UploadsDir: filepath.Join(absolute, "uploads"),
		PluginsDir: filepath.Join(absolute, "plugins"), DownloadsDir: filepath.Join(absolute, "downloads"),
		MaxUploadBytes: maxUploadBytes, MaxHistoryBytes: maxHistoryBytes,
	}
	for _, directory := range []string{service.DataDir, service.UploadsDir, service.PluginsDir, service.DownloadsDir} {
		if err := os.MkdirAll(directory, 0o700); err != nil {
			return nil, fmt.Errorf("创建数据目录失败 %s: %w", directory, err)
		}
	}
	return service, nil
}

// NewSessionID returns a collision-resistant filesystem-safe ID.
func (s *Service) NewSessionID() string { return strings.ReplaceAll(uuid.NewString(), "-", "") }

// ValidateSessionID rejects path traversal and ambiguous identifiers.
func (s *Service) ValidateSessionID(sessionID string) (string, error) {
	sessionID = strings.TrimSpace(sessionID)
	if sessionID == "" || len(sessionID) > 128 || !sessionPattern.MatchString(sessionID) {
		return "", errors.New("session_id 非法")
	}
	return sessionID, nil
}

// SessionDir resolves a validated session directory.
func (s *Service) SessionDir(sessionID string) (string, error) {
	validated, err := s.ValidateSessionID(sessionID)
	if err != nil {
		return "", err
	}
	return filepath.Join(s.UploadsDir, validated), nil
}

// SaveUpload streams a video to an isolated session directory.
func (s *Service) SaveUpload(sessionID, sourceName string, source io.Reader) (string, error) {
	directory, err := s.SessionDir(sessionID)
	if err != nil {
		return "", err
	}
	if _, statErr := os.Stat(filepath.Join(directory, "result.json")); statErr == nil {
		return "", errors.New("session_id 已存在，请使用新的会话 ID")
	}
	if matches, _ := filepath.Glob(filepath.Join(directory, "source.*")); len(matches) > 0 {
		return "", errors.New("session_id 已存在，请使用新的会话 ID")
	}
	suffix := strings.ToLower(filepath.Ext(sourceName))
	if suffix == "" {
		suffix = ".mp4"
	}
	if !allowedVideoSuffixes[suffix] {
		return "", fmt.Errorf("不支持的视频格式: %s", suffix)
	}
	if err := os.MkdirAll(directory, 0o700); err != nil {
		return "", err
	}
	destination := filepath.Join(directory, "source"+suffix)
	target, err := os.OpenFile(destination, os.O_CREATE|os.O_EXCL|os.O_WRONLY, 0o600)
	if err != nil {
		return "", err
	}
	limit := s.MaxUploadBytes
	if limit <= 0 {
		limit = 2 * 1024 * 1024 * 1024
	}
	written, copyErr := io.Copy(target, io.LimitReader(source, limit+1))
	closeErr := target.Close()
	if copyErr != nil || closeErr != nil || written > limit {
		_ = os.Remove(destination)
		_ = removeEmptyDir(directory)
		if written > limit {
			return "", fmt.Errorf("视频超过上传上限 %dMB", limit/1024/1024)
		}
		return "", errors.Join(copyErr, closeErr)
	}
	if written == 0 {
		_ = os.Remove(destination)
		_ = removeEmptyDir(directory)
		return "", errors.New("上传文件为空")
	}
	return destination, nil
}

// SourceVideo returns the retained source media path.
func (s *Service) SourceVideo(sessionID string) (string, error) {
	directory, err := s.SessionDir(sessionID)
	if err != nil {
		return "", err
	}
	matches, err := filepath.Glob(filepath.Join(directory, "source.*"))
	if err != nil {
		return "", err
	}
	for _, path := range matches {
		if info, statErr := os.Stat(path); statErr == nil && !info.IsDir() {
			return path, nil
		}
	}
	return "", nil
}

// SaveResult atomically persists a completed analysis.
func (s *Service) SaveResult(sessionID string, result *domain.DNA, sourceName string) error {
	directory, err := s.SessionDir(sessionID)
	if err != nil {
		return err
	}
	result.SessionID = sessionID
	result.SourceFile = filepath.Base(sourceName)
	result.VideoURL = "/api/sessions/" + sessionID + "/video"
	result.FrameBase = "/api/sessions/" + sessionID + "/frames/"
	payload, err := json.MarshalIndent(result, "", "  ")
	if err != nil {
		return err
	}
	temporary := filepath.Join(directory, "result.json.tmp")
	target := filepath.Join(directory, "result.json")
	if err := os.WriteFile(temporary, payload, 0o600); err != nil {
		return err
	}
	return os.Rename(temporary, target)
}

// ReadResult reads a completed analysis or returns os.ErrNotExist.
func (s *Service) ReadResult(sessionID string) (*domain.DNA, error) {
	directory, err := s.SessionDir(sessionID)
	if err != nil {
		return nil, err
	}
	payload, err := os.ReadFile(filepath.Join(directory, "result.json"))
	if err != nil {
		return nil, err
	}
	var result domain.DNA
	if err := json.Unmarshal(payload, &result); err != nil {
		return nil, err
	}
	return &result, nil
}

// FramePath safely resolves a keyframe within a session.
func (s *Service) FramePath(sessionID, filename string) (string, error) {
	directory, err := s.SessionDir(sessionID)
	if err != nil {
		return "", err
	}
	if filepath.Base(filename) != filename || filename == "." || filename == "" {
		return "", errors.New("关键帧文件名非法")
	}
	return filepath.Join(directory, "frames", filename), nil
}

// ListHistory returns readable completed results newest first.
func (s *Service) ListHistory() ([]HistoryItem, error) {
	entries, err := os.ReadDir(s.UploadsDir)
	if err != nil {
		return nil, err
	}
	type entryWithInfo struct {
		entry fs.DirEntry
		info  fs.FileInfo
	}
	directories := make([]entryWithInfo, 0, len(entries))
	for _, entry := range entries {
		if !entry.IsDir() {
			continue
		}
		info, infoErr := entry.Info()
		if infoErr == nil {
			directories = append(directories, entryWithInfo{entry: entry, info: info})
		}
	}
	sort.Slice(directories, func(i, j int) bool { return directories[i].info.ModTime().After(directories[j].info.ModTime()) })
	items := make([]HistoryItem, 0, len(directories))
	for _, directory := range directories {
		result, readErr := s.ReadResult(directory.entry.Name())
		if readErr != nil {
			continue
		}
		source, _ := s.SourceVideo(directory.entry.Name())
		items = append(items, HistoryItem{
			SessionID: directory.entry.Name(), Name: result.SourceFile,
			Time:       directory.info.ModTime().Format("2006-01-02 15:04"),
			TotalShots: result.Meta.TotalShots, Duration: result.Meta.Duration,
			BPM: result.Audio.TempoBPM, Summary: result.Summary,
			HasVideo: source != "", ShotCount: len(result.Shots),
		})
	}
	return items, nil
}

// DeleteSession removes one validated session directory.
func (s *Service) DeleteSession(sessionID string) (bool, error) {
	directory, err := s.SessionDir(sessionID)
	if err != nil {
		return false, err
	}
	if _, err := os.Stat(directory); errors.Is(err, os.ErrNotExist) {
		return false, nil
	} else if err != nil {
		return false, err
	}
	return true, os.RemoveAll(directory)
}

// ClearHistory removes all sessions except IDs in keep.
func (s *Service) ClearHistory(keep map[string]bool) error {
	entries, err := os.ReadDir(s.UploadsDir)
	if err != nil {
		return err
	}
	for _, entry := range entries {
		if entry.IsDir() && !keep[entry.Name()] {
			if err := os.RemoveAll(filepath.Join(s.UploadsDir, entry.Name())); err != nil {
				return err
			}
		}
	}
	return nil
}

// CleanupHistory removes only as many oldest sessions as needed.
func (s *Service) CleanupHistory(keepSessionID string) ([]string, error) {
	entries, err := os.ReadDir(s.UploadsDir)
	if err != nil {
		return nil, err
	}
	type usage struct {
		name    string
		path    string
		size    int64
		modTime time.Time
	}
	items := make([]usage, 0, len(entries))
	var total int64
	for _, entry := range entries {
		if !entry.IsDir() {
			continue
		}
		path := filepath.Join(s.UploadsDir, entry.Name())
		size, sizeErr := directorySize(path)
		info, infoErr := entry.Info()
		if sizeErr != nil || infoErr != nil {
			continue
		}
		items = append(items, usage{name: entry.Name(), path: path, size: size, modTime: info.ModTime()})
		total += size
	}
	if s.MaxHistoryBytes <= 0 || total <= s.MaxHistoryBytes {
		return nil, nil
	}
	sort.Slice(items, func(i, j int) bool { return items[i].modTime.Before(items[j].modTime) })
	removed := make([]string, 0)
	for _, item := range items {
		if item.name == keepSessionID {
			continue
		}
		if err := os.RemoveAll(item.path); err != nil {
			return removed, err
		}
		total -= item.size
		removed = append(removed, item.name)
		if total <= s.MaxHistoryBytes {
			break
		}
	}
	return removed, nil
}

func directorySize(root string) (int64, error) {
	var total int64
	err := filepath.WalkDir(root, func(path string, entry fs.DirEntry, err error) error {
		if err != nil {
			return err
		}
		if !entry.IsDir() {
			info, infoErr := entry.Info()
			if infoErr != nil {
				return infoErr
			}
			total += info.Size()
		}
		return nil
	})
	return total, err
}

func removeEmptyDir(directory string) error {
	entries, err := os.ReadDir(directory)
	if err != nil {
		return err
	}
	if len(entries) == 0 {
		return os.Remove(directory)
	}
	return nil
}
