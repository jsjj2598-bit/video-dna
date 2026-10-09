package analysis

import (
	"net/http"

	logic "github.com/jsjj2598-bit/video-dna/service/videodna/api/internal/logic/analysis"
	"github.com/jsjj2598-bit/video-dna/service/videodna/api/internal/svc"
	"github.com/jsjj2598-bit/video-dna/service/videodna/api/internal/types"
	"github.com/zeromicro/go-zero/rest/httpx"
)

// CancelHandler cancels one queued or running analysis task.
func CancelHandler(svcCtx *svc.ServiceContext) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		var req types.SessionReq
		if err := httpx.Parse(r, &req); err != nil {
			httpx.ErrorCtx(r.Context(), w, err)
			return
		}
		resp, err := logic.NewCancelLogic(r.Context(), svcCtx).Cancel(&req)
		if err != nil {
			httpx.ErrorCtx(r.Context(), w, err)
			return
		}
		httpx.OkJsonCtx(r.Context(), w, resp)
	}
}
