// Code scaffolded by goctl. Safe to edit.
// goctl 1.9.2

package components

import (
	"context"

	"github.com/jsjj2598-bit/video-dna/service/videodna/api/internal/service/registry"
	"github.com/jsjj2598-bit/video-dna/service/videodna/api/internal/svc"
	"github.com/jsjj2598-bit/video-dna/service/videodna/api/internal/types"

	"github.com/zeromicro/go-zero/core/logx"
)

type ComponentToggleLogic struct {
	logx.Logger
	ctx    context.Context
	svcCtx *svc.ServiceContext
}

// 启用或关闭分析组件
func NewComponentToggleLogic(ctx context.Context, svcCtx *svc.ServiceContext) *ComponentToggleLogic {
	return &ComponentToggleLogic{
		Logger: logx.WithContext(ctx),
		ctx:    ctx,
		svcCtx: svcCtx,
	}
}

func (l *ComponentToggleLogic) ComponentToggle(req *types.ComponentToggleReq) (*registry.Component, error) {
	component, err := l.svcCtx.Registry.SetComponent(req.ComponentId, req.Enabled, req.ModelId)
	return &component, err
}
