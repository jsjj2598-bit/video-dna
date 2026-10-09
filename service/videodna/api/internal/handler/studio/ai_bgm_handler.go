// Code scaffolded by goctl. Safe to edit.
// goctl 1.9.2

package studio

import (
	"net/http"

	"github.com/jsjj2598-bit/video-dna/service/videodna/api/internal/logic/studio"
	"github.com/jsjj2598-bit/video-dna/service/videodna/api/internal/svc"
	"github.com/zeromicro/go-zero/rest/httpx"
)

// 根据分析结果推荐 BGM
func AiBgmHandler(svcCtx *svc.ServiceContext) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		var body studio.BGMBody
		if err := httpx.ParseJsonBody(r, &body); err != nil {
			httpx.ErrorCtx(r.Context(), w, err)
			return
		}

		l := studio.NewAiBgmLogic(r.Context(), svcCtx)
		resp, err := l.Recommend(body)
		if err != nil {
			httpx.ErrorCtx(r.Context(), w, err)
		} else {
			httpx.OkJsonCtx(r.Context(), w, resp)
		}
	}
}
