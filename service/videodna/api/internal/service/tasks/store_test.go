package tasks

import (
	"errors"
	"testing"
	"time"
)

func TestStoreBoundsLogsAndTerminalState(t *testing.T) {
	store := NewStore(time.Hour, 3)
	store.Create("s1", "upload")
	for index := 0; index < 10; index++ {
		store.Report("s1", "work", index*10, "progress")
	}
	store.Fail("s1", errors.New("boom"))
	state, ok := store.Get("s1")
	if !ok || !state.Done || state.Error != "boom" {
		t.Fatalf("invalid terminal state: %#v", state)
	}
	if len(state.Logs) > 3 {
		t.Fatalf("logs are unbounded: %d", len(state.Logs))
	}
}
