// Code scaffolded by goctl. Safe to edit.
// goctl 1.9.2

package media

import (
	"context"

	"github.com/jsjj2598-bit/video-dna/service/videodna/api/internal/svc"
	"github.com/jsjj2598-bit/video-dna/service/videodna/api/internal/types"

	"github.com/zeromicro/go-zero/core/logx"
)

type HistoryClearLogic struct {
	logx.Logger
	ctx    context.Context
	svcCtx *svc.ServiceContext
}

// 清空已完成的分析历史
func NewHistoryClearLogic(ctx context.Context, svcCtx *svc.ServiceContext) *HistoryClearLogic {
	return &HistoryClearLogic{
		Logger: logx.WithContext(ctx),
		ctx:    ctx,
		svcCtx: svcCtx,
	}
}

func (l *HistoryClearLogic) HistoryClear() (resp *types.OkResp, err error) {
	if err := l.svcCtx.Storage.ClearHistory(l.svcCtx.Tasks.ActiveIDs()); err != nil {
		return nil, err
	}
	l.svcCtx.Tasks.ClearCompleted()
	return &types.OkResp{Ok: true}, nil
}
