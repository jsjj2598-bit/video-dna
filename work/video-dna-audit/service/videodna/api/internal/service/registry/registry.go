// Package registry manages local models, components, skills and executable plugins.
package registry

import (
	"archive/zip"
	"bytes"
	"context"
	"crypto/ed25519"
	"crypto/sha256"
	"encoding/base64"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"os"
	"os/exec"
	"path"
	"path/filepath"
	"runtime"
	"sort"
	"strings"
	"sync"
	"time"

	"github.com/google/uuid"
	"github.com/jsjj2598-bit/video-dna/pkg/xaiapi"
	"github.com/jsjj2598-bit/video-dna/service/videodna/api/internal/domain"
)

// Model describes one OpenAI-compatible model.
type Model struct {
	ID       string `json:"id"`
	Name     string `json:"name"`
	Kind     string `json:"kind"`
	Provider string `json:"provider"`
	BaseURL  string `json:"base_url"`
	Model    string `json:"model"`
	// APIKey is deliberately process-local. It must never be serialized to config.json.
	APIKey    string `json:"-"`
	Builtin   bool   `json:"builtin"`
	HasAPIKey bool   `json:"has_api_key,omitempty"`
}

// Component describes one analysis feature switch.
type Component struct {
	ID        string `json:"id"`
	Name      string `json:"name"`
	Desc      string `json:"desc"`
	Kind      string `json:"kind"`
	Icon      string `json:"icon"`
	DefaultOn bool   `json:"default_on,omitempty"`
	Enabled   bool   `json:"enabled"`
	ModelID   string `json:"model_id,omitempty"`
}

// Skill is a reusable prompt template.
type Skill struct {
	ID      string `json:"id"`
	Name    string `json:"name"`
	Desc    string `json:"desc"`
	Prompt  string `json:"prompt"`
	Builtin bool   `json:"builtin"`
}

// Plugin is a cross-platform executable plugin manifest.
type Plugin struct {
	ID          string            `json:"id"`
	Name        string            `json:"name"`
	Version     string            `json:"version"`
	Desc        string            `json:"desc,omitempty"`
	Hooks       []string          `json:"hooks"`
	Enabled     bool              `json:"enabled"`
	Entry       string            `json:"entry,omitempty"`
	Entries     map[string]string `json:"entries,omitempty"`
	Compatible  bool              `json:"compatible"`
	Path        string            `json:"-"`
	Publisher   string            `json:"publisher,omitempty"`
	PublicKey   string            `json:"public_key,omitempty"`
	Signature   string            `json:"signature,omitempty"`
	Files       map[string]string `json:"files,omitempty"`
	Fingerprint string            `json:"fingerprint,omitempty"`
	Trusted     bool              `json:"trusted,omitempty"`
}

type configFile struct {
	Models     []Model                     `json:"models,omitempty"`
	Components map[string]componentSetting `json:"components,omitempty"`
	Skills     []Skill                     `json:"skills,omitempty"`
}

type componentSetting struct {
	Enabled bool   `json:"enabled"`
	ModelID string `json:"model_id,omitempty"`
}

// Service persists registry state as one atomic JSON file.
type Service struct {
	mu          sync.RWMutex
	configPath  string
	pluginsDir  string
	trustPath   string
	maxZipBytes int64
	ai          *xaiapi.Client
	secrets     map[string]string
}

// New creates a registry.
func New(dataDir, pluginsDir string, maxZipBytes int64) *Service {
	return &Service{
		configPath: filepath.Join(dataDir, "config.json"), pluginsDir: pluginsDir, trustPath: filepath.Join(dataDir, "trusted-plugin-publishers.json"),
		maxZipBytes: maxZipBytes, ai: xaiapi.NewClient(90 * time.Second), secrets: make(map[string]string),
	}
}

var defaultModels = []Model{
	{ID: "openai-gpt4o", Name: "OpenAI GPT-4o", Kind: "vision", Provider: "openai", BaseURL: "https://api.openai.com/v1", Model: "gpt-4o", Builtin: true},
	{ID: "openai-gpt4o-mini", Name: "OpenAI GPT-4o Mini", Kind: "chat", Provider: "openai", BaseURL: "https://api.openai.com/v1", Model: "gpt-4o-mini", Builtin: true},
	{ID: "qwen-vl-max", Name: "通义千问 Qwen-VL-Max", Kind: "vision", Provider: "dashscope", BaseURL: "https://dashscope.aliyuncs.com/compatible-mode/v1", Model: "qwen-vl-max", Builtin: true},
	{ID: "qwen-max", Name: "通义千问 Qwen-Max", Kind: "chat", Provider: "dashscope", BaseURL: "https://dashscope.aliyuncs.com/compatible-mode/v1", Model: "qwen-max", Builtin: true},
	{ID: "ollama-llama3", Name: "Ollama Llama3（本地）", Kind: "chat", Provider: "ollama", BaseURL: "http://localhost:11434/v1", Model: "llama3", Builtin: true},
}

