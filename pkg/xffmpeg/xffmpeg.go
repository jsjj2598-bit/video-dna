// Package xffmpeg contains all FFmpeg and FFprobe process integration.
package xffmpeg

import (
	"bufio"
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"os"
	"os/exec"
	"path/filepath"
	"regexp"
	"runtime"
	"sort"
	"strconv"
	"strings"
)

// Tools is an immutable FFmpeg toolchain.
type Tools struct {
	FFmpeg  string
	FFprobe string
}

// MediaInfo is the normalized subset of ffprobe output used by the app.
type MediaInfo struct {
	Duration   float64
	Width      int
	Height     int
	FPS        float64
	VideoCodec string
	AudioCodec string
	SizeBytes  int64
}

// Discover resolves explicit paths, bundled tools beside the backend, then PATH.
func Discover(ffmpegPath, ffprobePath string) (Tools, error) {
	ffmpegName, ffprobeName := "ffmpeg", "ffprobe"
	if runtime.GOOS == "windows" {
		ffmpegName, ffprobeName = "ffmpeg.exe", "ffprobe.exe"
	}
	candidateDirs := make([]string, 0, 4)
	if executable, err := os.Executable(); err == nil {
		base := filepath.Dir(executable)
		candidateDirs = append(candidateDirs, base, filepath.Join(base, "tools"), filepath.Join(base, "ffmpeg"))
	}
	if cwd, err := os.Getwd(); err == nil {
		candidateDirs = append(candidateDirs, cwd, filepath.Join(cwd, "tools"))
	}
	resolve := func(explicit, envName, name string) string {
		for _, value := range []string{explicit, os.Getenv(envName)} {
			if value != "" {
				if absolute, err := filepath.Abs(value); err == nil {
					value = absolute
				}
				if stat, err := os.Stat(value); err == nil && !stat.IsDir() {
					return value
				}
			}
		}
		for _, directory := range candidateDirs {
			candidate := filepath.Join(directory, name)
			if stat, err := os.Stat(candidate); err == nil && !stat.IsDir() {
				return candidate
			}
		}
		path, _ := exec.LookPath(name)
		return path
	}
	tools := Tools{
		FFmpeg:  resolve(ffmpegPath, "VIDEODNA_FFMPEG", ffmpegName),
		FFprobe: resolve(ffprobePath, "VIDEODNA_FFPROBE", ffprobeName),
	}
	if tools.FFmpeg == "" || tools.FFprobe == "" {
		return Tools{}, fmt.Errorf("未找到 FFmpeg/FFprobe，请安装到 PATH 或放在 backend 同目录的 tools 文件夹")
	}
	return tools, nil
}

// Probe reads media metadata through ffprobe JSON output.
func (t Tools) Probe(ctx context.Context, source string) (MediaInfo, error) {
	cmd := exec.CommandContext(ctx, t.FFprobe,
		"-v", "error", "-print_format", "json", "-show_format", "-show_streams", source,
	)
	output, err := cmd.Output()
	if err != nil {
		return MediaInfo{}, fmt.Errorf("ffprobe 读取失败: %w", err)
	}
	var payload struct {
		Format struct {
			Duration string `json:"duration"`
			Size     string `json:"size"`
		} `json:"format"`
		Streams []struct {
			CodecType    string `json:"codec_type"`
			CodecName    string `json:"codec_name"`
			Width        int    `json:"width"`
			Height       int    `json:"height"`
			AvgFrameRate string `json:"avg_frame_rate"`
			RFrameRate   string `json:"r_frame_rate"`
		} `json:"streams"`
	}
	if err := json.Unmarshal(output, &payload); err != nil {
		return MediaInfo{}, fmt.Errorf("ffprobe JSON 无效: %w", err)
	}
	info := MediaInfo{Duration: parseFloat(payload.Format.Duration)}
	info.SizeBytes, _ = strconv.ParseInt(payload.Format.Size, 10, 64)
	for _, stream := range payload.Streams {
		switch stream.CodecType {
		case "video":
			if info.VideoCodec == "" {
				info.VideoCodec = stream.CodecName
				info.Width, info.Height = stream.Width, stream.Height
				info.FPS = parseFraction(stream.AvgFrameRate)
				if info.FPS == 0 {
					info.FPS = parseFraction(stream.RFrameRate)
				}
			}
		case "audio":
			if info.AudioCodec == "" {
				info.AudioCodec = stream.CodecName
			}
		}
	}
	return info, nil
}

