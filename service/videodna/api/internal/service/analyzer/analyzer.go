// Package analyzer implements the Video DNA pipeline without Python or CGO.
package analyzer

import (
	"bufio"
	"context"
	"encoding/binary"
	"encoding/json"
	"errors"
	"fmt"
	"image"
	_ "image/jpeg"
	_ "image/png"
	"io"
	"math"
	"os"
	"path/filepath"
	"strings"

	"github.com/jsjj2598-bit/video-dna/pkg/xaiapi"
	"github.com/jsjj2598-bit/video-dna/pkg/xffmpeg"
	"github.com/jsjj2598-bit/video-dna/service/videodna/api/internal/domain"
	"github.com/jsjj2598-bit/video-dna/service/videodna/api/internal/service/registry"
)

// ReportFunc receives stable stage names and monotonic percentages.
type ReportFunc func(stage string, percent int, message string)

// Options controls one analysis request.
type Options struct {
	Detector  string
	Backend   string
	OpenAIKey string
	QwenKey   string
}

// Service owns the pure analysis pipeline.
type Service struct {
	tools             xffmpeg.Tools
	registry          *registry.Service
	sceneThreshold    float64
	adaptiveThreshold float64
	minShotSeconds    float64
}

// New creates an analyzer with explicit dependencies.
func New(tools xffmpeg.Tools, registryService *registry.Service, sceneThreshold, adaptiveThreshold, minShotSeconds float64) *Service {
	return &Service{
		tools: tools, registry: registryService, sceneThreshold: sceneThreshold,
		adaptiveThreshold: adaptiveThreshold, minShotSeconds: minShotSeconds,
	}
}