var defaultComponents = map[string]Component{
	"describer": {ID: "describer", Name: "镜头语义描述", Desc: "生成画面内容、景别、场景类型与情绪标签", Kind: "vision", Icon: "🖼️", DefaultOn: true},
	"asr":       {ID: "asr", Name: "语音转写 ASR（预留）", Desc: "预留 whisper.cpp 可执行组件接口；当前版本默认关闭", Kind: "local", Icon: "🎙️", DefaultOn: false},
	"beats":     {ID: "beats", Name: "节拍卡点检测", Desc: "纯 Go BPM、节拍点和镜头卡点分析", Kind: "local", Icon: "🥁", DefaultOn: true},
	"translate": {ID: "translate", Name: "台词翻译", Desc: "用对话模型将台词翻译为中文", Kind: "chat", Icon: "🌐", DefaultOn: false},
	"summarize": {ID: "summarize", Name: "智能摘要", Desc: "用对话模型生成剪辑分析摘要", Kind: "chat", Icon: "📝", DefaultOn: false},
}

var defaultSkills = []Skill{
	{ID: "review", Name: "剪辑点评", Desc: "点评节奏、转场与卡点", Builtin: true, Prompt: "请以专业剪辑师视角点评视频。\n【视频概况】{meta}\n【摘要】{summary}\n【镜头】{shots}\n【台词】{transcript}\n请评价节奏、音乐配合、转场并给出三条具体建议。"},
	{ID: "structure", Name: "剪辑结构拆解", Desc: "拆解钩子、节奏曲线与结尾设计", Builtin: true, Prompt: "请拆解视频结构。\n【镜头】{shots}\n【摘要】{summary}\n【音频】{audio}\n输出开头钩子、结构曲线、高潮、结尾和常见结构模板。"},
	{ID: "copywriting", Name: "爆款标题文案", Desc: "生成多平台标题与文案", Builtin: true, Prompt: "根据视频生成抖音、B站、小红书标题和一段发布文案。\n【摘要】{summary}\n【台词】{transcript}\n【时长】{duration} 秒。"},
	{ID: "emotion_curve", Name: "情绪曲线分析", Desc: "还原观众情绪起伏", Builtin: true, Prompt: "分析视频情绪曲线。\n【镜头】{shots}\n【音频】{audio}\n描述阶段、峰谷、断层风险和优化建议。"},
}

// ListModels returns merged models with keys removed.
func (s *Service) ListModels() ([]Model, error) {
	models, err := s.modelsWithSecrets()
	if err != nil {
		return nil, err
	}
	for index := range models {
		models[index].HasAPIKey = models[index].APIKey != "" || (models[index].Provider == "ollama" && !models[index].Builtin)
		models[index].APIKey = ""
	}
	return models, nil
}

func (s *Service) modelsWithSecrets() ([]Model, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	cfg, err := s.loadLocked()
	if err != nil {
		return nil, err
	}
	merged := make(map[string]Model, len(defaultModels)+len(cfg.Models))
	migrated := false
	for _, model := range defaultModels {
		merged[model.ID] = model
	}
	for _, model := range cfg.Models {
		if model.APIKey != "" {
			// Migrate historical plaintext keys into the process-local secret map,
			// then rewrite config.json without the secret.
			s.secrets[model.ID] = model.APIKey
			model.APIKey = ""
			migrated = true
		}
		merged[model.ID] = model
	}
	if migrated {
		if err := s.saveLocked(cfg); err != nil {
			return nil, err
		}
	}
	result := make([]Model, 0, len(merged))
	for _, model := range merged {
		if key := s.secrets[model.ID]; key != "" {
			model.APIKey = key
		}
		result = append(result, model)
	}
	sort.Slice(result, func(i, j int) bool { return result[i].ID < result[j].ID })
	return result, nil
}

// GetModel returns one model including its secret for internal use.
func (s *Service) GetModel(modelID string) (Model, bool, error) {
	models, err := s.modelsWithSecrets()
	if err != nil {
		return Model{}, false, err
	}
	for _, model := range models {
		if model.ID == modelID {
			return model, true, nil
		}
	}
	return Model{}, false, nil
}

