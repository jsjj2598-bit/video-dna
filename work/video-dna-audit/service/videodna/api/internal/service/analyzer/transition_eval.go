package analyzer

import "sort"

// TransitionScore evaluates predictions against a labelled boundary set.
// Labels use cut, dissolve, fade and flash; absent labels are ignored.
type TransitionScore struct {
	Precision, Recall, F1        float64
	Correct, Predicted, Expected int
}

func EvaluateTransitions(expected, predicted map[float64]string, tolerance float64) TransitionScore {
	keys := make([]float64, 0, len(expected))
	for key := range expected {
		keys = append(keys, key)
	}
	sort.Float64s(keys)
	used := map[float64]bool{}
	score := TransitionScore{Expected: len(expected), Predicted: len(predicted)}
	for key, label := range expected {
		for candidate, prediction := range predicted {
			if !used[candidate] && abs(candidate-key) <= tolerance && label == prediction {
				used[candidate] = true
				score.Correct++
				break
			}
		}
	}
	if score.Predicted > 0 {
		score.Precision = float64(score.Correct) / float64(score.Predicted)
	}
	if score.Expected > 0 {
		score.Recall = float64(score.Correct) / float64(score.Expected)
	}
	if score.Precision+score.Recall > 0 {
		score.F1 = 2 * score.Precision * score.Recall / (score.Precision + score.Recall)
	}
	return score
}
func abs(value float64) float64 {
	if value < 0 {
		return -value
	}
	return value
}