// Analyze probes, segments and describes one source video.
func (s *Service) Analyze(ctx context.Context, sourcePath, sessionDir string, options Options, report ReportFunc) (*domain.DNA, error) {
	if report == nil {
		report = func(string, int, string) {}
	}
	report("probe", 2, "读取视频元信息：分辨率 / 帧率 / 时长 / 编码")
	media, err := s.tools.Probe(ctx, sourcePath)
	if err != nil {
		return nil, err
	}
	if media.Duration <= 0 || media.Width <= 0 || media.Height <= 0 {
		return nil, errors.New("无法读取有效的视频元信息")
	}

	threshold := s.sceneThreshold
	if options.Detector == "adaptive" {
		threshold = s.adaptiveThreshold
	}
	report("shots", 8, fmt.Sprintf("FFmpeg 场景分数检测：%dx%d · %.3ffps", media.Width, media.Height, media.FPS))
	sceneTimes, err := s.tools.DetectSceneTimes(ctx, sourcePath, threshold)
	if err != nil {
		return nil, err
	}
	shots := buildShots(sceneTimes, media.Duration, media.FPS, s.minShotSeconds)
	report("shots", 20, fmt.Sprintf("镜头切分完成：共 %d 个镜头", len(shots)))

	audioInfo := domain.AudioInfo{
		Duration: media.Duration, Beats: []float64{}, SilenceRegions: []domain.TimeRegion{},
		SFXCandidates: []domain.SFXCandidate{}, SpeechRegions: []domain.TimeRegion{}, Segments: []domain.Transcript{},
	}
	if media.AudioCodec != "" {
		report("audio", 23, "FFmpeg 流式解码音轨，纯 Go 分析能量与瞬态")
		audioInfo, err = analyzeAudio(ctx, s.tools, sourcePath, media.Duration)
		if err != nil {
			return nil, err
		}
		report("audio", 38, fmt.Sprintf("音频分析完成：BPM=%.2f，节拍 %d 个", audioInfo.TempoBPM, audioInfo.BeatCount))
	} else {
		report("audio", 38, "视频无音轨，跳过音频分析")
	}
	if !s.registry.ComponentEnabled("beats") {
		audioInfo.Beats, audioInfo.BeatCount, audioInfo.TempoBPM = []float64{}, 0, 0
	}

	aligned := alignBeats(shots, audioInfo.Beats, 0.15)
	report("beats", 43, fmt.Sprintf("节拍对齐：%d/%d 个镜头卡点", aligned, len(shots)))
	transitions := make(map[string]int)
	for index := range shots {
		if index > 0 {
			shots[index].Transition = "cut"
			confidence := 0.75
			shots[index].TransitionConfidence = &confidence
			transitions["cut"]++
		}
	}
	report("transitions", 50, "转场基础分类完成：场景分数边界标记为硬切")

	framesDir := filepath.Join(sessionDir, "frames")
	if err := os.MkdirAll(framesDir, 0o700); err != nil {
		return nil, err
	}
	report("frames", 56, fmt.Sprintf("提取 %d 个镜头关键帧", len(shots)))
	for index := range shots {
		filename := fmt.Sprintf("shot_%03d.jpg", shots[index].Index)
		midpoint := (shots[index].Start + shots[index].End) / 2
		if err := s.tools.ExtractFrame(ctx, sourcePath, midpoint, filepath.Join(framesDir, filename)); err == nil {
			shots[index].Keyframe = filename
		}
	}
	report("frames", 65, "关键帧提取完成")

	visionModel, useVision, _ := s.selectVisionModel(options)
	if options.Backend == "heuristic" {
		useVision = false
	}
	report("describer", 67, "分析镜头亮度、色彩和画面变化")
	for index := range shots {
		if shots[index].Keyframe == "" {
			continue
		}
		framePath := filepath.Join(framesDir, shots[index].Keyframe)
		describeFrameHeuristic(framePath, &shots[index])
		if useVision {
			if description, describeErr := s.describeFrame(ctx, visionModel, framePath); describeErr == nil {
				applyDescription(description, &shots[index])
			}
		}
	}
	report("describer", 78, fmt.Sprintf("镜头描述完成：%d 个镜头", len(shots)))

	avgShot := media.Duration / math.Max(1, float64(len(shots)))
	beatRatio := float64(aligned) / math.Max(1, float64(len(shots)))
	dna := &domain.DNA{
		Meta: domain.Meta{
			Duration: round(media.Duration, 3), Resolution: fmt.Sprintf("%dx%d", media.Width, media.Height),
			Width: media.Width, Height: media.Height, FPS: round(media.FPS, 3),
			VideoCodec: media.VideoCodec, AudioCodec: media.AudioCodec, SizeBytes: media.SizeBytes,
			TotalShots: len(shots), AvgShotDuration: round(avgShot, 3),
			BeatAlignmentRatio: round(beatRatio, 3), Transitions: transitions,
		},
		Audio: audioInfo, Shots: shots,
	}
	dna.Summary = summarize(dna)
	report("summary", 86, "汇总镜头节奏、转场和卡点统计")

	if s.registry.ComponentEnabled("translate") && dna.Audio.Text != "" {
		if model, ok, _ := s.registry.EnabledChatModel(); ok {
			translated, translateErr := s.registry.Chat(ctx, model, []xaiapi.Message{
				{Role: "system", Content: "将台词翻译为简体中文，保留口语感。"},
				{Role: "user", Content: dna.Audio.Text},
			}, false)
			if translateErr == nil {
				dna.Audio.Translation = translated
			}
		}
	}
	if s.registry.ComponentEnabled("summarize") {
		if model, ok, _ := s.registry.EnabledChatModel(); ok {
			prompt := fmt.Sprintf("请用 150 字以内总结视频剪辑节奏、转场、卡点和改进建议。数据：%s", mustJSON(dna))
			if summary, summaryErr := s.registry.Chat(ctx, model, []xaiapi.Message{{Role: "user", Content: prompt}}, false); summaryErr == nil {
				dna.Summary, dna.SummaryMethod = summary, "llm"
			}
		}
	}
	report("plugins", 94, "运行兼容的 Go 可执行插件")
	if updated, pluginErr := s.registry.RunPluginHooks(ctx, dna); pluginErr == nil {
		dna = updated
	}
	report("done", 98, "剪辑 DNA 已生成，正在持久化")
	return dna, nil
}

func (s *Service) selectVisionModel(options Options) (registry.Model, bool, error) {
	switch options.Backend {
	case "openai":
		if options.OpenAIKey != "" {
			return registry.Model{BaseURL: "https://api.openai.com/v1", Model: "gpt-4o", APIKey: options.OpenAIKey}, true, nil
		}
	case "qwen":
		if options.QwenKey != "" {
			return registry.Model{BaseURL: "https://dashscope.aliyuncs.com/compatible-mode/v1", Model: "qwen-vl-max", APIKey: options.QwenKey}, true, nil
		}
	}
	return s.registry.EnabledVisionModel()
}