// UpsertModel validates and persists a custom override.
func (s *Service) UpsertModel(input Model) (Model, error) {
	input.ID = strings.TrimSpace(input.ID)
	if input.ID == "" {
		input.ID = strings.ReplaceAll(uuid.NewString()[:8], "-", "")
	}
	if !validID(input.ID) {
		return Model{}, errors.New("model_id 非法")
	}
	input.Name, input.BaseURL, input.Model = strings.TrimSpace(input.Name), strings.TrimSpace(input.BaseURL), strings.TrimSpace(input.Model)
	if input.Name == "" || input.BaseURL == "" || input.Model == "" {
		return Model{}, errors.New("名称、接口地址与模型名不能为空")
	}
	if !strings.HasPrefix(input.BaseURL, "http://") && !strings.HasPrefix(input.BaseURL, "https://") {
		return Model{}, errors.New("接口地址必须以 http(s):// 开头")
	}
	if input.Kind != "vision" && input.Kind != "chat" {
		input.Kind = "chat"
	}
	input.BaseURL = strings.TrimRight(input.BaseURL, "/")
	input.Builtin, input.HasAPIKey = false, false
	s.mu.Lock()
	defer s.mu.Unlock()
	cfg, err := s.loadLocked()
	if err != nil {
		return Model{}, err
	}
	for _, existing := range append(defaultModels, cfg.Models...) {
		if existing.ID == input.ID {
			if existing.APIKey != "" && s.secrets[input.ID] == "" {
				s.secrets[input.ID] = existing.APIKey
			}
			if input.APIKey == "" {
				input.APIKey = s.secrets[input.ID]
			}
		}
	}
	if input.APIKey != "" {
		s.secrets[input.ID] = input.APIKey
	} else if existing, ok := s.secrets[input.ID]; ok {
		input.APIKey = existing
	}
	// Keep secrets out of the persisted model metadata.
	persisted := input
	persisted.APIKey = ""
	found := false
	for index := range cfg.Models {
		if cfg.Models[index].ID == input.ID {
			cfg.Models[index], found = persisted, true
		}
	}
	if !found {
		cfg.Models = append(cfg.Models, persisted)
	}
	if err := s.saveLocked(cfg); err != nil {
		return Model{}, err
	}
	public := input
	public.HasAPIKey, public.APIKey = input.APIKey != "" || (input.Provider == "ollama" && !input.Builtin), ""
	return public, nil
}

// DeleteModel deletes only user overrides.
func (s *Service) DeleteModel(modelID string) (bool, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	cfg, err := s.loadLocked()
	if err != nil {
		return false, err
	}
	filtered := cfg.Models[:0]
	removed := false
	for _, model := range cfg.Models {
		if model.ID == modelID {
			removed = true
			continue
		}
		filtered = append(filtered, model)
	}
	delete(s.secrets, modelID)
	cfg.Models = filtered
	if removed {
		err = s.saveLocked(cfg)
	}
	return removed, err
}

// TestModel performs a minimal chat request.
func (s *Service) TestModel(ctx context.Context, modelID string) (string, error) {
	model, ok, err := s.GetModel(modelID)
	if err != nil || !ok {
		return "", errors.New("模型不存在")
	}
	if model.APIKey == "" && model.Provider != "ollama" {
		return "", errors.New("请先填写 API Key 再测试")
	}
	reply, err := s.ai.Chat(ctx, toAIModel(model), []xaiapi.Message{{Role: "user", Content: "请只回复两个字：正常"}}, false)
	if len(reply) > 200 {
		reply = reply[:200]
	}
	return reply, err
}

// ListComponents returns effective feature switches.
func (s *Service) ListComponents() ([]Component, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	cfg, err := s.loadLocked()
	if err != nil {
		return nil, err
	}
	result := make([]Component, 0, len(defaultComponents))
	for id, component := range defaultComponents {
		setting, ok := cfg.Components[id]
		component.Enabled = component.DefaultOn
		if ok {
			component.Enabled, component.ModelID = setting.Enabled, setting.ModelID
		}
		result = append(result, component)
	}
	sort.Slice(result, func(i, j int) bool { return result[i].ID < result[j].ID })
	return result, nil
}

// ComponentEnabled returns the effective switch state.
func (s *Service) ComponentEnabled(componentID string) bool {
	components, err := s.ListComponents()
	if err != nil {
		return false
	}
	for _, component := range components {
		if component.ID == componentID {
			return component.Enabled
		}
	}
	return false
}

