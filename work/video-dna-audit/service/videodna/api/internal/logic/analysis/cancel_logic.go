package analysis

import (
	"context"
	"net/http"

	"github.com/jsjj2598-bit/video-dna/service/videodna/api/internal/svc"
	"github.com/jsjj2598-bit/video-dna/service/videodna/api/internal/types"
	"github.com/jsjj2598-bit/video-dna/service/videodna/api/internal/xerr"
	"github.com/zeromicro/go-zero/core/logx"
)

// CancelLogic cancels a queued or running asynchronous analysis.
type CancelLogic struct {
	logx.Logger
	ctx    context.Context
	svcCtx *svc.ServiceContext
}

func NewCancelLogic(ctx context.Context, svcCtx *svc.ServiceContext) *CancelLogic {
	return &CancelLogic{Logger: logx.WithContext(ctx), ctx: ctx, svcCtx: svcCtx}
}

func (l *CancelLogic) Cancel(req *types.SessionReq) (map[string]bool, error) {
	if _, err := l.svcCtx.Storage.ValidateSessionID(req.SessionId); err != nil {
		return nil, xerr.New(http.StatusBadRequest, err.Error())
	}
	if !l.svcCtx.Analyzer.Cancel(req.SessionId) {
		return nil, xerr.New(http.StatusConflict, "任务不存在或已结束")
	}
	return map[string]bool{"ok": true}, nil
}