var sceneTimePattern = regexp.MustCompile(`pts_time:([0-9]+(?:\.[0-9]+)?)`)

// DetectSceneTimes returns timestamps selected by FFmpeg's scene score filter.
func (t Tools) DetectSceneTimes(ctx context.Context, source string, threshold float64) ([]float64, error) {
	filter := fmt.Sprintf("select=gt(scene\\,%.4f),showinfo", threshold)
	cmd := exec.CommandContext(ctx, t.FFmpeg,
		"-hide_banner", "-nostdin", "-i", source, "-filter:v", filter, "-an", "-f", "null", "-",
	)
	stderr, err := cmd.StderrPipe()
	if err != nil {
		return nil, err
	}
	if err := cmd.Start(); err != nil {
		return nil, err
	}
	times := make([]float64, 0, 32)
	scanner := bufio.NewScanner(stderr)
	scanner.Buffer(make([]byte, 64*1024), 2*1024*1024)
	for scanner.Scan() {
		matches := sceneTimePattern.FindStringSubmatch(scanner.Text())
		if len(matches) == 2 {
			if value, parseErr := strconv.ParseFloat(matches[1], 64); parseErr == nil && value > 0 {
				times = append(times, value)
			}
		}
	}
	if err := scanner.Err(); err != nil {
		_ = cmd.Process.Kill()
		return nil, err
	}
	if err := cmd.Wait(); err != nil {
		return nil, fmt.Errorf("FFmpeg 镜头检测失败: %w", err)
	}
	sort.Float64s(times)
	return uniqueTimes(times, 0.08), nil
}

// ExtractFrame writes one JPEG keyframe.
func (t Tools) ExtractFrame(ctx context.Context, source string, second float64, destination string) error {
	cmd := exec.CommandContext(ctx, t.FFmpeg,
		"-hide_banner", "-loglevel", "error", "-nostdin", "-y",
		"-ss", fmt.Sprintf("%.3f", max(0, second)), "-i", source,
		"-frames:v", "1", "-q:v", "2", destination,
	)
	if output, err := cmd.CombinedOutput(); err != nil {
		return fmt.Errorf("提取关键帧失败: %w: %s", err, strings.TrimSpace(string(output)))
	}
	return nil
}

// PCMStream streams signed little-endian 16-bit mono samples from FFmpeg.
type PCMStream struct {
	io.ReadCloser
	cmd    *exec.Cmd
	stderr bytes.Buffer
}

// StartPCM starts an audio decoder at the requested sample rate.
func (t Tools) StartPCM(ctx context.Context, source string, sampleRate int) (*PCMStream, error) {
	cmd := exec.CommandContext(ctx, t.FFmpeg,
		"-hide_banner", "-loglevel", "error", "-nostdin", "-i", source,
		"-vn", "-ac", "1", "-ar", strconv.Itoa(sampleRate), "-f", "s16le", "pipe:1",
	)
	reader, err := cmd.StdoutPipe()
	if err != nil {
		return nil, err
	}
	stream := &PCMStream{ReadCloser: reader, cmd: cmd}
	cmd.Stderr = &stream.stderr
	if err := cmd.Start(); err != nil {
		return nil, err
	}
	return stream, nil
}

// Wait waits for the audio decoder and includes FFmpeg diagnostics on failure.
func (s *PCMStream) Wait() error {
	if err := s.cmd.Wait(); err != nil {
		return fmt.Errorf("提取音频失败: %w: %s", err, strings.TrimSpace(s.stderr.String()))
	}
	return nil
}

func parseFraction(value string) float64 {
	parts := strings.SplitN(value, "/", 2)
	if len(parts) == 2 {
		denominator := parseFloat(parts[1])
		if denominator == 0 {
			return 0
		}
		return parseFloat(parts[0]) / denominator
	}
	return parseFloat(value)
}

func parseFloat(value string) float64 {
	parsed, _ := strconv.ParseFloat(strings.TrimSpace(value), 64)
	return parsed
}

func uniqueTimes(values []float64, tolerance float64) []float64 {
	result := make([]float64, 0, len(values))
	for _, value := range values {
		if len(result) == 0 || value-result[len(result)-1] >= tolerance {
			result = append(result, value)
		}
	}
	return result
}
