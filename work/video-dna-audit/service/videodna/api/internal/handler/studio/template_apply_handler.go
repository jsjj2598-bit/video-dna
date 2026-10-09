// Code scaffolded by goctl. Safe to edit.
// goctl 1.9.2

package studio

import (
	"net/http"

	"github.com/jsjj2598-bit/video-dna/service/videodna/api/internal/logic/studio"
	"github.com/jsjj2598-bit/video-dna/service/videodna/api/internal/svc"
	"github.com/zeromicro/go-zero/rest/httpx"
)

// 将示例视频节奏模板应用到新视频
func TemplateApplyHandler(svcCtx *svc.ServiceContext) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		l := studio.NewTemplateApplyLogic(r.Context(), svcCtx)
		resp, err := l.Apply(r)
		if err != nil {
			httpx.ErrorCtx(r.Context(), w, err)
		} else {
			httpx.OkJsonCtx(r.Context(), w, resp)
		}
	}
}
