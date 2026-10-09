package storage

import (
	"bytes"
	"testing"

	"github.com/jsjj2598-bit/video-dna/service/videodna/api/internal/domain"
)

func TestStorageRoundTripAndTraversal(t *testing.T) {
	service, err := New(t.TempDir(), 1024, 4096)
	if err != nil {
		t.Fatal(err)
	}
	if _, err := service.SessionDir("../escape"); err == nil {
		t.Fatal("path traversal was accepted")
	}
	if _, err := service.SaveUpload("session1", "video.txt", bytes.NewBufferString("bad")); err == nil {
		t.Fatal("unsupported extension was accepted")
	}
	if _, err := service.SaveUpload("session1", "video.mp4", bytes.NewBufferString("video")); err != nil {
		t.Fatal(err)
	}
	dna := &domain.DNA{Meta: domain.Meta{Duration: 1}, Audio: domain.AudioInfo{Beats: []float64{}}, Shots: []domain.Shot{}}
	if err := service.SaveResult("session1", dna, "video.mp4"); err != nil {
		t.Fatal(err)
	}
	loaded, err := service.ReadResult("session1")
	if err != nil {
		t.Fatal(err)
	}
	if loaded.SessionID != "session1" || loaded.VideoURL == "" {
		t.Fatalf("metadata missing: %#v", loaded)
	}
}