// SetComponent persists one feature switch.
func (s *Service) SetComponent(componentID string, enabled bool, modelID string) (Component, error) {
	if _, ok := defaultComponents[componentID]; !ok {
		return Component{}, errors.New("组件不存在")
	}
	s.mu.Lock()
	cfg, err := s.loadLocked()
	if err == nil {
		if cfg.Components == nil {
			cfg.Components = make(map[string]componentSetting)
		}
		cfg.Components[componentID] = componentSetting{Enabled: enabled, ModelID: modelID}
		err = s.saveLocked(cfg)
	}
	s.mu.Unlock()
	if err != nil {
		return Component{}, err
	}
	components, err := s.ListComponents()
	for _, component := range components {
		if component.ID == componentID {
			return component, err
		}
	}
	return Component{}, errors.New("组件不存在")
}

// ListSkills returns built-in and custom prompts.
func (s *Service) ListSkills() ([]Skill, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	cfg, err := s.loadLocked()
	if err != nil {
		return nil, err
	}
	merged := make(map[string]Skill)
	for _, skill := range defaultSkills {
		merged[skill.ID] = skill
	}
	for _, skill := range cfg.Skills {
		merged[skill.ID] = skill
	}
	result := make([]Skill, 0, len(merged))
	for _, skill := range merged {
		result = append(result, skill)
	}
	sort.Slice(result, func(i, j int) bool { return result[i].ID < result[j].ID })
	return result, nil
}

// AddSkill validates and stores a user skill.
func (s *Service) AddSkill(skill Skill) (Skill, error) {
	skill.Name, skill.Prompt, skill.Desc = strings.TrimSpace(skill.Name), strings.TrimSpace(skill.Prompt), strings.TrimSpace(skill.Desc)
	if skill.Name == "" || skill.Prompt == "" {
		return Skill{}, errors.New("名称与提示词不能为空")
	}
	if skill.ID == "" {
		skill.ID = strings.ReplaceAll(uuid.NewString()[:8], "-", "")
	}
	if !validID(skill.ID) {
		return Skill{}, errors.New("skill_id 非法")
	}
	skill.Builtin = false
	s.mu.Lock()
	defer s.mu.Unlock()
	cfg, err := s.loadLocked()
	if err != nil {
		return Skill{}, err
	}
	found := false
	for index := range cfg.Skills {
		if cfg.Skills[index].ID == skill.ID {
			cfg.Skills[index], found = skill, true
		}
	}
	if !found {
		cfg.Skills = append(cfg.Skills, skill)
	}
	return skill, s.saveLocked(cfg)
}

// DeleteSkill deletes only custom skills.
func (s *Service) DeleteSkill(skillID string) (bool, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	cfg, err := s.loadLocked()
	if err != nil {
		return false, err
	}
	filtered, removed := cfg.Skills[:0], false
	for _, skill := range cfg.Skills {
		if skill.ID == skillID {
			removed = true
			continue
		}
		filtered = append(filtered, skill)
	}
	cfg.Skills = filtered
	if removed {
		err = s.saveLocked(cfg)
	}
	return removed, err
}

// RunSkill renders a prompt and calls the first configured chat model.
func (s *Service) RunSkill(ctx context.Context, skillID string, dna *domain.DNA) (string, string, error) {
	skills, err := s.ListSkills()
	if err != nil {
		return "", "", err
	}
	var selected *Skill
	for index := range skills {
		if skills[index].ID == skillID {
			selected = &skills[index]
			break
		}
	}
	if selected == nil {
		return "", "", errors.New("技能不存在")
	}
	model, ok, err := s.EnabledChatModel()
	if err != nil || !ok {
		return "", "", errors.New("没有可用的 chat 模型，请先配置 API Key")
	}
	prompt := renderPrompt(selected.Prompt, dna)
	output, err := s.ai.Chat(ctx, toAIModel(model), []xaiapi.Message{
		{Role: "system", Content: "你是专业的视频剪辑分析助手，回答简洁、结构清晰。"},
		{Role: "user", Content: prompt},
	}, false)
	return output, selected.Name, err
}

// EnabledChatModel returns the first configured chat model.
func (s *Service) EnabledChatModel() (Model, bool, error) {
	models, err := s.modelsWithSecrets()
	if err != nil {
		return Model{}, false, err
	}
	for _, model := range models {
		if model.Kind == "chat" && (model.APIKey != "" || (model.Provider == "ollama" && !model.Builtin)) {
			return model, true, nil
		}
	}
	return Model{}, false, nil
}

