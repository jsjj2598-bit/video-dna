// Code scaffolded by goctl. Safe to edit.
// goctl 1.9.2

package studio

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"strings"

	"github.com/jsjj2598-bit/video-dna/pkg/xaiapi"
	"github.com/jsjj2598-bit/video-dna/service/videodna/api/internal/svc"
	"github.com/jsjj2598-bit/video-dna/service/videodna/api/internal/types"
	"github.com/jsjj2598-bit/video-dna/service/videodna/api/internal/xerr"

	"github.com/zeromicro/go-zero/core/logx"
)

type AiStoryboardLogic struct {
	logx.Logger
	ctx    context.Context
	svcCtx *svc.ServiceContext
}

// 生成短视频分镜
func NewAiStoryboardLogic(ctx context.Context, svcCtx *svc.ServiceContext) *AiStoryboardLogic {
	return &AiStoryboardLogic{
		Logger: logx.WithContext(ctx),
		ctx:    ctx,
		svcCtx: svcCtx,
	}
}

func (l *AiStoryboardLogic) AiStoryboard(req *types.StoryboardReq) (any, error) {
	topic := strings.TrimSpace(req.Topic)
	if topic == "" {
		return nil, xerr.New(http.StatusBadRequest, "请输入主题或文案")
	}
	length := min(20, max(3, int(req.Length)))
	if req.Length == 0 {
		length = 6
	}
	model, ok, err := l.svcCtx.Registry.EnabledChatModel()
	if err != nil || !ok {
		scenes := []string{"开场钩子：快速吸引注意力", "主体推进：展示核心内容", "情绪强化：特写/慢镜", "高潮：节奏加快", "结尾：留白与引导"}
		cameras := []string{"中景固定", "推近", "侧移跟拍", "特写", "拉远"}
		shots := make([]map[string]any, 0, length)
		for index := 0; index < length; index++ {
			shots = append(shots, map[string]any{"index": index, "duration": 3.0, "scene": scenes[index%len(scenes)], "camera": cameras[index%len(cameras)], "voiceover": ""})
		}
		return map[string]any{"method": "heuristic", "topic": topic, "shots": shots, "hint": "未配置对话模型，已生成基础框架。"}, nil
	}
	prompt := "为主题「" + topic + "」创作短视频分镜，输出 JSON 数组；每项包含 scene、camera、duration、voiceover、transition。镜头数严格为 " + fmt.Sprint(length) + "。"
	output, err := l.svcCtx.Registry.Chat(l.ctx, model, []xaiapi.Message{{Role: "system", Content: "你是专业分镜脚本导演，只输出 JSON。"}, {Role: "user", Content: prompt}}, true)
	if err != nil {
		return nil, xerr.Wrap(http.StatusBadGateway, "分镜生成失败", err)
	}
	start, end := strings.IndexByte(output, '['), strings.LastIndexByte(output, ']')
	if start < 0 || end <= start {
		return nil, xerr.New(http.StatusBadGateway, "模型未返回分镜数组")
	}
	var shots []any
	if err := json.Unmarshal([]byte(output[start:end+1]), &shots); err != nil {
		return nil, xerr.Wrap(http.StatusBadGateway, "模型返回的分镜 JSON 无效", err)
	}
	return map[string]any{"method": "llm", "model": model.Model, "topic": topic, "shots": shots}, nil
}
