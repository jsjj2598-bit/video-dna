package xwhisper

import "testing"

func TestParseJSONWhisperCpp(t *testing.T) {
	segments, language, err := parseJSON([]byte(`{"language":"zh","transcription":[{"timestamps":{"from":"00:00:01.200","to":"00:00:02.500"},"text":"你好"}]}`))
	if err != nil || language != "zh" || len(segments) != 1 || segments[0].Start != 1.2 || segments[0].End != 2.5 {
		t.Fatalf("unexpected result: %#v %s %v", segments, language, err)
	}
}

func TestParseJSONSegments(t *testing.T) {
	segments, _, err := parseJSON([]byte(`{"segments":[{"start":0,"end":1,"text":"hello"}]}`))
	if err != nil || len(segments) != 1 || segments[0].Text != "hello" {
		t.Fatalf("unexpected result: %#v %v", segments, err)
	}
}
