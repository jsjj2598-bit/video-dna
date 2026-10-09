package export

import (
	"encoding/json"
	"io"
	"net/http"
	"os"
	"path/filepath"
	"strings"

	"github.com/jsjj2598-bit/video-dna/service/videodna/api/internal/domain"
	"github.com/jsjj2598-bit/video-dna/service/videodna/api/internal/service/exporter"
	"github.com/jsjj2598-bit/video-dna/service/videodna/api/internal/xerr"
)

// Request is the existing frontend-compatible flat DNA export body.
type Request struct {
	domain.DNA
	DownloadDir string `json:"_download_dir"`
}

// Result is either an in-memory attachment or an explicit saved path.
type Result struct {
	File      exporter.File
	SavedPath string
}

func (l *ExportLogic) Render(r *http.Request) (Result, error) {
	var request Request
	decoder := json.NewDecoder(io.LimitReader(r.Body, 32<<20))
	if err := decoder.Decode(&request); err != nil {
		return Result{}, xerr.Wrap(http.StatusBadRequest, "DNA JSON 无效", err)
	}
	format := strings.TrimSpace(r.URL.Query().Get("fmt"))
	sourcePath := ""
	if request.SessionID != "" {
		sourcePath, _ = l.svcCtx.Storage.SourceVideo(request.SessionID)
	}
	file, err := exporter.Render(&request.DNA, format, sourcePath)
	if err != nil {
		return Result{}, xerr.New(http.StatusBadRequest, err.Error())
	}
	if strings.TrimSpace(request.DownloadDir) == "" {
		return Result{File: file}, nil
	}
	directory := expandHome(request.DownloadDir)
	if err := os.MkdirAll(directory, 0o700); err != nil {
		return Result{}, xerr.Wrap(http.StatusBadRequest, "导出目录不可写", err)
	}
	destination := filepath.Join(directory, file.Name)
	if err := os.WriteFile(destination, file.Data, 0o600); err != nil {
		return Result{}, xerr.Wrap(http.StatusBadRequest, "导出失败", err)
	}
	return Result{SavedPath: destination}, nil
}

func expandHome(path string) string {
	path = strings.TrimSpace(path)
	if path == "~" || strings.HasPrefix(path, "~/") || strings.HasPrefix(path, `~\`) {
		if home, err := os.UserHomeDir(); err == nil {
			path = filepath.Join(home, strings.TrimLeft(path[1:], `/\`))
		}
	}
	return filepath.Clean(path)
}
