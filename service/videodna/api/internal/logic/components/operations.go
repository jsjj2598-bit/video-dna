package components

import (
	"errors"
	"io"
	"net/http"
	"os"
	"path/filepath"

	"github.com/jsjj2598-bit/video-dna/service/videodna/api/internal/domain"
	"github.com/jsjj2598-bit/video-dna/service/videodna/api/internal/xerr"
)

// SkillRunBody accepts either an inline DNA or a persisted session.
type SkillRunBody struct {
	SessionID string      `json:"session_id"`
	DNA       *domain.DNA `json:"dna"`
}

func (l *SkillRunLogic) Run(skillID string, body SkillRunBody) (any, error) {
	dna := body.DNA
	if dna == nil && body.SessionID != "" {
		result, err := l.svcCtx.Storage.ReadResult(body.SessionID)
		if err != nil {
			return nil, xerr.New(http.StatusBadRequest, err.Error())
		}
		dna = result
	}
	if dna == nil {
		return nil, xerr.New(http.StatusBadRequest, "请提供 dna 或 session_id")
	}
	output, name, err := l.svcCtx.Registry.RunSkill(l.ctx, skillID, dna)
	if err != nil {
		return nil, xerr.Wrap(http.StatusBadGateway, "技能执行失败", err)
	}
	return map[string]any{"ok": true, "output": output, "skill": name}, nil
}

func (l *PluginInstallLogic) Install(r *http.Request) (any, error) {
	if err := r.ParseMultipartForm(8 << 20); err != nil {
		return nil, xerr.Wrap(http.StatusBadRequest, "插件上传表单无效", err)
	}
	if r.MultipartForm != nil {
		defer r.MultipartForm.RemoveAll()
	}
	file, _, err := r.FormFile("file")
	if err != nil {
		return nil, xerr.New(http.StatusBadRequest, "缺少插件 ZIP")
	}
	defer file.Close()
	temporary, err := os.CreateTemp("", "videodna-plugin-*.zip")
	if err != nil {
		return nil, err
	}
	path := temporary.Name()
	defer os.Remove(path)
	written, copyErr := temporary.ReadFrom(io.LimitReader(file, l.svcCtx.Config.Limits.PluginBytes+1))
	closeErr := temporary.Close()
	if copyErr != nil || closeErr != nil {
		return nil, xerr.Wrap(http.StatusBadRequest, "读取插件失败", errors.Join(copyErr, closeErr))
	}
	if written > l.svcCtx.Config.Limits.PluginBytes {
		return nil, xerr.New(http.StatusRequestEntityTooLarge, "插件包超过大小上限")
	}
	plugin, err := l.svcCtx.Registry.InstallPlugin(filepath.Clean(path))
	if err != nil {
		return nil, xerr.New(http.StatusBadRequest, err.Error())
	}
	return map[string]any{"ok": true, "plugin": plugin}, nil
}