func (s *Service) describeFrame(ctx context.Context, model registry.Model, framePath string) (map[string]any, error) {
	prompt := "分析视频关键帧，只输出 JSON：content 简短画面描述，shot_scale 景别，camera_motion 运镜，scene_type 场景类型，emotion 情绪。"
	output, err := s.registry.DescribeImage(ctx, model, framePath, prompt)
	if err != nil {
		return nil, err
	}
	start, end := strings.IndexByte(output, '{'), strings.LastIndexByte(output, '}')
	if start < 0 || end <= start {
		return nil, errors.New("视觉模型未返回 JSON")
	}
	var result map[string]any
	if err := json.Unmarshal([]byte(output[start:end+1]), &result); err != nil {
		return nil, err
	}
	return result, nil
}

func buildShots(sceneTimes []float64, duration, fps, minimum float64) []domain.Shot {
	boundaries := []float64{0}
	for _, value := range sceneTimes {
		if value-boundaries[len(boundaries)-1] >= minimum && duration-value >= minimum {
			boundaries = append(boundaries, value)
		}
	}
	boundaries = append(boundaries, duration)
	shots := make([]domain.Shot, 0, len(boundaries)-1)
	for index := 0; index+1 < len(boundaries); index++ {
		start, end := round(boundaries[index], 3), round(boundaries[index+1], 3)
		if end <= start {
			continue
		}
		shots = append(shots, domain.Shot{
			Index: len(shots), Start: start, End: end, Duration: round(end-start, 3),
			StartFrame: int64(math.Round(start * fps)), EndFrame: int64(math.Round(end * fps)),
		})
	}
	return shots
}

func alignBeats(shots []domain.Shot, beats []float64, tolerance float64) int {
	aligned := 0
	for index := range shots {
		best := math.Inf(1)
		for _, beat := range beats {
			offset := math.Abs(beat - shots[index].Start)
			if offset < best {
				best = offset
			}
			if beat > shots[index].Start+tolerance {
				break
			}
		}
		if best <= tolerance {
			offset := round(best, 3)
			shots[index].BeatAligned, shots[index].BeatOffset = true, &offset
			aligned++
		}
	}
	return aligned
}

func analyzeAudio(ctx context.Context, tools xffmpeg.Tools, source string, mediaDuration float64) (domain.AudioInfo, error) {
	const sampleRate, frameSize = 22050, 1024
	stream, err := tools.StartPCM(ctx, source, sampleRate)
	if err != nil {
		return domain.AudioInfo{}, err
	}
	reader := bufio.NewReaderSize(stream, frameSize*4)
	frameBytes := make([]byte, frameSize*2)
	energies := make([]float64, 0, int(mediaDuration*sampleRate/frameSize)+1)
	for {
		count, readErr := io.ReadFull(reader, frameBytes)
		if count > 1 {
			var sum float64
			for offset := 0; offset+1 < count; offset += 2 {
				sample := int16(binary.LittleEndian.Uint16(frameBytes[offset : offset+2]))
				normalized := float64(sample) / 32768
				sum += normalized * normalized
			}
			energies = append(energies, math.Sqrt(sum/math.Max(1, float64(count/2))))
		}
		if readErr != nil {
			if !errors.Is(readErr, io.EOF) && !errors.Is(readErr, io.ErrUnexpectedEOF) {
				_ = stream.Close()
				return domain.AudioInfo{}, readErr
			}
			break
		}
	}
	_ = stream.Close()
	if err := stream.Wait(); err != nil {
		return domain.AudioInfo{}, err
	}
	if len(energies) == 0 {
		return domain.AudioInfo{Duration: mediaDuration, Beats: []float64{}, SilenceRegions: []domain.TimeRegion{}, SFXCandidates: []domain.SFXCandidate{}, SpeechRegions: []domain.TimeRegion{}, Segments: []domain.Transcript{}, Method: "go_energy"}, nil
	}
	frameSeconds := float64(frameSize) / sampleRate
	mean, maximum := meanMax(energies)
	onsets := make([]float64, len(energies))
	for index := 1; index < len(energies); index++ {
		onsets[index] = math.Max(0, energies[index]-energies[index-1])
	}
	tempo, lag := estimateTempo(onsets, frameSeconds)
	beats := beatGrid(onsets, lag, frameSeconds, mediaDuration)
	silence := regionsByThreshold(energies, frameSeconds, math.Max(0.002, mean*0.25), false, 0.3)
	speech := regionsByThreshold(energies, frameSeconds, math.Max(0.008, mean*0.75), true, 0.35)
	return domain.AudioInfo{
		Duration: round(mediaDuration, 3), TempoBPM: round(tempo, 2), Beats: beats, BeatCount: len(beats),
		RMSMean: round(mean, 5), RMSMax: round(maximum, 5), SilenceRegions: silence,
		SFXCandidates: transientCandidates(onsets, frameSeconds), SpeechRegions: speech,
		Segments: []domain.Transcript{}, Method: "go_energy_autocorrelation",
	}, nil
}

