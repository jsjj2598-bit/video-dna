// Package middleware contains HTTP boundary policies shared by API groups.
package middleware

import (
	"crypto/subtle"
	"encoding/json"
	"net/http"
	"strings"
)

// TokenAuth protects /api while leaving embedded static files and health open.
func TokenAuth(token string) func(http.HandlerFunc) http.HandlerFunc {
	return func(next http.HandlerFunc) http.HandlerFunc {
		return func(w http.ResponseWriter, r *http.Request) {
			if token == "" || !strings.HasPrefix(r.URL.Path, "/api/") {
				next(w, r)
				return
			}
			provided := r.Header.Get("X-VideoDNA-Token")
			if provided == "" {
				if cookie, err := r.Cookie("videodna_token"); err == nil {
					provided = cookie.Value
				}
			}
			if len(provided) != len(token) || subtle.ConstantTimeCompare([]byte(provided), []byte(token)) != 1 {
				w.Header().Set("Content-Type", "application/json; charset=utf-8")
				w.WriteHeader(http.StatusUnauthorized)
				_ = json.NewEncoder(w).Encode(map[string]string{"detail": "API token 无效"})
				return
			}
			next(w, r)
		}
	}
}