// EnabledVisionModel returns the selected or first configured vision model.
func (s *Service) EnabledVisionModel() (Model, bool, error) {
	if !s.ComponentEnabled("describer") {
		return Model{}, false, nil
	}
	components, _ := s.ListComponents()
	selectedID := ""
	for _, component := range components {
		if component.ID == "describer" {
			selectedID = component.ModelID
		}
	}
	models, err := s.modelsWithSecrets()
	if err != nil {
		return Model{}, false, err
	}
	for _, model := range models {
		if model.ID == selectedID && model.Kind == "vision" && model.APIKey != "" {
			return model, true, nil
		}
	}
	for _, model := range models {
		if model.Kind == "vision" && model.APIKey != "" {
			return model, true, nil
		}
	}
	return Model{}, false, nil
}

// DescribeImage calls a configured vision model.
func (s *Service) DescribeImage(ctx context.Context, model Model, imagePath, prompt string) (string, error) {
	return s.ai.DescribeImage(ctx, toAIModel(model), imagePath, prompt)
}

// Chat calls a selected internal model through the shared third-party wrapper.
func (s *Service) Chat(ctx context.Context, model Model, messages []xaiapi.Message, jsonMode bool) (string, error) {
	return s.ai.Chat(ctx, toAIModel(model), messages, jsonMode)
}

// ListPlugins loads valid manifests from the user plugin directory.
func (s *Service) ListPlugins() ([]Plugin, error) {
	entries, err := os.ReadDir(s.pluginsDir)
	if err != nil {
		return nil, err
	}
	plugins := make([]Plugin, 0, len(entries))
	for _, entry := range entries {
		if !entry.IsDir() {
			continue
		}
		plugin, loadErr := loadPlugin(filepath.Join(s.pluginsDir, entry.Name()))
		if loadErr == nil {
			trusted, trustErr := s.isTrustedPublisher(plugin.Fingerprint)
			if trustErr != nil {
				return nil, trustErr
			}
			plugin.Trusted = trusted
			plugins = append(plugins, plugin)
		}
	}
	sort.Slice(plugins, func(i, j int) bool { return plugins[i].ID < plugins[j].ID })
	return plugins, nil
}

// InstallPlugin installs a validated ZIP and returns its manifest.
func (s *Service) InstallPlugin(archivePath, approvedFingerprint string) (Plugin, error) {
	reader, err := zip.OpenReader(archivePath)
	if err != nil {
		return Plugin{}, errors.New("插件 ZIP 无效")
	}
	defer reader.Close()
	limit := s.maxZipBytes
	if limit <= 0 {
		limit = 50 * 1024 * 1024
	}
	if len(reader.File) > 500 {
		return Plugin{}, errors.New("插件文件数量超过上限")
	}
	temporary, err := os.MkdirTemp(s.pluginsDir, ".install-")
	if err != nil {
		return Plugin{}, err
	}
	defer os.RemoveAll(temporary)
	var total int64
	for _, file := range reader.File {
		if file.Mode()&os.ModeSymlink != 0 {
			return Plugin{}, errors.New("插件 ZIP 不允许符号链接")
		}
		total += int64(file.UncompressedSize64)
		if total > limit {
			return Plugin{}, errors.New("插件解压大小超过上限")
		}
		clean, safe := safeRelativePath(file.Name)
		if !safe {
			return Plugin{}, errors.New("插件 ZIP 包含非法路径")
		}
		destination := filepath.Join(temporary, clean)
		if file.FileInfo().IsDir() {
			if err := os.MkdirAll(destination, 0o700); err != nil {
				return Plugin{}, err
			}
			continue
		}
		if err := os.MkdirAll(filepath.Dir(destination), 0o700); err != nil {
			return Plugin{}, err
		}
		source, openErr := file.Open()
		if openErr != nil {
			return Plugin{}, openErr
		}
		target, createErr := os.OpenFile(destination, os.O_CREATE|os.O_TRUNC|os.O_WRONLY, file.Mode().Perm()|0o600)
		if createErr == nil {
			_, createErr = io.Copy(target, source)
			createErr = errors.Join(createErr, target.Close())
		}
		_ = source.Close()
		if createErr != nil {
			return Plugin{}, createErr
		}
	}
	manifestRoot, err := findManifestRoot(temporary)
	if err != nil {
		return Plugin{}, err
	}
	plugin, err := loadPlugin(manifestRoot)
	if err != nil {
		return Plugin{}, err
	}
	if err := verifyPluginSignature(manifestRoot, plugin); err != nil {
		return Plugin{}, err
	}
	if plugin.Fingerprint == "" {
		return Plugin{}, errors.New("插件签名公钥无效")
	}
	if approvedFingerprint != plugin.Fingerprint {
		return Plugin{}, fmt.Errorf("PUBLISHER_CONFIRM_REQUIRED:%s", plugin.Fingerprint)
	}
	if err := s.trustPublisher(plugin.Fingerprint); err != nil {
		return Plugin{}, err
	}
	destination := filepath.Join(s.pluginsDir, plugin.ID)
	if err := os.RemoveAll(destination); err != nil {
		return Plugin{}, err
	}
	if err := copyDirectory(manifestRoot, destination); err != nil {
		return Plugin{}, err
	}
	installed, err := loadPlugin(destination)
	installed.Trusted = err == nil
	return installed, err
}

