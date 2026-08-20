// Code scaffolded by goctl. Safe to edit.
// goctl 1.9.2

package studio

import (
	"context"

	"github.com/jsjj2598-bit/video-dna/service/videodna/api/internal/service/templates"
	"github.com/jsjj2598-bit/video-dna/service/videodna/api/internal/svc"
	"github.com/jsjj2598-bit/video-dna/service/videodna/api/internal/types"

	"github.com/zeromicro/go-zero/core/logx"
)

type AiTemplatesLogic struct {
	logx.Logger
	ctx    context.Context
	svcCtx *svc.ServiceContext
}

// 获取内置节奏模板
func NewAiTemplatesLogic(ctx context.Context, svcCtx *svc.ServiceContext) *AiTemplatesLogic {
	return &AiTemplatesLogic{
		Logger: logx.WithContext(ctx),
		ctx:    ctx,
		svcCtx: svcCtx,
	}
}

func (l *AiTemplatesLogic) AiTemplates() (resp *types.TemplateListResp, err error) {
	resp = &types.TemplateListResp{Templates: make([]types.RhythmTemplate, 0, len(templates.Builtins))}
	for _, item := range templates.Builtins {
		resp.Templates = append(resp.Templates, types.RhythmTemplate{Id: item.ID, Name: item.Name, Desc: item.Desc, Icon: item.Icon, Bpm: item.BPM, Shot: item.Shot, Pattern: item.Pattern})
	}
	return resp, nil
}
