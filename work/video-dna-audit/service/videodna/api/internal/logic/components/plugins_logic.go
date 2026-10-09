// Code scaffolded by goctl. Safe to edit.
// goctl 1.9.2

package components

import (
	"context"

	"github.com/jsjj2598-bit/video-dna/service/videodna/api/internal/svc"

	"github.com/zeromicro/go-zero/core/logx"
)

type PluginsLogic struct {
	logx.Logger
	ctx    context.Context
	svcCtx *svc.ServiceContext
}

// 获取插件列表
func NewPluginsLogic(ctx context.Context, svcCtx *svc.ServiceContext) *PluginsLogic {
	return &PluginsLogic{
		Logger: logx.WithContext(ctx),
		ctx:    ctx,
		svcCtx: svcCtx,
	}
}

func (l *PluginsLogic) Plugins() (any, error) {
	return l.svcCtx.Registry.ListPlugins()
}
