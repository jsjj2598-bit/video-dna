// Package exporter converts Video DNA into common NLE interchange formats.
package exporter

import (
	"archive/zip"
	"bytes"
	"encoding/json"
	"encoding/xml"
	"errors"
	"fmt"
	"math"
	"net/url"
	"path/filepath"
	"strings"

	"github.com/jsjj2598-bit/video-dna/service/videodna/api/internal/domain"
)

// File is a downloadable export artifact.
type File struct {
	Name        string
	ContentType string
	Data        []byte
}

// Render generates one supported export format in memory.
func Render(dna *domain.DNA, format, sourcePath string) (File, error) {
	if dna == nil {
		return File{}, errors.New("DNA 数据不能为空")
	}
	format = strings.ToLower(strings.TrimSpace(format))
	if format == "" {
		format = "cutmark"
	}
	switch format {
	case "edl":
		return File{Name: "video-dna.edl", ContentType: "text/plain; charset=utf-8", Data: []byte(renderEDL(dna))}, nil
	case "fcp7xml", "xml":
		return File{Name: "video-dna.xml", ContentType: "application/xml; charset=utf-8", Data: []byte(renderFCP7XML(dna, sourcePath))}, nil
	case "cutmark", "json":
		data, err := renderCutmark(dna)
		return File{Name: "video-dna-cuts.json", ContentType: "application/json; charset=utf-8", Data: data}, err
	case "srt":
		return File{Name: "video-dna-subtitles.srt", ContentType: "application/x-subrip; charset=utf-8", Data: []byte(renderSRT(dna))}, nil
	case "all", "zip":
		return renderAll(dna, sourcePath)
	default:
		return File{}, fmt.Errorf("不支持的导出格式: %s", format)
	}
}

func renderAll(dna *domain.DNA, sourcePath string) (File, error) {
	var buffer bytes.Buffer
	archive := zip.NewWriter(&buffer)
	cutmark, err := renderCutmark(dna)
	if err != nil {
		return File{}, err
	}
	files := []struct {
		name string
		data []byte
	}{
		{"dna.edl", []byte(renderEDL(dna))},
		{"dna.xml", []byte(renderFCP7XML(dna, sourcePath))},
		{"dna_cuts.json", cutmark},
		{"dna_subtitles.srt", []byte(renderSRT(dna))},
	}
	for _, item := range files {
		entry, createErr := archive.Create(item.name)
		if createErr != nil {
			_ = archive.Close()
			return File{}, createErr
		}
		if _, writeErr := entry.Write(item.data); writeErr != nil {
			_ = archive.Close()
			return File{}, writeErr
		}
	}
	if err := archive.Close(); err != nil {
		return File{}, err
	}
	return File{Name: "video-dna-exports.zip", ContentType: "application/zip", Data: buffer.Bytes()}, nil
}

func renderEDL(dna *domain.DNA) string {
	fps := normalizedFPS(dna.Meta.FPS)
	var output strings.Builder
	output.WriteString("TITLE: Video DNA Analysis\nFCM: NON-DROP FRAME\n\n")
	for index, shot := range dna.Shots {
		transition := "C    "
		if shot.Transition == "dissolve" || shot.Transition == "fade" || shot.Transition == "white_flash" {
			duration := shot.TransitionDuration
			if duration <= 0 {
				duration = 0.5
			}
			transition = fmt.Sprintf("D %03d", max(1, int(math.Round(duration*fps))))
		}
		fmt.Fprintf(&output, "%03d  AX       V     %s    %s %s %s %s\n", index+1, transition,
			timecode(shot.Start, fps), timecode(shot.End, fps), timecode(shot.Start, fps), timecode(shot.End, fps))
		if shot.Keyframe != "" {
			fmt.Fprintf(&output, "* KEYFRAME: frames/%s\n", shot.Keyframe)
		}
		if shot.Transition != "" {
			fmt.Fprintf(&output, "* TRANSITION: %s\n", shot.Transition)
		}
		if shot.Transcript != "" {
			fmt.Fprintf(&output, "* DIALOG: %s\n", truncateRunes(shot.Transcript, 60))
		}
		if transition[0] == 'D' {
			duration := shot.TransitionDuration
			if duration <= 0 {
				duration = 0.5
			}
			fmt.Fprintf(&output, "* EFFECT NAME: %s\n* EFFECT DURATION: %d\n", shot.Transition, int(math.Round(duration*fps)))
		}
		output.WriteByte('\n')
	}
	fmt.Fprintf(&output, "* TOTAL EVENTS: %d\n* DURATION: %s\n", len(dna.Shots), timecode(dna.Meta.Duration, fps))
	return output.String()
}

