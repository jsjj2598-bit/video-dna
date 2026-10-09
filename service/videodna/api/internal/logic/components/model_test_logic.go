// Code scaffolded by goctl. Safe to edit.
// goctl 1.9.2

package components

import (
	"context"

	"github.com/jsjj2598-bit/video-dna/service/videodna/api/internal/svc"
	"github.com/jsjj2598-bit/video-dna/service/videodna/api/internal/types"

	"github.com/zeromicro/go-zero/core/logx"
)

type ModelTestLogic struct {
	logx.Logger
	ctx    context.Context
	svcCtx *svc.ServiceContext
}

// 测试 AI 模型连通性
func NewModelTestLogic(ctx context.Context, svcCtx *svc.ServiceContext) *ModelTestLogic {
	return &ModelTestLogic{
		Logger: logx.WithContext(ctx),
		ctx:    ctx,
		svcCtx: svcCtx,
	}
}

func (l *ModelTestLogic) ModelTest(req *types.ModelPathReq) (any, error) {
	reply, err := l.svcCtx.Registry.TestModel(l.ctx, req.ModelId)
	if err != nil {
		return nil, err
	}
	return map[string]any{"ok": true, "reply": reply}, nil
}
