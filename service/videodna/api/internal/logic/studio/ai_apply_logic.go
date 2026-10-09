// Code scaffolded by goctl. Safe to edit.
// goctl 1.9.2

package studio

import (
	"context"
	"net/http"

	"github.com/jsjj2598-bit/video-dna/service/videodna/api/internal/svc"

	"github.com/zeromicro/go-zero/core/logx"
)

type AiApplyLogic struct {
	logx.Logger
	ctx    context.Context
	svcCtx *svc.ServiceContext
}

// 将内置节奏模板应用到新视频
func NewAiApplyLogic(ctx context.Context, svcCtx *svc.ServiceContext) *AiApplyLogic {
	return &AiApplyLogic{
		Logger: logx.WithContext(ctx),
		ctx:    ctx,
		svcCtx: svcCtx,
	}
}

func (l *AiApplyLogic) Apply(r *http.Request) (any, error) {
	return applyTemplate(r, l.svcCtx, true)
}
