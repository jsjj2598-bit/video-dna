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

type SkillCreateLogic struct {
	logx.Logger
	ctx    context.Context
	svcCtx *svc.ServiceContext
}

// 创建自定义技能
func NewSkillCreateLogic(ctx context.Context, svcCtx *svc.ServiceContext) *SkillCreateLogic {
	return &SkillCreateLogic{
		Logger: logx.WithContext(ctx),
		ctx:    ctx,
		svcCtx: svcCtx,
	}
}

func (l *SkillCreateLogic) SkillCreate(req *types.SkillReq) (*registry.Skill, error) {
	skill, err := l.svcCtx.Registry.AddSkill(registry.Skill{ID: req.Id, Name: req.Name, Desc: req.Desc, Prompt: req.Prompt})
	return &skill, err
}