func estimateTempo(onsets []float64, frameSeconds float64) (float64, int) {
	if len(onsets) < 20 {
		return 0, 0
	}
	minLag := max(1, int(math.Round(60/(180*frameSeconds))))
	maxLag := min(len(onsets)/2, int(math.Round(60/(60*frameSeconds))))
	bestLag, bestScore := 0, 0.0
	for lag := minLag; lag <= maxLag; lag++ {
		var score, left, right float64
		for index := lag; index < len(onsets); index++ {
			a, b := onsets[index], onsets[index-lag]
			score, left, right = score+a*b, left+a*a, right+b*b
		}
		if left > 0 && right > 0 {
			score /= math.Sqrt(left * right)
		}
		if score > bestScore {
			bestScore, bestLag = score, lag
		}
	}
	if bestLag == 0 || bestScore < 0.05 {
		return 0, 0
	}
	return 60 / (float64(bestLag) * frameSeconds), bestLag
}

func beatGrid(onsets []float64, lag int, frameSeconds, duration float64) []float64 {
	if lag <= 0 || len(onsets) == 0 {
		return []float64{}
	}
	bestPhase, bestScore := 0, 0.0
	for phase := 0; phase < lag; phase++ {
		var score float64
		for index := phase; index < len(onsets); index += lag {
			score += onsets[index]
		}
		if score > bestScore {
			bestScore, bestPhase = score, phase
		}
	}
	beats := make([]float64, 0, int(duration/(float64(lag)*frameSeconds))+1)
	for index := bestPhase; ; index += lag {
		second := float64(index) * frameSeconds
		if second > duration {
			break
		}
		beats = append(beats, round(second, 3))
	}
	return beats
}

func transientCandidates(onsets []float64, frameSeconds float64) []domain.SFXCandidate {
	mean, _ := meanMax(onsets)
	var variance float64
	for _, value := range onsets {
		variance += (value - mean) * (value - mean)
	}
	deviation := math.Sqrt(variance / math.Max(1, float64(len(onsets))))
	threshold := mean + 2.5*deviation
	result := make([]domain.SFXCandidate, 0)
	lastTime := -1.0
	for index, value := range onsets {
		second := float64(index) * frameSeconds
		if value >= threshold && second-lastTime >= 0.2 {
			result = append(result, domain.SFXCandidate{Time: round(second, 3), Strength: round(value/math.Max(threshold, 1e-9), 3)})
			lastTime = second
		}
	}
	if len(result) > 200 {
		result = result[:200]
	}
	return result
}

func regionsByThreshold(values []float64, frameSeconds, threshold float64, above bool, minimumDuration float64) []domain.TimeRegion {
	result := make([]domain.TimeRegion, 0)
	start := -1
	flush := func(end int) {
		if start < 0 {
			return
		}
		startTime, endTime := float64(start)*frameSeconds, float64(end)*frameSeconds
		if endTime-startTime >= minimumDuration {
			result = append(result, domain.TimeRegion{Start: round(startTime, 3), End: round(endTime, 3)})
		}
		start = -1
	}
	for index, value := range values {
		matches := value >= threshold
		if !above {
			matches = value < threshold
		}
		if matches && start < 0 {
			start = index
		} else if !matches {
			flush(index)
		}
	}
	flush(len(values))
	return result
}

