// Code scaffolded by goctl. Safe to edit.
// goctl 1.9.2

package media

import (
	"context"
	"net/http"

	"github.com/jsjj2598-bit/video-dna/service/videodna/api/internal/svc"
	"github.com/jsjj2598-bit/video-dna/service/videodna/api/internal/types"
	"github.com/jsjj2598-bit/video-dna/service/videodna/api/internal/xerr"

	"github.com/zeromicro/go-zero/core/logx"
)

type SessionVideoLogic struct {
	logx.Logger
	ctx    context.Context
	svcCtx *svc.ServiceContext
}

// 读取支持 Range 的源视频
func NewSessionVideoLogic(ctx context.Context, svcCtx *svc.ServiceContext) *SessionVideoLogic {
	return &SessionVideoLogic{
		Logger: logx.WithContext(ctx),
		ctx:    ctx,
		svcCtx: svcCtx,
	}
}

func (l *SessionVideoLogic) SessionVideo(req *types.SessionReq) (string, error) {
	path, err := l.svcCtx.Storage.SourceVideo(req.SessionId)
	if err != nil {
		return "", xerr.New(http.StatusBadRequest, err.Error())
	}
	if path == "" {
		return "", xerr.New(http.StatusNotFound, "源视频不存在")
	}
	return path, nil
}
