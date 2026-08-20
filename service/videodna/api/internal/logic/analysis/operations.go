package analysis

import (
	"errors"
	"net/http"
	"os"
	"strings"

	"github.com/jsjj2598-bit/video-dna/service/videodna/api/internal/domain"
	"github.com/jsjj2598-bit/video-dna/service/videodna/api/internal/service/analyzer"
	"github.com/jsjj2598-bit/video-dna/service/videodna/api/internal/svc"
	"github.com/jsjj2598-bit/video-dna/service/videodna/api/internal/xerr"
)

func submitUpload(r *http.Request, svcCtx *svc.ServiceContext, wait bool) (any, error) {
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
	detector := firstValue(r.FormValue("detector"), r.URL.Query().Get("detector"), "content")
	backend := firstValue(r.FormValue("backend"), r.URL.Query().Get("backend"), "auto")
	if detector != "content" && detector != "adaptive" {
		return nil, xerr.New(http.StatusBadRequest, "detector 仅支持 content 或 adaptive")
	}
	if backend != "auto" && backend != "heuristic" && backend != "openai" && backend != "qwen" {
		return nil, xerr.New(http.StatusBadRequest, "backend 仅支持 auto/heuristic/openai/qwen")
	}
	sessionID := strings.TrimSpace(r.FormValue("session_id"))
	if sessionID == "" {
		sessionID = svcCtx.Storage.NewSessionID()
	} else if _, err := svcCtx.Storage.ValidateSessionID(sessionID); err != nil {
		return nil, xerr.New(http.StatusBadRequest, err.Error())
	}
	sourcePath, err := svcCtx.Storage.SaveUpload(sessionID, header.Filename, file)
	if err != nil {
		return nil, xerr.New(http.StatusBadRequest, err.Error())
	}
	svcCtx.Tasks.Create(sessionID, "文件已上传："+header.Filename)
	job := analyzer.Job{
		SessionID: sessionID, SourcePath: sourcePath, SourceName: header.Filename,
		Options: analyzer.Options{Detector: detector, Backend: backend, OpenAIKey: r.FormValue("openai_key"), QwenKey: r.FormValue("qwen_key")},
	}
	if !wait {
		svcCtx.Analyzer.Start(job)
		return map[string]any{"session_id": sessionID, "status": "running"}, nil
	}
	result, err := svcCtx.Analyzer.Run(r.Context(), job)
	if err != nil {
		if errors.Is(err, r.Context().Err()) {
			return nil, xerr.New(http.StatusRequestTimeout, "分析请求已取消")
		}
		return nil, xerr.Wrap(http.StatusUnprocessableEntity, "分析失败", err)
	}
	return result, nil
}

func firstValue(values ...string) string {
	for _, value := range values {
		if strings.TrimSpace(value) != "" {
			return strings.TrimSpace(value)
		}
	}
	return ""
}

func readResult(svcCtx *svc.ServiceContext, sessionID string) (*domain.DNA, error) {
	result, err := svcCtx.Storage.ReadResult(sessionID)
	if errors.Is(err, os.ErrNotExist) {
		return nil, xerr.New(http.StatusNotFound, "分析结果不存在")
	}
	if err != nil {
		return nil, xerr.New(http.StatusBadRequest, err.Error())
	}
	return result, nil
}
