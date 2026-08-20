// Code scaffolded by goctl. Safe to edit.
// goctl 1.9.2

package media

import (
	"context"
	"net/http"

	"github.com/jsjj2598-bit/video-dna/service/videodna/api/internal/svc"
	"github.com/jsjj2598-bit/video-dna/service/videodna/api/internal/types"
	"github.com/jsjj2598-bit/video-dna/service/videodna/api/internal/xerr"

	"github.com/zeromicro/go-zero/core/logx"
)

type HistoryDeleteLogic struct {
	logx.Logger
	ctx    context.Context
	svcCtx *svc.ServiceContext
}

// 删除指定分析历史
func NewHistoryDeleteLogic(ctx context.Context, svcCtx *svc.ServiceContext) *HistoryDeleteLogic {
	return &HistoryDeleteLogic{
		Logger: logx.WithContext(ctx),
		ctx:    ctx,
		svcCtx: svcCtx,
	}
}

func (l *HistoryDeleteLogic) HistoryDelete(req *types.SessionReq) (resp *types.OkResp, err error) {
	if l.svcCtx.Tasks.IsActive(req.SessionId) {
		return nil, xerr.New(http.StatusConflict, "分析任务运行中，暂时不能删除")
	}
	removed, err := l.svcCtx.Storage.DeleteSession(req.SessionId)
	if err == nil && removed {
		l.svcCtx.Tasks.Remove(req.SessionId)
	}
	return &types.OkResp{Ok: removed}, err
}
