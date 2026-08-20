// Code scaffolded by goctl. Safe to edit.
// goctl 1.9.2

package analysis

import (
	"context"
	"net/http"

	"github.com/jsjj2598-bit/video-dna/service/videodna/api/internal/svc"

	"github.com/zeromicro/go-zero/core/logx"
)

type AnalyzeWaitLogic struct {
	logx.Logger
	ctx    context.Context
	svcCtx *svc.ServiceContext
}

// 同步上传并等待视频分析完成
func NewAnalyzeWaitLogic(ctx context.Context, svcCtx *svc.ServiceContext) *AnalyzeWaitLogic {
	return &AnalyzeWaitLogic{
		Logger: logx.WithContext(ctx),
		ctx:    ctx,
		svcCtx: svcCtx,
	}
}

func (l *AnalyzeWaitLogic) Submit(r *http.Request) (any, error) {
	return submitUpload(r, l.svcCtx, true)
}
