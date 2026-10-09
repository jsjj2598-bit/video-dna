package analyzer

import "testing"

func TestEvaluateTransitions(t *testing.T) {
	score := EvaluateTransitions(map[float64]string{10: "cut", 20: "dissolve"}, map[float64]string{10.04: "cut", 20.1: "fade", 30: "cut"}, .15)
	if score.Correct != 1 || score.Expected != 2 || score.Predicted != 3 {
		t.Fatalf("unexpected score: %#v", score)
	}
}
