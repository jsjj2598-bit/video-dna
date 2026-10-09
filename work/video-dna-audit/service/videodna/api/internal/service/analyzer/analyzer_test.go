package analyzer

import (
	"math"
	"testing"
)

func TestBeatGridDoesNotDuplicateTimestamps(t *testing.T) {
	onsets := make([]float64, 12)
	onsets[1], onsets[5], onsets[9] = 1, 1, 1

	beats := beatGrid(onsets, 4, 0.25, 3)
	want := []float64{0.25, 1.25, 2.25}
	if len(beats) != len(want) {
		t.Fatalf("beat count = %d, want %d: %#v", len(beats), len(want), beats)
	}
	for index := range want {
		if math.Abs(beats[index]-want[index]) > 1e-9 {
			t.Fatalf("beat[%d] = %v, want %v", index, beats[index], want[index])
		}
	}
}

func TestBuildShotsFiltersShortBoundaries(t *testing.T) {
	shots := buildShots([]float64{0.1, 1, 1.1, 2.7}, 3, 25, 0.25)
	if len(shots) != 3 {
		t.Fatalf("shot count = %d, want 3: %#v", len(shots), shots)
	}
	if shots[0].Start != 0 || shots[0].End != 1 || shots[2].End != 3 {
		t.Fatalf("unexpected shot boundaries: %#v", shots)
	}
}
