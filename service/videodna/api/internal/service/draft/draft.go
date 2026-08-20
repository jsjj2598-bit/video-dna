// Package draft writes JianyingPro/CapCut desktop draft folders.
package draft

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"regexp"
	"runtime"
	"strings"
	"time"

	"github.com/google/uuid"
	"github.com/jsjj2598-bit/video-dna/pkg/xffmpeg"
	"github.com/jsjj2598-bit/video-dna/service/videodna/api/internal/domain"
)

const draftVersion = 1776001

var unsafeName = regexp.MustCompile(`[\\/:*?"<>|]`)

// ExportFolder generates a self-contained Jianying draft and returns its path.
func ExportFolder(ctx context.Context, tools xffmpeg.Tools, projectName, sourcePath, outputDir string, dna *domain.DNA, cuts []domain.Cut) (string, error) {
	if dna == nil || dna.Meta.Duration <= 0 {
		return "", errors.New("无法读取源视频元信息")
	}
	if len(cuts) == 0 {
		return "", errors.New("缺少剪辑区间")
	}
	for _, cut := range cuts {
		if cut.Start < 0 || cut.End <= cut.Start || cut.End > dna.Meta.Duration+0.001 {
			return "", fmt.Errorf("剪辑区间越界: %.3f-%.3f", cut.Start, cut.End)
		}
	}
	name := safeName(projectName)
	if outputDir == "" {
		return "", errors.New("导出目录不能为空")
	}
	absoluteOutput, err := filepath.Abs(outputDir)
	if err != nil {
		return "", err
	}
	if err := os.MkdirAll(absoluteOutput, 0o700); err != nil {
		return "", fmt.Errorf("草稿目录不可写: %w", err)
	}
	draftDir := uniqueDirectory(filepath.Join(absoluteOutput, name))
	if err := os.MkdirAll(draftDir, 0o700); err != nil {
		return "", err
	}
	complete := false
	defer func() {
		if !complete {
			_ = os.RemoveAll(draftDir)
		}
	}()

	mediaDestination := filepath.Join(draftDir, filepath.Base(sourcePath))
	if err := copyFile(sourcePath, mediaDestination); err != nil {
		return "", fmt.Errorf("复制视频素材失败: %w", err)
	}
	content := buildContent(name, mediaDestination, dna, cuts)
	meta := map[string]any{
		"draft_id": uuid.NewString(), "draft_name": name,
		"tm_draft_modified": time.Now().UnixMilli(), "tm_draft_create": time.Now().UnixMilli(),
		"draft_root_path": "JianyingPro Drafts/" + name, "tm_draft_removed": false,
		"draft_removed_storage": false, "tm_draft_type": "NEW_DRAFT", "draft_fold_path": "",
	}
	if err := writeJSON(filepath.Join(draftDir, "draft_content.json"), content); err != nil {
		return "", err
	}
	if err := writeJSON(filepath.Join(draftDir, "draft_meta_info.json"), meta); err != nil {
		return "", err
	}
	_ = tools.ExtractFrame(ctx, mediaDestination, dna.Meta.Duration*0.2, filepath.Join(draftDir, "draft_cover.jpg"))
	instructions := "【Video DNA Analyzer · 剪映草稿使用说明】\n\n" +
		"1. 本文件夹就是完整的剪映草稿工程，已经包含视频素材。\n" +
		"2. 打开剪映专业版 → 设置 → 全局设置，查看草稿位置。\n" +
		"3. 把整个「" + filepath.Base(draftDir) + "」文件夹复制到草稿位置。\n" +
		"4. 重启剪映或刷新草稿列表后打开。\n"
	if err := os.WriteFile(filepath.Join(draftDir, "使用说明.txt"), []byte(instructions), 0o600); err != nil {
		return "", err
	}
	complete = true
	return draftDir, nil
}

