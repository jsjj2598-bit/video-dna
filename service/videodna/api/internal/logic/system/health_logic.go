// Code scaffolded by goctl. Safe to edit.
// goctl 1.9.2

package system

import (
	"context"

	"github.com/jsjj2598-bit/video-dna/service/videodna/api/internal/svc"

	"github.com/zeromicro/go-zero/core/logx"
)

type HealthLogic struct {
	logx.Logger
	ctx    context.Context
	svcCtx *svc.ServiceContext
}

// 服务健康检查
func NewHealthLogic(ctx context.Context, svcCtx *svc.ServiceContext) *HealthLogic {
	return &HealthLogic{
		Logger: logx.WithContext(ctx),
		ctx:    ctx,
		svcCtx: svcCtx,
	}
}

func (l *HealthLogic) Health() (any, error) {
	return map[string]any{
		"status": "ok", "service": "video-dna-analyzer", "version": "0.4.0",
		"runtime": "go", "ffmpeg": l.svcCtx.Tools.FFmpeg != "", "ffprobe": l.svcCtx.Tools.FFprobe != "",
	}, nil
}
