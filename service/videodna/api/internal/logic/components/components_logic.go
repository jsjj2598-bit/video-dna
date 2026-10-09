// Code scaffolded by goctl. Safe to edit.
// goctl 1.9.2

package components

import (
	"context"

	"github.com/jsjj2598-bit/video-dna/service/videodna/api/internal/svc"

	"github.com/zeromicro/go-zero/core/logx"
)

type ComponentsLogic struct {
	logx.Logger
	ctx    context.Context
	svcCtx *svc.ServiceContext
}

// 获取模型、组件、技能和插件
func NewComponentsLogic(ctx context.Context, svcCtx *svc.ServiceContext) *ComponentsLogic {
	return &ComponentsLogic{
		Logger: logx.WithContext(ctx),
		ctx:    ctx,
		svcCtx: svcCtx,
	}
}

func (l *ComponentsLogic) Components() (any, error) {
	components, err := l.svcCtx.Registry.ListComponents()
	if err != nil {
		return nil, err
	}
	models, err := l.svcCtx.Registry.ListModels()
	if err != nil {
		return nil, err
	}
	plugins, err := l.svcCtx.Registry.ListPlugins()
	if err != nil {
		return nil, err
	}
	skills, err := l.svcCtx.Registry.ListSkills()
	if err != nil {
		return nil, err
	}
	return map[string]any{"components": components, "models": models, "plugins": plugins, "skills": skills}, nil
}