func renderFCP7XML(dna *domain.DNA, sourcePath string) string {
	fps := normalizedFPS(dna.Meta.FPS)
	timebase := int(math.Round(fps))
	ntsc := "FALSE"
	if math.Abs(fps-math.Round(fps)) > 0.01 {
		ntsc = "TRUE"
	}
	durationFrames := int(math.Round(dna.Meta.Duration * fps))
	var output strings.Builder
	output.WriteString(`<xmeml version="4"><sequence>`)
	fmt.Fprintf(&output, "<duration>%d</duration><rate><timebase>%d</timebase><ntsc>%s</ntsc></rate>", durationFrames, timebase, ntsc)
	fmt.Fprintf(&output, "<media><video><format><samplecharacteristics><rate><timebase>%d</timebase><ntsc>%s</ntsc></rate></samplecharacteristics></format><track>", timebase, ntsc)
	for index, shot := range dna.Shots {
		start := int(math.Round(shot.Start * fps))
		end := int(math.Round(shot.End * fps))
		duration := max(0, end-start)
		if index > 0 && shot.Transition != "" && shot.Transition != "cut" {
			seconds := shot.TransitionDuration
			if seconds <= 0 {
				seconds = 0.5
			}
			frames := max(1, int(math.Round(seconds*fps)))
			fmt.Fprintf(&output, "<transitionitem><start>%d</start><end>%d</end><alignment>center</alignment><effect><name>%s</name><effectid>Cross Dissolve</effectid><effecttype>transition</effecttype><mediatype>video</mediatype></effect></transitionitem>", max(0, start-frames/2), start+frames/2, escapeXML(shot.Transition))
		}
		fmt.Fprintf(&output, "<clipitem><name>Shot %d (%s)</name><duration>%d</duration><in>%d</in><out>%d</out><start>%d</start><end>%d</end>", index, escapeXML(defaultString(shot.Transition, "cut")), duration, start, end, start, end)
		if index == 0 {
			filename := "source-video"
			pathURL := ""
			if sourcePath != "" {
				absolute, _ := filepath.Abs(sourcePath)
				filename = filepath.Base(absolute)
				pathURL = (&url.URL{Scheme: "file", Path: filepath.ToSlash(absolute)}).String()
			}
			fmt.Fprintf(&output, "<file id=\"source-media\"><name>%s</name><pathurl>%s</pathurl><duration>%d</duration><rate><timebase>%d</timebase><ntsc>%s</ntsc></rate></file>", escapeXML(filename), escapeXML(pathURL), durationFrames, timebase, ntsc)
		} else {
			output.WriteString(`<file id="source-media"/>`)
		}
		comments := make([]string, 0, 2)
		if shot.Transcript != "" {
			comments = append(comments, "DIALOG: "+truncateRunes(shot.Transcript, 200))
		}
		if shot.BeatAligned {
			comments = append(comments, "BEAT_ALIGNED")
		}
		if len(comments) > 0 {
			fmt.Fprintf(&output, "<comment>%s</comment>", escapeXML(strings.Join(comments, "\n")))
		}
		output.WriteString(`</clipitem>`)
	}
	output.WriteString(`</track></video></media>`)
	for _, beat := range dna.Audio.Beats {
		frame := int(math.Round(beat * fps))
		fmt.Fprintf(&output, "<marker><name>Beat</name><comment>Detected beat</comment><in>%d</in><out>%d</out></marker>", frame, frame)
	}
	for _, candidate := range dna.Audio.SFXCandidates {
		frame := int(math.Round(candidate.Time * fps))
		comment := defaultString(candidate.Class, "Sound effect candidate")
		fmt.Fprintf(&output, "<marker><name>SFX</name><comment>%s</comment><in>%d</in><out>%d</out></marker>", escapeXML(comment), frame, frame)
	}
	output.WriteString(`</sequence></xmeml>`)
	return output.String()
}

