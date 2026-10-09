package system

import (
	"net/http"

	"github.com/jsjj2598-bit/video-dna/service/videodna/api/internal/logic/system"
	"github.com/jsjj2598-bit/video-dna/service/videodna/api/internal/svc"
	"github.com/zeromicro/go-zero/rest/httpx"
)

func TasksHandler(svcCtx *svc.ServiceContext) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		resp := system.NewTasksLogic(r.Context(), svcCtx).Tasks()
		httpx.OkJsonCtx(r.Context(), w, resp)
	}
}
