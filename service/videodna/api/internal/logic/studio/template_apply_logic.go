// Code scaffolded by goctl. Safe to edit.
// goctl 1.9.2

package studio

import (
	"context"
	"net/http"

	"github.com/jsjj2598-bit/video-dna/service/videodna/api/internal/svc"

	"github.com/zeromicro/go-zero/core/logx"
)

type TemplateApplyLogic struct {
	logx.Logger
	ctx    context.Context
	svcCtx *svc.ServiceContext
}

// 将示例视频节奏模板应用到新视频
func NewTemplateApplyLogic(ctx context.Context, svcCtx *svc.ServiceContext) *TemplateApplyLogic {
	return &TemplateApplyLogic{
		Logger: logx.WithContext(ctx),
		ctx:    ctx,
		svcCtx: svcCtx,
	}
}

func (l *TemplateApplyLogic) Apply(r *http.Request) (any, error) {
	return applyTemplate(r, l.svcCtx, false)
}
