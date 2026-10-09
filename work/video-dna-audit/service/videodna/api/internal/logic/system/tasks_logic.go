package system

import (
	"context"

	"github.com/jsjj2598-bit/video-dna/service/videodna/api/internal/svc"
	"github.com/jsjj2598-bit/video-dna/service/videodna/api/internal/types"
)

type TasksLogic struct {
	ctx    context.Context
	svcCtx *svc.ServiceContext
}

func NewTasksLogic(ctx context.Context, svcCtx *svc.ServiceContext) *TasksLogic {
	return &TasksLogic{ctx: ctx, svcCtx: svcCtx}
}

func (l *TasksLogic) Tasks() *types.TaskListResp {
	states := l.svcCtx.Tasks.List()
	items := make([]types.TaskItem, 0, len(states))
	for _, state := range states {
		logs := make([]types.ProgressLog, 0, len(state.Logs))
		for _, item := range state.Logs {
			logs = append(logs, types.ProgressLog{Time: item.Time, Stage: item.Stage, Percent: int64(item.Percent), Message: item.Message})
		}
		items = append(items, types.TaskItem{SessionId: state.SessionID, Stage: state.Stage, Percent: int64(state.Percent), Error: state.Error, Done: state.Done, Logs: logs})
	}
	return &types.TaskListResp{Items: items}
}
