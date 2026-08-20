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

type PluginDeleteLogic struct {
	logx.Logger
	ctx    context.Context
	svcCtx *svc.ServiceContext
}

// 删除用户安装的插件
func NewPluginDeleteLogic(ctx context.Context, svcCtx *svc.ServiceContext) *PluginDeleteLogic {
	return &PluginDeleteLogic{
		Logger: logx.WithContext(ctx),
		ctx:    ctx,
		svcCtx: svcCtx,
	}
}

func (l *PluginDeleteLogic) PluginDelete(req *types.PluginPathReq) (resp *types.OkResp, err error) {
	removed, err := l.svcCtx.Registry.DeletePlugin(req.PluginId)
	if err == nil && !removed {
		return nil, xerr.New(http.StatusNotFound, "插件不存在")
	}
	return &types.OkResp{Ok: removed}, err
}
