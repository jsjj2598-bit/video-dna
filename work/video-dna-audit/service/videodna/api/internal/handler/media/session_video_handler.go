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

// 读取支持 Range 的源视频
func SessionVideoHandler(svcCtx *svc.ServiceContext) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		var req types.SessionReq
		if err := httpx.Parse(r, &req); err != nil {
			httpx.ErrorCtx(r.Context(), w, err)
			return
		}

		l := media.NewSessionVideoLogic(r.Context(), svcCtx)
		path, err := l.SessionVideo(&req)
		if err != nil {
			httpx.ErrorCtx(r.Context(), w, err)
		} else {
			http.ServeFile(w, r, path)
		}
	}
}
