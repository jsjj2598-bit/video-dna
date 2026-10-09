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

func TestStoreCancelIsTerminal(t *testing.T) {
	store := NewStore(time.Hour, 20)
	store.Create("cancel-me", "uploaded")
	store.Report("cancel-me", "frames", 60, "extracting")
	if !store.Cancel("cancel-me") {
		t.Fatal("Cancel returned false for an active task")
	}
	store.Report("cancel-me", "done", 100, "should be ignored")
	state, ok := store.Get("cancel-me")
	if !ok {
		t.Fatal("cancelled task disappeared")
	}
	if state.Stage != "cancelled" || !state.Done || state.Error == "" {
		t.Fatalf("unexpected cancelled state: %#v", state)
	}
	if store.Cancel("cancel-me") {
		t.Fatal("Cancel returned true for a terminal task")
	}
}
