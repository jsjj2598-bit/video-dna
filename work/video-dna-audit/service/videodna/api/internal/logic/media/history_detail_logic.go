// Code scaffolded by goctl. Safe to edit.
// goctl 1.9.2

package media

import (
	"context"
	"errors"
	"net/http"
	"os"

	"github.com/jsjj2598-bit/video-dna/service/videodna/api/internal/domain"
	"github.com/jsjj2598-bit/video-dna/service/videodna/api/internal/svc"
	"github.com/jsjj2598-bit/video-dna/service/videodna/api/internal/types"
	"github.com/jsjj2598-bit/video-dna/service/videodna/api/internal/xerr"

	"github.com/zeromicro/go-zero/core/logx"
)

type HistoryDetailLogic struct {
	logx.Logger
	ctx    context.Context
	svcCtx *svc.ServiceContext
}

// 获取单条历史分析详情
func NewHistoryDetailLogic(ctx context.Context, svcCtx *svc.ServiceContext) *HistoryDetailLogic {
	return &HistoryDetailLogic{
		Logger: logx.WithContext(ctx),
		ctx:    ctx,
		svcCtx: svcCtx,
	}
}

func (l *HistoryDetailLogic) HistoryDetail(req *types.SessionReq) (*domain.DNA, error) {
	result, err := l.svcCtx.Storage.ReadResult(req.SessionId)
	if errors.Is(err, os.ErrNotExist) {
		return nil, xerr.New(http.StatusNotFound, "历史记录不存在")
	}
	return result, err
}
