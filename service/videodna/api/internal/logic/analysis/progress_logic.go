// Code scaffolded by goctl. Safe to edit.
// goctl 1.9.2

package analysis

import (
	"context"
	"net/http"

	"github.com/jsjj2598-bit/video-dna/service/videodna/api/internal/svc"
	"github.com/jsjj2598-bit/video-dna/service/videodna/api/internal/types"
	"github.com/jsjj2598-bit/video-dna/service/videodna/api/internal/xerr"

	"github.com/zeromicro/go-zero/core/logx"
)

type ProgressLogic struct {
	logx.Logger
	ctx    context.Context
	svcCtx *svc.ServiceContext
}

// 查询分析任务进度
func NewProgressLogic(ctx context.Context, svcCtx *svc.ServiceContext) *ProgressLogic {
	return &ProgressLogic{
		Logger: logx.WithContext(ctx),
		ctx:    ctx,
		svcCtx: svcCtx,
	}
}

func (l *ProgressLogic) Progress(req *types.SessionReq) (resp *types.ProgressResp, err error) {
	state, ok := l.svcCtx.Tasks.Get(req.SessionId)
	if !ok {
		return nil, xerr.New(http.StatusNotFound, "分析任务不存在")
	}
	logs := make([]types.ProgressLog, 0, len(state.Logs))
	for _, item := range state.Logs {
		logs = append(logs, types.ProgressLog{Time: item.Time, Stage: item.Stage, Percent: int64(item.Percent), Message: item.Message})
	}
	return &types.ProgressResp{SessionId: state.SessionID, Stage: state.Stage, Percent: int64(state.Percent), Logs: logs, Error: state.Error, Done: state.Done}, nil
}
