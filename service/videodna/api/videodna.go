// Code scaffolded by goctl. Safe to edit.
// goctl 1.9.2

package main

import (
	"context"
	"errors"
	"flag"
	"fmt"
	"io/fs"
	"net/http"
	"os"

	webapp "github.com/jsjj2598-bit/video-dna/app"
	"github.com/jsjj2598-bit/video-dna/service/videodna/api/internal/config"
	"github.com/jsjj2598-bit/video-dna/service/videodna/api/internal/handler"
	appmiddleware "github.com/jsjj2598-bit/video-dna/service/videodna/api/internal/middleware"
	"github.com/jsjj2598-bit/video-dna/service/videodna/api/internal/svc"
	"github.com/jsjj2598-bit/video-dna/service/videodna/api/internal/xerr"

	"github.com/zeromicro/go-zero/core/conf"
	"github.com/zeromicro/go-zero/rest"
	"github.com/zeromicro/go-zero/rest/httpx"
)

var configFile = flag.String("f", "etc/videodna.yaml", "the config file")

func main() {
	flag.Parse()

	c := config.Default()
	if _, err := os.Stat(*configFile); err == nil {
		conf.MustLoad(*configFile, &c)
	}
	if err := config.Normalize(&c); err != nil {
		panic(err)
	}
	httpx.SetErrorHandlerCtx(func(_ context.Context, err error) (int, any) {
		var apiError *xerr.Error
		if errors.As(err, &apiError) {
			return apiError.Status, map[string]string{"detail": apiError.Message}
		}
		return http.StatusBadRequest, map[string]string{"detail": err.Error()}
	})

	server := rest.MustNewServer(c.RestConf)
	defer server.Stop()
	server.Use(appmiddleware.TokenAuth(c.Auth.Token))

	ctx, err := svc.NewServiceContext(c)
	if err != nil {
		panic(err)
	}
	handler.RegisterHandlers(server, ctx)
	registerStatic(server, c.Auth.Token)

	fmt.Printf("Video DNA Go backend 0.4.0 listening at http://%s:%d\n", c.Host, c.Port)
	server.Start()
}

func registerStatic(server *rest.Server, token string) {
	staticFS := webapp.Static()
	fileServer := http.FileServer(http.FS(staticFS))
	server.AddRoute(rest.Route{Method: http.MethodGet, Path: "/", Handler: func(w http.ResponseWriter, r *http.Request) {
		if token != "" && r.URL.Query().Get("token") == token {
			http.SetCookie(w, &http.Cookie{Name: "videodna_token", Value: token, Path: "/", HttpOnly: true, SameSite: http.SameSiteStrictMode})
		}
		index, err := fs.ReadFile(staticFS, "index.html")
		if err != nil {
			http.Error(w, "UI unavailable", http.StatusInternalServerError)
			return
		}
		w.Header().Set("Content-Type", "text/html; charset=utf-8")
		_, _ = w.Write(index)
	}})
	for _, path := range []string{"/app.css", "/js/analysis.js", "/js/components.js", "/js/core.js", "/js/history.js", "/js/studio.js"} {
		assetPath := path
		server.AddRoute(rest.Route{Method: http.MethodGet, Path: "/static" + path, Handler: func(w http.ResponseWriter, r *http.Request) {
			clone := r.Clone(r.Context())
			clone.URL.Path = assetPath
			fileServer.ServeHTTP(w, clone)
		}})
	}
}
