// Code scaffolded by goctl. Safe to edit.
// goctl 1.9.2

package components

import (
	"context"
	"net/http"

	"github.com/jsjj2598-bit/video-dna/service/videodna/api/internal/svc"
	"github.com/jsjj2598-bit/video-dna/service/videodna/api/internal/types"
	"github.com/jsjj2598-bit/video-dna/service/videodna/api/internal/xerr"

	"github.com/zeromicro/go-zero/core/logx"
)

type ModelDeleteLogic struct {
	logx.Logger
	ctx    context.Context
	svcCtx *svc.ServiceContext
}

// 删除自定义 AI 模型
func NewModelDeleteLogic(ctx context.Context, svcCtx *svc.ServiceContext) *ModelDeleteLogic {
	return &ModelDeleteLogic{
		Logger: logx.WithContext(ctx),
		ctx:    ctx,
		svcCtx: svcCtx,
	}
}

func (l *ModelDeleteLogic) ModelDelete(req *types.ModelPathReq) (resp *types.OkResp, err error) {
	removed, err := l.svcCtx.Registry.DeleteModel(req.ModelId)
	if err == nil && !removed {
		return nil, xerr.New(http.StatusNotFound, "模型不存在或不可删除")
	}
	return &types.OkResp{Ok: removed}, err
}
