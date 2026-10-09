// Code scaffolded by goctl. Safe to edit.
// goctl 1.9.2

package export

import (
	"net/http"

	"github.com/jsjj2598-bit/video-dna/service/videodna/api/internal/logic/export"
	"github.com/jsjj2598-bit/video-dna/service/videodna/api/internal/svc"
	"github.com/jsjj2598-bit/video-dna/service/videodna/api/internal/types"
	"github.com/zeromicro/go-zero/rest/httpx"
)

// 导出剪映草稿目录
func DraftExportHandler(svcCtx *svc.ServiceContext) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		var req types.DraftExportReq
		if err := httpx.Parse(r, &req); err != nil {
			httpx.ErrorCtx(r.Context(), w, err)
			return
		}

		l := export.NewDraftExportLogic(r.Context(), svcCtx)
		resp, err := l.DraftExport(&req)
		if err != nil {
			httpx.ErrorCtx(r.Context(), w, err)
		} else {
			httpx.OkJsonCtx(r.Context(), w, resp)
		}
	}
}
