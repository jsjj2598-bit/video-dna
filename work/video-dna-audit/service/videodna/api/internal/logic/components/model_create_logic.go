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

type ModelCreateLogic struct {
	logx.Logger
	ctx    context.Context
	svcCtx *svc.ServiceContext
}

// 创建自定义 AI 模型
func NewModelCreateLogic(ctx context.Context, svcCtx *svc.ServiceContext) *ModelCreateLogic {
	return &ModelCreateLogic{
		Logger: logx.WithContext(ctx),
		ctx:    ctx,
		svcCtx: svcCtx,
	}
}

func (l *ModelCreateLogic) ModelCreate(req *types.ModelReq) (*registry.Model, error) {
	model, err := l.svcCtx.Registry.UpsertModel(registry.Model{ID: req.ModelId, Name: req.Name, Kind: req.Kind, Provider: req.Provider, BaseURL: req.BaseUrl, Model: req.Model, APIKey: req.ApiKey})
	return &model, err
}
