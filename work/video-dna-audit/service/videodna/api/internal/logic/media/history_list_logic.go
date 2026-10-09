// Code scaffolded by goctl. Safe to edit.
// goctl 1.9.2

package media

import (
	"context"

	"github.com/jsjj2598-bit/video-dna/service/videodna/api/internal/svc"
	"github.com/jsjj2598-bit/video-dna/service/videodna/api/internal/types"

	"github.com/zeromicro/go-zero/core/logx"
)

type HistoryListLogic struct {
	logx.Logger
	ctx    context.Context
	svcCtx *svc.ServiceContext
}

// 获取分析历史列表
func NewHistoryListLogic(ctx context.Context, svcCtx *svc.ServiceContext) *HistoryListLogic {
	return &HistoryListLogic{
		Logger: logx.WithContext(ctx),
		ctx:    ctx,
		svcCtx: svcCtx,
	}
}

func (l *HistoryListLogic) HistoryList() (resp *types.HistoryListResp, err error) {
	items, err := l.svcCtx.Storage.ListHistory()
	if err != nil {
		return nil, err
	}
	resp = &types.HistoryListResp{Items: make([]types.HistoryItem, 0, len(items))}
	for _, item := range items {
		resp.Items = append(resp.Items, types.HistoryItem{SessionId: item.SessionID, Name: item.Name, Time: item.Time, TotalShots: int64(item.TotalShots), Duration: item.Duration, Bpm: item.BPM, Summary: item.Summary, HasVideo: item.HasVideo, ShotCount: int64(item.ShotCount)})
	}
	return resp, nil
}
