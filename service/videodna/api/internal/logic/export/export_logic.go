// Code scaffolded by goctl. Safe to edit.
// goctl 1.9.2

package export

import (
	"context"

	"github.com/jsjj2598-bit/video-dna/service/videodna/api/internal/svc"

	"github.com/zeromicro/go-zero/core/logx"
)

type ExportLogic struct {
	logx.Logger
	ctx    context.Context
	svcCtx *svc.ServiceContext
}

// 导出 EDL、FCP7 XML、Cutmark、SRT 或 ZIP
func NewExportLogic(ctx context.Context, svcCtx *svc.ServiceContext) *ExportLogic {
	return &ExportLogic{
		Logger: logx.WithContext(ctx),
		ctx:    ctx,
		svcCtx: svcCtx,
	}
}