// DeletePlugin removes only a user plugin directory.
func (s *Service) DeletePlugin(pluginID string) (bool, error) {
	if !validID(pluginID) {
		return false, errors.New("plugin_id 非法")
	}
	directory := filepath.Join(s.pluginsDir, pluginID)
	plugin, err := loadPlugin(directory)
	if errors.Is(err, os.ErrNotExist) {
		return false, nil
	}
	if err != nil || plugin.ID != pluginID {
		return false, err
	}
	return true, os.RemoveAll(directory)
}

// RunPluginHooks executes compatible plugins using a JSON stdin/stdout protocol.
func (s *Service) RunPluginHooks(ctx context.Context, dna *domain.DNA) (*domain.DNA, error) {
	plugins, err := s.ListPlugins()
	if err != nil {
		return dna, err
	}
	current := dna
	for _, plugin := range plugins {
		if !plugin.Enabled || !plugin.Compatible || !plugin.Trusted {
			continue
		}
		entry := pluginEntry(plugin)
		for _, hook := range plugin.Hooks {
			payload, marshalErr := json.Marshal(current)
			if marshalErr != nil {
				return current, marshalErr
			}
			hookCtx, cancel := context.WithTimeout(ctx, 30*time.Second)
			cmd := exec.CommandContext(hookCtx, entry, hook)
			cmd.Stdin = bytes.NewReader(payload)
			stdout, pipeErr := cmd.StdoutPipe()
			if pipeErr != nil {
				cancel()
				return current, fmt.Errorf("插件 %s 输出管道失败: %w", plugin.ID, pipeErr)
			}
			runErr := cmd.Start()
			var output []byte
			if runErr == nil {
				output, runErr = io.ReadAll(io.LimitReader(stdout, 20*1024*1024+1))
			}
			if runErr == nil {
				runErr = cmd.Wait()
			}
			cancel()
			if runErr != nil {
				return current, fmt.Errorf("插件 %s 执行失败: %w", plugin.ID, runErr)
			}
			if len(output) > 20*1024*1024 {
				return current, fmt.Errorf("插件 %s 输出超过上限", plugin.ID)
			}
			var updated domain.DNA
			if err := json.Unmarshal(output, &updated); err != nil {
				return current, fmt.Errorf("插件 %s 输出不是有效 DNA JSON: %w", plugin.ID, err)
			}
			current = &updated
		}
	}
	return current, nil
}

func (s *Service) loadLocked() (configFile, error) {
	var cfg configFile
	payload, err := os.ReadFile(s.configPath)
	if errors.Is(err, os.ErrNotExist) {
		return cfg, nil
	}
	if err != nil {
		return cfg, err
	}
	if err := json.Unmarshal(bytes.TrimPrefix(payload, []byte{0xef, 0xbb, 0xbf}), &cfg); err != nil {
		return cfg, fmt.Errorf("读取配置失败: %w", err)
	}
	return cfg, nil
}

func (s *Service) saveLocked(cfg configFile) error {
	payload, err := json.MarshalIndent(cfg, "", "  ")
	if err != nil {
		return err
	}
	temporary := s.configPath + ".tmp"
	if err := os.WriteFile(temporary, payload, 0o600); err != nil {
		return err
	}
	if err := os.Chmod(temporary, 0o600); err != nil && runtime.GOOS != "windows" {
		return err
	}
	return os.Rename(temporary, s.configPath)
}

func toAIModel(model Model) xaiapi.Model {
	return xaiapi.Model{BaseURL: model.BaseURL, Name: model.Model, APIKey: model.APIKey}
}

