package studio

import (
	"encoding/json"
	"net/http"
	"strings"

	"github.com/jsjj2598-bit/video-dna/service/videodna/api/internal/domain"
	"github.com/jsjj2598-bit/video-dna/service/videodna/api/internal/service/analyzer"
	"github.com/jsjj2598-bit/video-dna/service/videodna/api/internal/service/templates"
	"github.com/jsjj2598-bit/video-dna/service/videodna/api/internal/svc"
	"github.com/jsjj2598-bit/video-dna/service/videodna/api/internal/xerr"
)

func applyTemplate(r *http.Request, svcCtx *svc.ServiceContext, builtin bool) (any, error) {
	if err := r.ParseMultipartForm(32 << 20); err != nil {
		return nil, xerr.Wrap(http.StatusBadRequest, "上传表单无效", err)
	}
	if r.MultipartForm != nil {
		defer r.MultipartForm.RemoveAll()
	}
	file, header, err := r.FormFile("file")
	if err != nil {
		return nil, xerr.New(http.StatusBadRequest, "缺少视频文件")
	}
	defer file.Close()
	detector := defaultValue(r.FormValue("detector"), "content")
	backend := defaultValue(r.FormValue("backend"), "auto")
	if detector != "content" && detector != "adaptive" {
		return nil, xerr.New(http.StatusBadRequest, "detector 仅支持 content 或 adaptive")
	}
	if backend != "auto" && backend != "heuristic" && backend != "openai" && backend != "qwen" {
		return nil, xerr.New(http.StatusBadRequest, "backend 仅支持 auto/heuristic/openai/qwen")
	}
	var templateDNA *domain.DNA
	var selected any
	if builtin {
		template, ok := templates.Find(strings.TrimSpace(r.FormValue("template")))
		if !ok {
			return nil, xerr.New(http.StatusBadRequest, "模板不存在")
		}
		selected = template
		// The target duration is only known after analysis; expand below.
		templateDNA = templates.TemplateDNA(template, 1)
	} else {
		var parsed domain.DNA
		if err := json.Unmarshal([]byte(r.FormValue("template")), &parsed); err != nil || len(parsed.Shots) == 0 {
			return nil, xerr.New(http.StatusBadRequest, "模板 JSON 无效")
		}
		templateDNA = &parsed
	}
	sessionID := svcCtx.Storage.NewSessionID()
	sourcePath, err := svcCtx.Storage.SaveUpload(sessionID, header.Filename, file)
	if err != nil {
		return nil, xerr.New(http.StatusBadRequest, err.Error())
	}
	svcCtx.Tasks.Create(sessionID, "文件已上传："+header.Filename)
	result, err := svcCtx.Analyzer.Run(r.Context(), analyzer.Job{
		SessionID: sessionID, SourcePath: sourcePath, SourceName: header.Filename,
		Options: analyzer.Options{Detector: detector, Backend: backend, OpenAIKey: r.FormValue("openai_key"), QwenKey: r.FormValue("qwen_key")},
	})
	if err != nil {
		return nil, xerr.Wrap(http.StatusUnprocessableEntity, "分析失败", err)
	}
	if builtin {
		template := selected.(templates.RhythmTemplate)
		templateDNA = templates.TemplateDNA(template, result.Meta.Duration)
	}
	plan, err := templates.BuildCutPlan(templateDNA, result, svcCtx.Config.Analysis.MinShotSeconds)
	if err != nil {
		return nil, xerr.New(http.StatusUnprocessableEntity, err.Error())
	}
	result.CutPlan = plan
	if err := svcCtx.Storage.SaveResult(sessionID, result, header.Filename); err != nil {
		return nil, err
	}
	response := map[string]any{"analysis": result, "cut_plan": plan}
	if builtin {
		response["template"] = selected
	}
	return response, nil
}

// BGMBody accepts either inline DNA or a session reference.
type BGMBody struct {
	SessionID string      `json:"session_id"`
	DNA       *domain.DNA `json:"dna"`
}

func recommendBGM(body BGMBody, svcCtx *svc.ServiceContext) (any, error) {
	dna := body.DNA
	if dna == nil && body.SessionID != "" {
		result, err := svcCtx.Storage.ReadResult(body.SessionID)
		if err != nil {
			return nil, xerr.New(http.StatusBadRequest, err.Error())
		}
		dna = result
	}
	if dna == nil {
		return nil, xerr.New(http.StatusBadRequest, "请提供 dna 或 session_id")
	}
	bpm := dna.Audio.TempoBPM
	if bpm <= 0 {
		return nil, xerr.New(http.StatusBadRequest, "未检测到 BPM，无法推荐")
	}
	mood := "低沉/悬疑"
	genres := []string{"暗黑氛围", "Drone", "悬疑配乐", "低频垫乐"}
	if bpm >= 120 {
		mood, genres = "高燃/活力", []string{"EDM", "Trap", "电子舞曲", "Bounce"}
	} else if bpm >= 90 {
		mood, genres = "轻快/向上", []string{"流行", "Future Bass", "Pop 电子", "轻摇滚"}
	} else if bpm >= 60 {
		mood, genres = "舒缓/叙事", []string{"钢琴抒情", "Lo-fi", "氛围电子", "民谣"}
	}
	return map[string]any{
		"bpm": bpm, "mood": mood, "recommend": genres,
		"hint": "建议切点对齐 BPM 节拍", "search_hint": "在剪映/BGM 平台搜索关键词：" + strings.Join(genres, "、"),
	}, nil
}

func defaultValue(value, fallback string) string {
	if strings.TrimSpace(value) == "" {
		return fallback
	}
	return strings.TrimSpace(value)
}
