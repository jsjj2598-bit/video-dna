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

type SkillDeleteLogic struct {
	logx.Logger
	ctx    context.Context
	svcCtx *svc.ServiceContext
}

// 删除自定义技能
func NewSkillDeleteLogic(ctx context.Context, svcCtx *svc.ServiceContext) *SkillDeleteLogic {
	return &SkillDeleteLogic{
		Logger: logx.WithContext(ctx),
		ctx:    ctx,
		svcCtx: svcCtx,
	}
}

func (l *SkillDeleteLogic) SkillDelete(req *types.SkillPathReq) (resp *types.OkResp, err error) {
	removed, err := l.svcCtx.Registry.DeleteSkill(req.SkillId)
	if err == nil && !removed {
		return nil, xerr.New(http.StatusNotFound, "技能不存在或不可删除")
	}
	return &types.OkResp{Ok: removed}, err
}
