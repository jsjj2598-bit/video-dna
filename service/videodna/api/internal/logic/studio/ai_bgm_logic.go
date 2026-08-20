// Code scaffolded by goctl. Safe to edit.
// goctl 1.9.2

package studio

import (
	"context"

	"github.com/jsjj2598-bit/video-dna/service/videodna/api/internal/svc"

	"github.com/zeromicro/go-zero/core/logx"
)

type AiBgmLogic struct {
	logx.Logger
	ctx    context.Context
	svcCtx *svc.ServiceContext
}

// 根据分析结果推荐 BGM
func NewAiBgmLogic(ctx context.Context, svcCtx *svc.ServiceContext) *AiBgmLogic {
	return &AiBgmLogic{
		Logger: logx.WithContext(ctx),
		ctx:    ctx,
		svcCtx: svcCtx,
	}
}

func (l *AiBgmLogic) Recommend(body BGMBody) (any, error) {
	return recommendBGM(body, l.svcCtx)
}