func renderCutmark(dna *domain.DNA) ([]byte, error) {
	type cut struct {
		Index       int     `json:"index"`
		Start       float64 `json:"start_sec"`
		End         float64 `json:"end_sec"`
		Duration    float64 `json:"duration_sec"`
		Transition  string  `json:"transition,omitempty"`
		BeatAligned bool    `json:"beat_aligned"`
		Transcript  string  `json:"transcript,omitempty"`
		Content     string  `json:"content,omitempty"`
	}
	cuts := make([]cut, 0, len(dna.Shots))
	for _, shot := range dna.Shots {
		cuts = append(cuts, cut{shot.Index, shot.Start, shot.End, shot.Duration, shot.Transition, shot.BeatAligned, shot.Transcript, shot.Content})
	}
	result := map[string]any{
		"format": "videodna-cutmark-v1",
		"meta":   map[string]any{"duration_sec": dna.Meta.Duration, "fps": dna.Meta.FPS, "resolution": dna.Meta.Resolution, "total_shots": len(dna.Shots), "avg_shot_sec": dna.Meta.AvgShotDuration},
		"cuts":   cuts, "beats": dna.Audio.Beats, "bpm": dna.Audio.TempoBPM,
		"sfx": dna.Audio.SFXCandidates, "transcript": nil,
	}
	if dna.Audio.Text != "" {
		result["transcript"] = dna.Audio.Text
	}
	return json.MarshalIndent(result, "", "  ")
}

func renderSRT(dna *domain.DNA) string {
	var output strings.Builder
	for index, segment := range dna.Audio.SpeechRegions {
		text := defaultString(segment.Text, "[语音]")
		fmt.Fprintf(&output, "%d\n%s --> %s\n%s\n\n", index+1, srtTime(segment.Start), srtTime(segment.End), text)
	}
	return output.String()
}

func timecode(seconds, fps float64) string {
	framesPerSecond := max(1, int(math.Round(fps)))
	totalFrames := int(math.Round(max(0.0, seconds) * fps))
	frame := totalFrames % framesPerSecond
	totalSeconds := totalFrames / framesPerSecond
	return fmt.Sprintf("%02d:%02d:%02d:%02d", totalSeconds/3600, (totalSeconds%3600)/60, totalSeconds%60, frame)
}

func srtTime(seconds float64) string {
	totalMilliseconds := int64(math.Round(max(0.0, seconds) * 1000))
	hours := totalMilliseconds / 3_600_000
	remainder := totalMilliseconds % 3_600_000
	minutes := remainder / 60_000
	remainder %= 60_000
	return fmt.Sprintf("%02d:%02d:%02d,%03d", hours, minutes, remainder/1000, remainder%1000)
}

func escapeXML(value string) string {
	var output bytes.Buffer
	_ = xml.EscapeText(&output, []byte(value))
	return output.String()
}

func normalizedFPS(fps float64) float64 {
	if fps <= 0 {
		return 30
	}
	return fps
}

func defaultString(value, fallback string) string {
	if value == "" {
		return fallback
	}
	return value
}

func truncateRunes(value string, limit int) string {
	runes := []rune(value)
	if len(runes) <= limit {
		return value
	}
	return string(runes[:limit])
}
