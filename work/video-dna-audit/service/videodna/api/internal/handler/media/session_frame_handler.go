// Code scaffolded by goctl. Safe to edit.
// goctl 1.9.2

package media

import (
	"net/http"

	"github.com/jsjj2598-bit/video-dna/service/videodna/api/internal/logic/media"
	"github.com/jsjj2598-bit/video-dna/service/videodna/api/internal/svc"
	"github.com/jsjj2598-bit/video-dna/service/videodna/api/internal/types"
	"github.com/zeromicro/go-zero/rest/httpx"
)

// 读取镜头关键帧
func SessionFrameHandler(svcCtx *svc.ServiceContext) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		var req types.SessionFrameReq
		if err := httpx.Parse(r, &req); err != nil {
			httpx.ErrorCtx(r.Context(), w, err)
			return
		}

		l := media.NewSessionFrameLogic(r.Context(), svcCtx)
		path, err := l.SessionFrame(&req)
		if err != nil {
			httpx.ErrorCtx(r.Context(), w, err)
		} else {
			http.ServeFile(w, r, path)
		}
	}
}
