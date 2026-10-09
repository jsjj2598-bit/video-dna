# Contributing

项目使用 Go + go-zero 后端和 Electron 桌面壳。提交应保持 HTTP JSON、桌面行为和导出格式向后兼容。

## 开发环境

```bash
go mod download
npm ci
npm start
```

## 提交前检查

```bash
gofmt -w app internal pkg scripts service
go test -race ./...
go vet ./...
npm test
for file in app/static/js/*.js; do node --check "$file"; done
```

## 约定

- `videodna.api` 是 HTTP 契约源，接口变更先改契约再运行 goctl。
- handler 只处理 HTTP 输入输出；logic 编排用例；service 负责领域能力和持久化。
- FFmpeg、AI 服务等第三方集成只放在 `pkg/x*`，业务层不直接拼第三方请求。
- 不使用包级“最近任务”、跨请求共享密钥或未经校验的用户路径。
- 算法、存储、导出或模板变更必须补 Go 回归测试。
