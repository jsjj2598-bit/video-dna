# Contributing

感谢你参与 Video DNA Analyzer。项目当前处于 alpha 阶段，提交应优先保持分析结果、HTTP API 和桌面端行为可验证。

## 开发环境

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -e ".[asr,dev]"
npm ci
```

## 提交前检查

```bash
ruff check app tests
pytest
python -m compileall -q app
node --check electron/main.js
node --check electron/preload.js
for file in app/static/js/*.js; do node --check "$file"; done
```

涉及分析算法或导出格式的变更必须增加回归测试。涉及 EDL、XML、SRT 或剪映草稿的变更，还应说明使用哪个外部软件和版本完成了导入验证。

## 代码组织

- `app/api/routes/`：HTTP 输入输出，不放分析算法和文件系统细节。
- `app/services/`：任务、存储、模板和分析用例。
- `app/core/`：配置、安全和全局常量。
- `app/analyzer/`：纯视频/音频分析能力。
- `tests/`：纯函数测试、服务测试和 API 回归测试。

请避免重新引入“最近一次任务”全局变量、请求间共享 API Key、静默吞掉异常或在路由中直接拼接用户文件路径。
