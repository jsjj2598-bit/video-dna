// Code scaffolded by goctl. Safe to edit.
// goctl 1.9.2

package analysis

import (
	"context"

	"github.com/jsjj2598-bit/video-dna/service/videodna/api/internal/domain"
	"github.com/jsjj2598-bit/video-dna/service/videodna/api/internal/svc"
	"github.com/jsjj2598-bit/video-dna/service/videodna/api/internal/types"

	"github.com/zeromicro/go-zero/core/logx"
)

type ResultLogic struct {
	logx.Logger
	ctx    context.Context
	svcCtx *svc.ServiceContext
}

// 读取完整 Video DNA 分析结果
func NewResultLogic(ctx context.Context, svcCtx *svc.ServiceContext) *ResultLogic {
	return &ResultLogic{
		Logger: logx.WithContext(ctx),
		ctx:    ctx,
		svcCtx: svcCtx,
	}
}

func (l *ResultLogic) Result(req *types.SessionReq) (*domain.DNA, error) {
	return readResult(l.svcCtx, req.SessionId)
}
