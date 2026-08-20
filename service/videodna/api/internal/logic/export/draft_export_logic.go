// Code scaffolded by goctl. Safe to edit.
// goctl 1.9.2

package export

import (
	"context"
	"net/http"
	"path/filepath"

	"github.com/jsjj2598-bit/video-dna/service/videodna/api/internal/domain"
	"github.com/jsjj2598-bit/video-dna/service/videodna/api/internal/service/draft"
	"github.com/jsjj2598-bit/video-dna/service/videodna/api/internal/svc"
	"github.com/jsjj2598-bit/video-dna/service/videodna/api/internal/types"
	"github.com/jsjj2598-bit/video-dna/service/videodna/api/internal/xerr"

	"github.com/zeromicro/go-zero/core/logx"
)

type DraftExportLogic struct {
	logx.Logger
	ctx    context.Context
	svcCtx *svc.ServiceContext
}

// 导出剪映草稿目录
func NewDraftExportLogic(ctx context.Context, svcCtx *svc.ServiceContext) *DraftExportLogic {
	return &DraftExportLogic{
		Logger: logx.WithContext(ctx),
		ctx:    ctx,
		svcCtx: svcCtx,
	}
}

func (l *DraftExportLogic) DraftExport(req *types.DraftExportReq) (any, error) {
	if req.SessionId == "" {
		return nil, xerr.New(http.StatusBadRequest, "缺少 session_id")
	}
	result, err := l.svcCtx.Storage.ReadResult(req.SessionId)
	if err != nil {
		return nil, xerr.New(http.StatusBadRequest, err.Error())
	}
	sourcePath, err := l.svcCtx.Storage.SourceVideo(req.SessionId)
	if err != nil || sourcePath == "" {
		return nil, xerr.New(http.StatusNotFound, "源视频不存在")
	}
	cuts := make([]domain.Cut, 0, len(req.Cuts))
	for index, item := range req.Cuts {
		cuts = append(cuts, domain.Cut{Index: index, Start: item.Start, End: item.End, Duration: item.End - item.Start, AlignedToBeat: item.AlignedToBeat})
	}
	outputDir := req.DownloadDir
	if outputDir == "" {
		outputDir = filepath.Join(l.svcCtx.Storage.DownloadsDir, "drafts")
	} else {
		outputDir = expandHome(outputDir)
	}
	path, err := draft.ExportFolder(l.ctx, l.svcCtx.Tools, req.ProjectName, sourcePath, outputDir, result, cuts)
	if err != nil {
		return nil, xerr.New(http.StatusBadRequest, err.Error())
	}
	return map[string]any{"path": path, "download_dir": outputDir}, nil
}
