// Code scaffolded by goctl. Safe to edit.
// goctl 1.9.2

package media

import (
	"net/http"

	"github.com/jsjj2598-bit/video-dna/service/videodna/api/internal/logic/media"
	"github.com/jsjj2598-bit/video-dna/service/videodna/api/internal/svc"
	"github.com/zeromicro/go-zero/rest/httpx"
)

// 获取分析历史列表
func HistoryListHandler(svcCtx *svc.ServiceContext) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		l := media.NewHistoryListLogic(r.Context(), svcCtx)
		resp, err := l.HistoryList()
		if err != nil {
			httpx.ErrorCtx(r.Context(), w, err)
		} else {
			httpx.OkJsonCtx(r.Context(), w, resp)
		}
	}
}
