// Package templates builds validated rhythm-based editing plans.
package templates

import (
	"errors"
	"math"
	"sort"

	"github.com/jsjj2598-bit/video-dna/service/videodna/api/internal/domain"
)

// RhythmTemplate is a built-in editing rhythm.
type RhythmTemplate struct {
	ID      string    `json:"id"`
	Name    string    `json:"name"`
	Desc    string    `json:"desc"`
	Icon    string    `json:"icon"`
	BPM     float64   `json:"bpm"`
	Shot    float64   `json:"shot"`
	Pattern []float64 `json:"pattern"`
}

// Builtins are stable IDs consumed by the desktop UI.
var Builtins = []RhythmTemplate{
	{ID: "beat_kardian", Name: "抖音卡点快剪", Desc: "0.8s 短镜卡点，适合变装、舞蹈和高燃混剪", Icon: "🔥", BPM: 128, Shot: 0.8, Pattern: []float64{1, .8, .8, .6, .8, .8, 1.2, .8}},
	{ID: "vlog_relax", Name: "Vlog 生活慢叙", Desc: "3~6s 长镜慢节奏，适合日常、旅行和美食", Icon: "🌿", BPM: 92, Shot: 4, Pattern: []float64{4, 3.5, 5, 3, 4.5, 3}},
	{ID: "film_cinema", Name: "电影感叙事", Desc: "5~8s 大景别慢镜，适合短剧、宣传片和情感内容", Icon: "🎬", BPM: 70, Shot: 6, Pattern: []float64{6, 5, 8, 5, 6, 4, 7}},
	{ID: "game_esport", Name: "电竞高燃卡点", Desc: "0.4~1s 极速切镜，适合游戏集锦", Icon: "🎮", BPM: 144, Shot: .6, Pattern: []float64{.6, .4, .6, .8, .5, .4, .6, .8, .5, 1}},
	{ID: "story_bite", Name: "短剧钩子节奏", Desc: "开头强钩子，中段对话推进，结尾反转留白", Icon: "🎭", BPM: 100, Shot: 2.5, Pattern: []float64{3, 2, 2.5, 2, 2.5, 3, 2, 2.5, 3.5, 4}},
}

// Find returns one built-in template.
func Find(templateID string) (RhythmTemplate, bool) {
	for _, template := range Builtins {
		if template.ID == templateID {
			return template, true
		}
	}
	return RhythmTemplate{}, false
}

// TemplateDNA expands a repeating rhythm to the requested duration.
func TemplateDNA(template RhythmTemplate, duration float64) *domain.DNA {
	shots := make([]domain.Shot, 0)
	for cursor, index := 0.0, 0; cursor < duration-.001; index++ {
		shotDuration := math.Min(template.Pattern[index%len(template.Pattern)], duration-cursor)
		shots = append(shots, domain.Shot{Index: index, Start: round(cursor, 3), End: round(cursor+shotDuration, 3), Duration: round(shotDuration, 3)})
		cursor += shotDuration
	}
	return &domain.DNA{
		Meta:  domain.Meta{Duration: round(duration, 3), TotalShots: len(shots)},
		Shots: shots, Audio: domain.AudioInfo{TempoBPM: template.BPM}, SourceFile: template.Name,
	}
}

// BuildCutPlan maps relative template boundaries to a target DNA.
func BuildCutPlan(template, target *domain.DNA, minimumShotDuration float64) (*domain.CutPlan, error) {
	if target == nil || target.Meta.Duration <= 0 {
		return nil, errors.New("目标视频时长无效")
	}
	if template == nil || len(template.Shots) == 0 {
		return nil, errors.New("模板缺少镜头")
	}
	shots := append([]domain.Shot(nil), template.Shots...)
	sort.Slice(shots, func(i, j int) bool { return shots[i].Start < shots[j].Start })
	templateDuration := math.Max(template.Meta.Duration, shots[len(shots)-1].End)
	if templateDuration <= 0 {
		return nil, errors.New("模板时长无效")
	}
	if minimumShotDuration <= 0 {
		minimumShotDuration = .25
	}
	maxSegments := max(1, int(target.Meta.Duration/minimumShotDuration))
	desired := make([]float64, 0, len(shots)-1)
	for _, shot := range shots[:len(shots)-1] {
		desired = append(desired, math.Max(0, math.Min(1, shot.End/templateDuration)))
	}
	if len(desired) > maxSegments-1 {
		step := float64(len(desired)) / float64(max(1, maxSegments-1))
		reduced := make([]float64, 0, maxSegments-1)
		for index := 0; index < maxSegments-1; index++ {
			reduced = append(reduced, desired[min(len(desired)-1, int(float64(index)*step))])
		}
		desired = reduced
	}
	beats := append([]float64(nil), target.Audio.Beats...)
	sort.Float64s(beats)
	boundaries := []float64{0}
	alignedFlags := make([]bool, 0, len(desired))
	for index, ratio := range desired {
		raw, boundary, aligned := ratio*target.Meta.Duration, ratio*target.Meta.Duration, false
		if len(beats) > 0 {
			nearest := beats[0]
			for _, beat := range beats[1:] {
				if math.Abs(beat-raw) < math.Abs(nearest-raw) {
					nearest = beat
				}
			}
			if math.Abs(nearest-raw) <= .45 {
				boundary, aligned = nearest, true
			}
		}
		lower := boundaries[len(boundaries)-1] + minimumShotDuration
		remaining := len(desired) - index
		upper := target.Meta.Duration - float64(remaining)*minimumShotDuration
		boundary = math.Min(math.Max(boundary, lower), upper)
		if boundary <= boundaries[len(boundaries)-1] || boundary >= target.Meta.Duration {
			continue
		}
		boundaries = append(boundaries, boundary)
		alignedFlags = append(alignedFlags, aligned)
	}
	boundaries = append(boundaries, target.Meta.Duration)
	cuts := make([]domain.Cut, 0, len(boundaries)-1)
	for index := 0; index+1 < len(boundaries); index++ {
		start, end := boundaries[index], boundaries[index+1]
		if end-start < .001 {
			continue
		}
		aligned := index < len(alignedFlags) && alignedFlags[index]
		cuts = append(cuts, domain.Cut{
			Index: len(cuts), Start: round(start, 3), End: round(end, 3), Duration: round(end-start, 3),
			AlignedToBeat: aligned, TemplateRatio: round(end/target.Meta.Duration, 4),
		})
	}
	alignedCount := 0
	for _, cut := range cuts {
		if cut.AlignedToBeat {
			alignedCount++
		}
	}
	return &domain.CutPlan{
		Source: template.SourceFile, TemplateDuration: round(templateDuration, 3), TargetDuration: round(target.Meta.Duration, 3),
		Cuts: cuts, Total: len(cuts), BeatAlignedCount: alignedCount,
	}, nil
}

func round(value float64, places int) float64 {
	factor := math.Pow10(places)
	return math.Round(value*factor) / factor
}
