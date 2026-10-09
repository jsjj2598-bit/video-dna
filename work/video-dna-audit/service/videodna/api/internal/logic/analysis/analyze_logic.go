// Code scaffolded by goctl. Safe to edit.
// goctl 1.9.2

package analysis

import (
	"context"
	"net/http"

	"github.com/jsjj2598-bit/video-dna/service/videodna/api/internal/svc"

	"github.com/zeromicro/go-zero/core/logx"
)

type AnalyzeLogic struct {
	logx.Logger
	ctx    context.Context
	svcCtx *svc.ServiceContext
}

// 异步上传并分析视频
func NewAnalyzeLogic(ctx context.Context, svcCtx *svc.ServiceContext) *AnalyzeLogic {
	return &AnalyzeLogic{
		Logger: logx.WithContext(ctx),
		ctx:    ctx,
		svcCtx: svcCtx,
	}
}

func (l *AnalyzeLogic) Submit(r *http.Request) (any, error) {
	return submitUpload(r, l.svcCtx, false)
}
