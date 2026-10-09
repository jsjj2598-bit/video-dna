// Code scaffolded by goctl. Safe to edit.
// goctl 1.9.2

package components

import (
	"net/http"

	"github.com/jsjj2598-bit/video-dna/service/videodna/api/internal/logic/components"
	"github.com/jsjj2598-bit/video-dna/service/videodna/api/internal/svc"
	"github.com/jsjj2598-bit/video-dna/service/videodna/api/internal/types"
	"github.com/zeromicro/go-zero/rest/httpx"
)

// 对指定分析结果运行技能
func SkillRunHandler(svcCtx *svc.ServiceContext) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		var req types.SkillRunReq
		if err := httpx.ParsePath(r, &req); err != nil {
			httpx.ErrorCtx(r.Context(), w, err)
			return
		}
		var body components.SkillRunBody
		if err := httpx.ParseJsonBody(r, &body); err != nil {
			httpx.ErrorCtx(r.Context(), w, err)
			return
		}

		l := components.NewSkillRunLogic(r.Context(), svcCtx)
		resp, err := l.Run(req.SkillId, body)
		if err != nil {
			httpx.ErrorCtx(r.Context(), w, err)
		} else {
			httpx.OkJsonCtx(r.Context(), w, resp)
		}
	}
}
