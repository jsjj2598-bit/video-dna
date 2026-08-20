package templates

import (
	"math"
	"testing"

	"github.com/jsjj2598-bit/video-dna/service/videodna/api/internal/domain"
)

func TestBuildCutPlanStaysInBounds(t *testing.T) {
	template, ok := Find("beat_kardian")
	if !ok {
		t.Fatal("built-in template missing")
	}
	target := &domain.DNA{Meta: domain.Meta{Duration: 6}, Audio: domain.AudioInfo{Beats: []float64{.8, 1.6, 2.4, 3.2, 4, 4.8, 5.6}}}
	plan, err := BuildCutPlan(TemplateDNA(template, 8), target, .25)
	if err != nil {
		t.Fatal(err)
	}
	if len(plan.Cuts) == 0 || math.Abs(plan.Cuts[len(plan.Cuts)-1].End-6) > .001 {
		t.Fatalf("invalid plan: %#v", plan)
	}
	for _, cut := range plan.Cuts {
		if cut.Start < 0 || cut.End <= cut.Start || cut.End > 6.001 {
			t.Fatalf("out-of-bounds cut: %#v", cut)
		}
	}
}
