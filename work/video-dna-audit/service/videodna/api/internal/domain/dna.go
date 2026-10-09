// Package domain defines the stable Video DNA interchange model.
package domain

// DNA is the persisted result consumed by the desktop UI and exporters.
type DNA struct {
	Meta          Meta      `json:"meta"`
	Audio         AudioInfo `json:"audio"`
	Shots         []Shot    `json:"shots"`
	Summary       string    `json:"summary"`
	SummaryMethod string    `json:"summary_method,omitempty"`
	SessionID     string    `json:"_session_id,omitempty"`
	SourceFile    string    `json:"_source_file,omitempty"`
	VideoURL      string    `json:"_video_url,omitempty"`
	FrameBase     string    `json:"_frame_base,omitempty"`
	CutPlan       *CutPlan  `json:"_cut_plan,omitempty"`
}

// Meta contains source media and editing statistics.
type Meta struct {
	Duration           float64        `json:"duration"`
	Resolution         string         `json:"resolution,omitempty"`
	Width              int            `json:"width"`
	Height             int            `json:"height"`
	FPS                float64        `json:"fps"`
	VideoCodec         string         `json:"video_codec,omitempty"`
	AudioCodec         string         `json:"audio_codec,omitempty"`
	SizeBytes          int64          `json:"size_bytes"`
	TotalShots         int            `json:"total_shots"`
	AvgShotDuration    float64        `json:"avg_shot_duration"`
	BeatAlignmentRatio float64        `json:"beat_alignment_ratio"`
	Transitions        map[string]int `json:"transitions"`
}

// Shot is one continuous editing interval.
type Shot struct {
	Index                int      `json:"index"`
	Start                float64  `json:"start"`
	End                  float64  `json:"end"`
	Duration             float64  `json:"duration"`
	StartFrame           int64    `json:"start_frame,omitempty"`
	EndFrame             int64    `json:"end_frame,omitempty"`
	BeatAligned          bool     `json:"beat_aligned"`
	BeatOffset           *float64 `json:"beat_offset"`
	Transition           string   `json:"transition,omitempty"`
	TransitionDuration   float64  `json:"transition_duration,omitempty"`
	TransitionConfidence *float64 `json:"transition_confidence,omitempty"`
	Keyframe             string   `json:"keyframe,omitempty"`
	Content              string   `json:"content,omitempty"`
	ContentMethod        string   `json:"content_method,omitempty"`
	CameraMotion         string   `json:"camera_motion,omitempty"`
	ShotScale            string   `json:"shot_scale,omitempty"`
	SceneType            string   `json:"scene_type,omitempty"`
	Emotion              string   `json:"emotion,omitempty"`
	FaceCount            int      `json:"face_count,omitempty"`
	Transcript           string   `json:"transcript,omitempty"`
}

// AudioInfo contains rhythm, energy and optional ASR results.
type AudioInfo struct {
	Duration       float64        `json:"duration"`
	TempoBPM       float64        `json:"tempo_bpm,omitempty"`
	Beats          []float64      `json:"beats"`
	BeatCount      int            `json:"beat_count"`
	RMSMean        float64        `json:"rms_mean,omitempty"`
	RMSMax         float64        `json:"rms_max,omitempty"`
	SilenceRegions []TimeRegion   `json:"silence_regions"`
	SFXCandidates  []SFXCandidate `json:"sfx_candidates"`
	SpeechRegions  []TimeRegion   `json:"speech_regions"`
	Segments       []Transcript   `json:"segments"`
	Text           string         `json:"text,omitempty"`
	Language       string         `json:"language,omitempty"`
	WordCount      int            `json:"word_count,omitempty"`
	Translation    string         `json:"translation,omitempty"`
	Method         string         `json:"method,omitempty"`
}

// TimeRegion is a detected interval in seconds.
type TimeRegion struct {
	Start float64 `json:"start"`
	End   float64 `json:"end"`
	Text  string  `json:"text,omitempty"`
}

// SFXCandidate is a strong audio transient.
type SFXCandidate struct {
	Time     float64 `json:"time"`
	Strength float64 `json:"strength"`
	Class    string  `json:"class,omitempty"`
}

// Transcript is one ASR segment.
type Transcript struct {
	Start float64 `json:"start"`
	End   float64 `json:"end"`
	Text  string  `json:"text"`
}

// CutPlan is a validated target editing plan.
type CutPlan struct {
	Source           string  `json:"source"`
	TemplateDuration float64 `json:"template_duration"`
	TargetDuration   float64 `json:"target_duration"`
	Cuts             []Cut   `json:"cuts"`
	Total            int     `json:"total"`
	BeatAlignedCount int     `json:"beat_aligned_count"`
}

// Cut is one target editing interval.
type Cut struct {
	Index         int     `json:"index"`
	Start         float64 `json:"start"`
	End           float64 `json:"end"`
	Duration      float64 `json:"duration"`
	AlignedToBeat bool    `json:"aligned_to_beat"`
	TemplateRatio float64 `json:"template_ratio"`
}
