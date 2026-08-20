// Code scaffolded by goctl. Safe to edit.
// goctl 1.9.2

package media

import (
	"context"
	"errors"
	"net/http"
	"os"

	"github.com/jsjj2598-bit/video-dna/service/videodna/api/internal/svc"
	"github.com/jsjj2598-bit/video-dna/service/videodna/api/internal/types"
	"github.com/jsjj2598-bit/video-dna/service/videodna/api/internal/xerr"

	"github.com/zeromicro/go-zero/core/logx"
)

type SessionFrameLogic struct {
	logx.Logger
	ctx    context.Context
	svcCtx *svc.ServiceContext
}

// 读取镜头关键帧
func NewSessionFrameLogic(ctx context.Context, svcCtx *svc.ServiceContext) *SessionFrameLogic {
	return &SessionFrameLogic{
		Logger: logx.WithContext(ctx),
		ctx:    ctx,
		svcCtx: svcCtx,
	}
}

func (l *SessionFrameLogic) SessionFrame(req *types.SessionFrameReq) (string, error) {
	path, err := l.svcCtx.Storage.FramePath(req.SessionId, req.Filename)
	if err != nil {
		return "", xerr.New(http.StatusBadRequest, err.Error())
	}
	if _, err := os.Stat(path); errors.Is(err, os.ErrNotExist) {
		return "", xerr.New(http.StatusNotFound, "关键帧不存在")
	} else if err != nil {
		return "", err
	}
	return path, nil
}