func describeFrameHeuristic(path string, shot *domain.Shot) {
	file, err := os.Open(path)
	if err != nil {
		return
	}
	defer file.Close()
	imageValue, _, err := image.Decode(file)
	if err != nil {
		return
	}
	bounds := imageValue.Bounds()
	step := max(1, min(bounds.Dx(), bounds.Dy())/80)
	var lumaSum, saturationSum, edgeSum float64
	var count float64
	for y := bounds.Min.Y; y < bounds.Max.Y; y += step {
		previous := -1.0
		for x := bounds.Min.X; x < bounds.Max.X; x += step {
			r16, g16, b16, _ := imageValue.At(x, y).RGBA()
			r, g, b := float64(r16>>8), float64(g16>>8), float64(b16>>8)
			luma := 0.2126*r + 0.7152*g + 0.0722*b
			maximum, minimum := math.Max(r, math.Max(g, b)), math.Min(r, math.Min(g, b))
			lumaSum += luma
			if maximum > 0 {
				saturationSum += (maximum - minimum) / maximum
			}
			if previous >= 0 {
				edgeSum += math.Abs(luma - previous)
			}
			previous, count = luma, count+1
		}
	}
	brightness, saturation, edges := lumaSum/math.Max(1, count), saturationSum/math.Max(1, count), edgeSum/math.Max(1, count)
	tone := "均衡"
	if brightness < 70 {
		tone = "低调暗色"
	} else if brightness > 180 {
		tone = "明亮高调"
	}
	color := "自然色彩"
	if saturation > 0.5 {
		color = "高饱和色彩"
	} else if saturation < 0.18 {
		color = "低饱和色彩"
	}
	detail := "画面稳定"
	if edges > 18 {
		detail = "细节丰富"
	}
	shot.Content = fmt.Sprintf("%s、%s，%s的画面", tone, color, detail)
	shot.ContentMethod, shot.ShotScale, shot.CameraMotion = "go_image_heuristic", "中景", "未知"
	shot.SceneType = "general"
	if brightness < 70 {
		shot.Emotion = "沉静"
	} else if saturation > 0.5 {
		shot.Emotion = "活跃"
	} else {
		shot.Emotion = "平稳"
	}
}

func applyDescription(description map[string]any, shot *domain.Shot) {
	assign := func(key string, destination *string) {
		if value, ok := description[key].(string); ok && strings.TrimSpace(value) != "" {
			*destination = strings.TrimSpace(value)
		}
	}
	assign("content", &shot.Content)
	assign("shot_scale", &shot.ShotScale)
	assign("camera_motion", &shot.CameraMotion)
	assign("scene_type", &shot.SceneType)
	assign("emotion", &shot.Emotion)
	shot.ContentMethod = "vlm"
}

func summarize(dna *domain.DNA) string {
	pace := "慢"
	if dna.Meta.AvgShotDuration < 2 {
		pace = "极快"
	} else if dna.Meta.AvgShotDuration < 4 {
		pace = "快"
	} else if dna.Meta.AvgShotDuration < 8 {
		pace = "中等"
	}
	parts := []string{
		fmt.Sprintf("共 %d 个镜头，平均 %.2f 秒/镜", dna.Meta.TotalShots, dna.Meta.AvgShotDuration),
		"整体节奏偏" + pace,
		fmt.Sprintf("卡点率约 %.0f%%", dna.Meta.BeatAlignmentRatio*100),
	}
	if cuts := dna.Meta.Transitions["cut"]; cuts > 0 {
		parts = append(parts, fmt.Sprintf("转场：硬切×%d", cuts))
	}
	if dna.Audio.TempoBPM > 0 {
		parts = append(parts, fmt.Sprintf("BGM 约 %.0f BPM，检测到 %d 个节拍点", dna.Audio.TempoBPM, dna.Audio.BeatCount))
	} else {
		parts = append(parts, "未检测到明显节拍")
	}
	if len(dna.Audio.SFXCandidates) > 0 {
		parts = append(parts, fmt.Sprintf("检测到 %d 个强瞬态", len(dna.Audio.SFXCandidates)))
	}
	return strings.Join(parts, "；") + "。"
}

func meanMax(values []float64) (float64, float64) {
	var sum, maximum float64
	for _, value := range values {
		sum += value
		maximum = math.Max(maximum, value)
	}
	return sum / math.Max(1, float64(len(values))), maximum
}

func round(value float64, places int) float64 {
	factor := math.Pow10(places)
	return math.Round(value*factor) / factor
}

func mustJSON(value any) string {
	payload, _ := json.Marshal(value)
	return string(payload)
}
