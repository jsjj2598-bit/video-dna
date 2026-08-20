package exporter

import (
	"archive/zip"
	"bytes"
	"strings"
	"testing"

	"github.com/jsjj2598-bit/video-dna/service/videodna/api/internal/domain"
)

func testDNA() *domain.DNA {
	return &domain.DNA{
		Meta: domain.Meta{Duration: 4, FPS: 30, Resolution: "1920x1080", TotalShots: 2, AvgShotDuration: 2},
		Shots: []domain.Shot{
			{Index: 0, Start: 0, End: 2, Duration: 2, Transition: "cut"},
			{Index: 1, Start: 2, End: 4, Duration: 2, Transition: "dissolve", TransitionDuration: .5, Transcript: "hello"},
		},
		Audio: domain.AudioInfo{TempoBPM: 120, Beats: []float64{0, .5, 1}, SpeechRegions: []domain.TimeRegion{{Start: 1.2345, End: 2.5, Text: "字幕"}}},
	}
}

func TestRenderFormats(t *testing.T) {
	tests := map[string]string{"edl": "D 015", "fcp7xml": "<xmeml", "cutmark": "videodna-cutmark-v1", "srt": "00:00:01,235"}
	for format, expected := range tests {
		t.Run(format, func(t *testing.T) {
			file, err := Render(testDNA(), format, "")
			if err != nil {
				t.Fatal(err)
			}
			if !strings.Contains(string(file.Data), expected) {
				t.Fatalf("%s export missing %q", format, expected)
			}
		})
	}
}

func TestRenderAllZip(t *testing.T) {
	file, err := Render(testDNA(), "all", "")
	if err != nil {
		t.Fatal(err)
	}
	archive, err := zip.NewReader(bytes.NewReader(file.Data), int64(len(file.Data)))
	if err != nil {
		t.Fatal(err)
	}
	if len(archive.File) != 4 {
		t.Fatalf("got %d files, want 4", len(archive.File))
	}
}
