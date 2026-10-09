// Package xwhisper adapts whisper.cpp-compatible command line binaries.
package xwhisper

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"time"
)

type Segment struct {
	Start float64
	End   float64
	Text  string
}

type Runner struct {
	Binary  string
	Model   string
	Timeout time.Duration
}

func (r Runner) Available() bool { return r.Binary != "" && r.Model != "" }

func (r Runner) Transcribe(ctx context.Context, audioPath string) ([]Segment, string, error) {
	if !r.Available() {
		return nil, "", errors.New("ASR 未配置 whisper.cpp 可执行文件和模型")
	}
	if _, err := os.Stat(r.Binary); err != nil {
		return nil, "", fmt.Errorf("ASR 可执行文件不可用: %w", err)
	}
	if _, err := os.Stat(r.Model); err != nil {
		return nil, "", fmt.Errorf("ASR 模型不可用: %w", err)
	}
	timeout := r.Timeout
	if timeout <= 0 {
		timeout = 10 * time.Minute
	}
	runCtx, cancel := context.WithTimeout(ctx, timeout)
	defer cancel()
	outDir, err := os.MkdirTemp("", "videodna-asr-")
	if err != nil {
		return nil, "", err
	}
	defer os.RemoveAll(outDir)
	outBase := filepath.Join(outDir, "transcript")
	cmd := exec.CommandContext(runCtx, r.Binary, "-m", r.Model, "-f", audioPath, "-oj", "-of", outBase)
	var stdout, stderr bytes.Buffer
	cmd.Stdout, cmd.Stderr = &stdout, &stderr
	if err := cmd.Run(); err != nil {
		if errors.Is(runCtx.Err(), context.DeadlineExceeded) {
			return nil, "", fmt.Errorf("ASR 超时（%.0f 秒）", timeout.Seconds())
		}
		return nil, "", fmt.Errorf("ASR 执行失败: %w: %s", err, strings.TrimSpace(stderr.String()))
	}
	payload, err := os.ReadFile(outBase + ".json")
	if errors.Is(err, os.ErrNotExist) {
		payload = stdout.Bytes()
	} else if err != nil {
		return nil, "", err
	}
	segments, language, err := parseJSON(payload)
	if err != nil {
		return nil, "", err
	}
	return segments, language, nil
}

func parseJSON(payload []byte) ([]Segment, string, error) {
	var root struct {
		Language      string `json:"language"`
		Text          string `json:"text"`
		Transcription []struct {
			Text       string `json:"text"`
			Timestamps struct {
				From string `json:"from"`
				To   string `json:"to"`
			} `json:"timestamps"`
			Start float64 `json:"start"`
			End   float64 `json:"end"`
		} `json:"transcription"`
		Segments []struct {
			Text  string  `json:"text"`
			Start float64 `json:"start"`
			End   float64 `json:"end"`
		} `json:"segments"`
	}
	if err := json.Unmarshal(bytes.TrimSpace(payload), &root); err != nil {
		return nil, "", fmt.Errorf("ASR JSON 无效: %w", err)
	}
	result := make([]Segment, 0)
	for _, item := range root.Transcription {
		start, end := item.Start, item.End
		if item.Timestamps.From != "" {
			start = parseTimestamp(item.Timestamps.From)
		}
		if item.Timestamps.To != "" {
			end = parseTimestamp(item.Timestamps.To)
		}
		if strings.TrimSpace(item.Text) != "" && end >= start {
			result = append(result, Segment{start, end, strings.TrimSpace(item.Text)})
		}
	}
	for _, item := range root.Segments {
		if strings.TrimSpace(item.Text) != "" && item.End >= item.Start {
			result = append(result, Segment{item.Start, item.End, strings.TrimSpace(item.Text)})
		}
	}
	if len(result) == 0 && strings.TrimSpace(root.Text) != "" {
		result = append(result, Segment{Text: strings.TrimSpace(root.Text)})
	}
	return result, root.Language, nil
}

func parseTimestamp(value string) float64 {
	value = strings.TrimSpace(value)
	if strings.HasSuffix(value, "ms") {
		var n float64
		fmt.Sscanf(strings.TrimSuffix(value, "ms"), "%f", &n)
		return n / 1000
	}
	var h, m, s float64
	if _, err := fmt.Sscanf(value, "%f:%f:%f", &h, &m, &s); err == nil {
		return h*3600 + m*60 + s
	}
	fmt.Sscanf(value, "%f", &s)
	return s
}
