// Code scaffolded by goctl. Safe to edit.
// goctl 1.9.2

package export

import (
	"mime"
	"net/http"
	"path/filepath"

	"github.com/jsjj2598-bit/video-dna/service/videodna/api/internal/logic/export"
	"github.com/jsjj2598-bit/video-dna/service/videodna/api/internal/svc"
	"github.com/zeromicro/go-zero/rest/httpx"
)

// 导出 EDL、FCP7 XML、Cutmark、SRT 或 ZIP
func ExportHandler(svcCtx *svc.ServiceContext) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		l := export.NewExportLogic(r.Context(), svcCtx)
		result, err := l.Render(r)
		if err != nil {
			httpx.ErrorCtx(r.Context(), w, err)
		} else if result.SavedPath != "" {
			httpx.OkJsonCtx(r.Context(), w, map[string]any{"path": result.SavedPath, "fmt": r.URL.Query().Get("fmt")})
		} else {
			contentType := result.File.ContentType
			if contentType == "" {
				contentType = mime.TypeByExtension(filepath.Ext(result.File.Name))
			}
			w.Header().Set("Content-Type", contentType)
			w.Header().Set("Content-Disposition", `attachment; filename="`+result.File.Name+`"`)
			w.WriteHeader(http.StatusOK)
			_, _ = w.Write(result.File.Data)
		}
	}
}