func buildContent(name, sourcePath string, dna *domain.DNA, cuts []domain.Cut) map[string]any {
	videoID, audioID := compactID(), compactID()
	videoSegments := make([]any, 0, len(cuts))
	audioSegments := make([]any, 0, len(cuts))
	var cursor int64
	for _, cut := range cuts {
		duration := microseconds(cut.End - cut.Start)
		base := func() map[string]any {
			return map[string]any{
				"id": compactID(), "target_timeline": timeline(cursor, duration),
				"source_timeline": timeline(microseconds(cut.Start), duration),
				"keyframes":       []any{}, "extra_material_refs": []any{}, "is_scale_in_range": false, "is_overlap": false,
			}
		}
		video := base()
		video["material_id"] = videoID
		video["transform"] = map[string]any{"x": 0, "y": 0, "scale": 1, "rotation": 0}
		video["color_adjust"] = map[string]any{"brightness": 0, "contrast": 0, "saturation": 0, "highlight": 0, "shadow": 0, "temperature": 0, "vignette": 0}
		video["animation"] = map[string]any{"inner_type": nil}
		video["smart_remove_mask"] = map[string]any{"is_remove_mask": false}
		video["original_rot_angle"], video["speed_duration"] = 0, duration
		video["speed_curve_keyframes"], video["smart_retime_scope_segment_ids"] = []any{}, []any{}
		videoSegments = append(videoSegments, video)

		audio := base()
		audio["material_id"], audio["render_index"] = audioID, -1
		audio["audio_fade"] = map[string]any{"inner_type": "None", "start_fade": "None", "end_fade": "None", "start_fade_time": 0, "end_fade_time": 0}
		audio["adjustments"], audio["track_attribute"] = []any{}, 0
		audioSegments = append(audioSegments, audio)
		cursor += duration
	}
	width, height := dna.Meta.Width, dna.Meta.Height
	if width <= 0 || height <= 0 {
		width, height = 1920, 1080
	}
	fps := int(dna.Meta.FPS + 0.5)
	if fps < 1 {
		fps = 30
	}
	path := filepath.ToSlash(sourcePath)
	if runtime.GOOS == "windows" {
		path = strings.TrimPrefix(path, "//?/")
	}
	materials := map[string]any{
		"videos": []any{map[string]any{
			"id": videoID, "path": path, "material_name": filepath.Base(sourcePath),
			"duration": microseconds(dna.Meta.Duration), "width": width, "height": height, "type": "video",
			"material_audio": map[string]any{"id": audioID, "path": path, "type": "audio", "duration": microseconds(dna.Meta.Duration), "material_name": filepath.Base(sourcePath), "source": "video"},
			"rotate":         0, "rate": 1, "cover": "", "standard_mode": "video",
		}},
	}
	for _, key := range []string{"audio_materials", "texts", "stickers", "effects", "transitions", "adjustments", "audio_effects", "bubbles", "text_templates", "meme_materials", "video_effects", "filter_effects", "animation_effects", "emotion_effects", "auto_captions", "chat_groups", "highlight_moments", "materials", "plists"} {
		materials[key] = []any{}
	}
	track := func(kind string, segments []any) map[string]any {
		return map[string]any{"id": compactID(), "type": kind, "segments": segments, "is_default_name": true, "attribute": 0, "common_attrs": map[string]any{"canvas_config": map[string]any{"use_default": true}}}
	}
	return map[string]any{
		"duration": cursor, "version": draftVersion, "fps": fps,
		"canvas_config": map[string]any{"ratio": "original", "width": width, "height": height, "color": "#000000"},
		"name":          name, "materials": materials,
		"tracks":    []any{track("video", videoSegments), track("audio", audioSegments)},
		"keyframes": []any{}, "speed_curve_refs": map[string]any{}, "subtitle_tracks": []any{},
		"stats":   map[string]any{"storyboard": map[string]any{"video_duration": cursor, "video_frame_count": int(float64(cursor) / 1e6 * float64(fps)), "video_count": len(videoSegments), "effect_video_count": 0, "mark_count": 0, "speed_point_count": 0}},
		"configs": map[string]any{}, "attachments": []any{},
	}
}

func timeline(start, duration int64) map[string]any {
	return map[string]any{"duration": duration, "start": start, "speed": 1}
}

func microseconds(seconds float64) int64 { return int64(seconds*1_000_000 + 0.5) }

func compactID() string { return strings.ReplaceAll(uuid.NewString(), "-", "") }

func safeName(value string) string {
	value = strings.TrimSpace(unsafeName.ReplaceAllString(value, ""))
	if value == "" {
		return "VideoDNA剪辑方案"
	}
	return value
}

func uniqueDirectory(preferred string) string {
	if _, err := os.Stat(preferred); errors.Is(err, os.ErrNotExist) {
		return preferred
	}
	return preferred + "-" + time.Now().Format("20060102-150405")
}

func copyFile(source, destination string) error {
	input, err := os.Open(source)
	if err != nil {
		return err
	}
	defer input.Close()
	output, err := os.OpenFile(destination, os.O_CREATE|os.O_EXCL|os.O_WRONLY, 0o600)
	if err != nil {
		return err
	}
	_, copyErr := io.Copy(output, input)
	closeErr := output.Close()
	return errors.Join(copyErr, closeErr)
}

func writeJSON(path string, value any) error {
	data, err := json.MarshalIndent(value, "", "  ")
	if err != nil {
		return err
	}
	return os.WriteFile(path, data, 0o600)
}