func renderPrompt(prompt string, dna *domain.DNA) string {
	meta, _ := json.Marshal(dna.Meta)
	shots, _ := json.Marshal(dna.Shots)
	audio, _ := json.Marshal(dna.Audio)
	transcript := dna.Audio.Text
	if transcript == "" {
		parts := make([]string, 0)
		for _, shot := range dna.Shots {
			if shot.Transcript != "" {
				parts = append(parts, shot.Transcript)
			}
		}
		transcript = strings.Join(parts, "，")
	}
	return strings.NewReplacer(
		"{meta}", string(meta), "{summary}", dna.Summary, "{shots}", string(shots),
		"{audio}", string(audio), "{transcript}", transcript,
		"{bpm}", fmt.Sprintf("%.1f", dna.Audio.TempoBPM),
		"{duration}", fmt.Sprintf("%.3f", dna.Meta.Duration),
	).Replace(prompt)
}

func validID(value string) bool {
	if value == "" || len(value) > 128 {
		return false
	}
	for _, char := range value {
		if (char < 'a' || char > 'z') && (char < 'A' || char > 'Z') && (char < '0' || char > '9') && char != '-' && char != '_' {
			return false
		}
	}
	return true
}

func loadPlugin(directory string) (Plugin, error) {
	payload, err := os.ReadFile(filepath.Join(directory, "manifest.json"))
	if err != nil {
		return Plugin{}, err
	}
	var plugin Plugin
	if err := json.Unmarshal(bytes.TrimPrefix(payload, []byte{0xef, 0xbb, 0xbf}), &plugin); err != nil {
		return Plugin{}, errors.New("manifest.json 格式不正确")
	}
	if !validID(plugin.ID) || strings.TrimSpace(plugin.Name) == "" {
		return Plugin{}, errors.New("插件 ID 或名称无效")
	}
	if plugin.Version == "" {
		plugin.Version = "1.0"
	}
	if len(plugin.Hooks) == 0 {
		plugin.Hooks = []string{"on_shots", "on_summary"}
	}
	plugin.Path = directory
	plugin.Fingerprint = pluginFingerprint(plugin.PublicKey)
	if err := verifyPluginSignature(directory, plugin); err != nil {
		return Plugin{}, err
	}
	entry := pluginEntry(plugin)
	if entry != "" {
		if info, statErr := os.Stat(entry); statErr == nil && !info.IsDir() {
			plugin.Compatible = filepath.Ext(entry) != ".py"
		}
	}
	return plugin, nil
}

func verifyPluginSignature(directory string, plugin Plugin) error {
	if plugin.PublicKey == "" || plugin.Signature == "" || len(plugin.Files) == 0 {
		return errors.New("插件必须提供签名、公钥和文件哈希")
	}
	publicKey, err := base64.StdEncoding.DecodeString(plugin.PublicKey)
	if err != nil || len(publicKey) != ed25519.PublicKeySize {
		return errors.New("插件公钥无效")
	}
	signature, err := base64.StdEncoding.DecodeString(plugin.Signature)
	if err != nil || len(signature) != ed25519.SignatureSize {
		return errors.New("插件签名无效")
	}
	copyPlugin := plugin
	copyPlugin.Path = ""
	copyPlugin.Signature = ""
	copyPlugin.Fingerprint = ""
	copyPlugin.Trusted = false
	payload, err := json.Marshal(copyPlugin)
	if err != nil || !ed25519.Verify(ed25519.PublicKey(publicKey), payload, signature) {
		return errors.New("插件签名校验失败")
	}
	for name, expected := range plugin.Files {
		clean, safe := safeRelativePath(name)
		if !safe || clean == "manifest.json" {
			return errors.New("插件文件清单包含非法路径")
		}
		actual, err := sha256File(filepath.Join(directory, clean))
		if err != nil || !strings.EqualFold(actual, expected) {
			return fmt.Errorf("插件文件哈希不匹配: %s", name)
		}
	}
	return nil
}

func pluginFingerprint(encodedPublicKey string) string {
	publicKey, err := base64.StdEncoding.DecodeString(encodedPublicKey)
	if err != nil || len(publicKey) != ed25519.PublicKeySize {
		return ""
	}
	keyHash := sha256.Sum256(publicKey)
	return fmt.Sprintf("%x", keyHash[:])
}

func (s *Service) isTrustedPublisher(fingerprint string) (bool, error) {
	if fingerprint == "" {
		return false, nil
	}
	s.mu.RLock()
	defer s.mu.RUnlock()
	payload, err := os.ReadFile(s.trustPath)
	if errors.Is(err, os.ErrNotExist) {
		return false, nil
	}
	if err != nil {
		return false, err
	}
	var trusted []string
	if err := json.Unmarshal(payload, &trusted); err != nil {
		return false, fmt.Errorf("读取插件信任列表失败: %w", err)
	}
	for _, item := range trusted {
		if item == fingerprint {
			return true, nil
		}
	}
	return false, nil
}

