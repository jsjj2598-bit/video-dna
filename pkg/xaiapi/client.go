// Package xaiapi wraps third-party OpenAI-compatible HTTP APIs.
package xaiapi

import (
	"bytes"
	"context"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"os"
	"strings"
	"time"
)

// Model is an OpenAI-compatible endpoint configuration.
type Model struct {
	BaseURL string
	Name    string
	APIKey  string
}

// Message is one chat turn.
type Message struct {
	Role    string `json:"role"`
	Content any    `json:"content"`
}

// Client executes bounded external model requests.
type Client struct {
	httpClient *http.Client
}

// NewClient creates a model client with a request timeout.
func NewClient(timeout time.Duration) *Client {
	if timeout <= 0 {
		timeout = 90 * time.Second
	}
	return &Client{httpClient: &http.Client{Timeout: timeout}}
}

// Chat calls /chat/completions and returns the first text choice.
func (c *Client) Chat(ctx context.Context, model Model, messages []Message, jsonMode bool) (string, error) {
	payload := map[string]any{"model": model.Name, "messages": messages}
	if jsonMode {
		payload["response_format"] = map[string]string{"type": "json_object"}
	}
	return c.complete(ctx, model, payload)
}

// DescribeImage sends one local image with a textual analysis instruction.
func (c *Client) DescribeImage(ctx context.Context, model Model, imagePath, prompt string) (string, error) {
	content, err := os.ReadFile(imagePath)
	if err != nil {
		return "", err
	}
	mimeType := "image/jpeg"
	if strings.EqualFold(strings.TrimPrefix(filepathExt(imagePath), "."), "png") {
		mimeType = "image/png"
	}
	dataURL := "data:" + mimeType + ";base64," + base64.StdEncoding.EncodeToString(content)
	messages := []Message{{
		Role: "user",
		Content: []map[string]any{
			{"type": "text", "text": prompt},
			{"type": "image_url", "image_url": map[string]string{"url": dataURL}},
		},
	}}
	return c.Chat(ctx, model, messages, true)
}

func (c *Client) complete(ctx context.Context, model Model, payload map[string]any) (string, error) {
	if strings.TrimSpace(model.BaseURL) == "" || strings.TrimSpace(model.Name) == "" {
		return "", fmt.Errorf("模型接口地址与模型名不能为空")
	}
	body, err := json.Marshal(payload)
	if err != nil {
		return "", err
	}
	url := strings.TrimRight(model.BaseURL, "/") + "/chat/completions"
	request, err := http.NewRequestWithContext(ctx, http.MethodPost, url, bytes.NewReader(body))
	if err != nil {
		return "", err
	}
	request.Header.Set("Content-Type", "application/json")
	if model.APIKey != "" {
		request.Header.Set("Authorization", "Bearer "+model.APIKey)
	}
	response, err := c.httpClient.Do(request)
	if err != nil {
		return "", err
	}
	defer response.Body.Close()
	responseBody, err := io.ReadAll(io.LimitReader(response.Body, 2*1024*1024))
	if err != nil {
		return "", err
	}
	if response.StatusCode < 200 || response.StatusCode >= 300 {
		return "", fmt.Errorf("模型接口返回 HTTP %d", response.StatusCode)
	}
	var result struct {
		Choices []struct {
			Message struct {
				Content string `json:"content"`
			} `json:"message"`
		} `json:"choices"`
	}
	if err := json.Unmarshal(responseBody, &result); err != nil {
		return "", fmt.Errorf("模型响应格式无效: %w", err)
	}
	if len(result.Choices) == 0 || strings.TrimSpace(result.Choices[0].Message.Content) == "" {
		return "", fmt.Errorf("模型响应缺少文本内容")
	}
	return strings.TrimSpace(result.Choices[0].Message.Content), nil
}

func filepathExt(path string) string {
	index := strings.LastIndexByte(path, '.')
	if index < 0 {
		return ""
	}
	return path[index:]
}