func (s *Service) trustPublisher(fingerprint string) error {
	if len(fingerprint) != 64 {
		return errors.New("插件发布者指纹无效")
	}
	for _, char := range fingerprint {
		if !strings.ContainsRune("0123456789abcdef", char) {
			return errors.New("插件发布者指纹无效")
		}
	}
	s.mu.Lock()
	defer s.mu.Unlock()
	var trusted []string
	payload, err := os.ReadFile(s.trustPath)
	if err != nil && !errors.Is(err, os.ErrNotExist) {
		return err
	}
	if err == nil {
		if err := json.Unmarshal(payload, &trusted); err != nil {
			return fmt.Errorf("读取插件信任列表失败: %w", err)
		}
	}
	for _, item := range trusted {
		if item == fingerprint {
			return nil
		}
	}
	trusted = append(trusted, fingerprint)
	payload, err = json.MarshalIndent(trusted, "", "  ")
	if err != nil {
		return err
	}
	if err := os.MkdirAll(filepath.Dir(s.trustPath), 0o700); err != nil {
		return err
	}
	temporary := s.trustPath + ".tmp"
	if err := os.WriteFile(temporary, payload, 0o600); err != nil {
		return err
	}
	if err := os.Rename(temporary, s.trustPath); err != nil {
		_ = os.Remove(temporary)
		return err
	}
	return nil
}

func sha256File(path string) (string, error) {
	file, err := os.Open(path)
	if err != nil {
		return "", err
	}
	defer file.Close()
	hash := sha256.New()
	if _, err := io.Copy(hash, file); err != nil {
		return "", err
	}
	return fmt.Sprintf("%x", hash.Sum(nil)), nil
}

func pluginEntry(plugin Plugin) string {
	entry := plugin.Entries[runtime.GOOS]
	if entry == "" {
		entry = plugin.Entry
	}
	if entry == "" {
		return ""
	}
	clean, safe := safeRelativePath(entry)
	if !safe {
		return ""
	}
	candidate := filepath.Join(plugin.Path, clean)
	relative, err := filepath.Rel(plugin.Path, candidate)
	if err != nil || relative == ".." || strings.HasPrefix(relative, ".."+string(filepath.Separator)) || filepath.IsAbs(relative) {
		return ""
	}
	return candidate
}

// safeRelativePath accepts a portable relative archive/member path. ZIP
// metadata may use either slash style, so normalize both before joining it to
// an application-owned directory. This rejects Windows drive, UNC and rooted
// paths on every host OS instead of relying on the host's filepath semantics.
func safeRelativePath(value string) (string, bool) {
	normalized := strings.ReplaceAll(strings.TrimSpace(value), "\\", "/")
	if normalized == "" || strings.HasPrefix(normalized, "/") {
		return "", false
	}
	clean := path.Clean(normalized)
	if clean == "." || clean == ".." || strings.HasPrefix(clean, "../") {
		return "", false
	}
	first, _, _ := strings.Cut(clean, "/")
	if strings.Contains(first, ":") {
		return "", false
	}
	return filepath.FromSlash(clean), true
}

func findManifestRoot(root string) (string, error) {
	if _, err := os.Stat(filepath.Join(root, "manifest.json")); err == nil {
		return root, nil
	}
	entries, err := os.ReadDir(root)
	if err != nil {
		return "", err
	}
	for _, entry := range entries {
		if entry.IsDir() {
			candidate := filepath.Join(root, entry.Name())
			if _, err := os.Stat(filepath.Join(candidate, "manifest.json")); err == nil {
				return candidate, nil
			}
		}
	}
	return "", errors.New("压缩包内未找到 manifest.json")
}

func copyDirectory(source, destination string) error {
	return filepath.Walk(source, func(path string, info os.FileInfo, err error) error {
		if err != nil {
			return err
		}
		relative, err := filepath.Rel(source, path)
		if err != nil {
			return err
		}
		target := filepath.Join(destination, relative)
		if info.IsDir() {
			return os.MkdirAll(target, 0o700)
		}
		input, err := os.Open(path)
		if err != nil {
			return err
		}
		output, err := os.OpenFile(target, os.O_CREATE|os.O_TRUNC|os.O_WRONLY, info.Mode().Perm()|0o600)
		if err != nil {
			_ = input.Close()
			return err
		}
		_, copyErr := io.Copy(output, input)
		return errors.Join(copyErr, input.Close(), output.Close())
	})
}
