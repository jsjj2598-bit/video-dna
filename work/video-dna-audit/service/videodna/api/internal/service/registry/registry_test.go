package registry

import (
	"os"
	"path/filepath"
	"runtime"
	"strings"
	"testing"
)

func TestModelAPIKeyNeverPersisted(t *testing.T) {
	root := t.TempDir()
	svc := New(root, filepath.Join(root, "plugins"), 1<<20)
	if _, err := svc.UpsertModel(Model{ID: "custom", Name: "Custom", Kind: "chat", Provider: "custom", BaseURL: "https://example.com/v1", Model: "demo", APIKey: "secret-value"}); err != nil {
		t.Fatal(err)
	}
	payload, err := os.ReadFile(filepath.Join(root, "config.json"))
	if err != nil {
		t.Fatal(err)
	}
	if strings.Contains(string(payload), "secret-value") || strings.Contains(string(payload), "api_key") {
		t.Fatalf("model secret was persisted: %s", payload)
	}
	model, ok, err := svc.GetModel("custom")
	if err != nil || !ok || model.APIKey != "secret-value" {
		t.Fatalf("process-local secret not available: ok=%v err=%v model=%+v", ok, err, model)
	}
}

func TestPluginEntryStaysInsidePluginDirectory(t *testing.T) {
	root := t.TempDir()
	valid := Plugin{Path: root, Entry: "bin/plugin"}
	if got := pluginEntry(valid); got != filepath.Join(root, "bin", "plugin") {
		t.Fatalf("valid entry = %q", got)
	}

	for _, entry := range []string{"../outside", "../../outside", filepath.Join(string(filepath.Separator), "outside"), `..\outside`, `\outside`, `\\server\share\plugin`, `C:\outside`} {
		if got := pluginEntry(Plugin{Path: root, Entry: entry}); got != "" {
			t.Fatalf("unsafe entry %q resolved to %q", entry, got)
		}
	}

	platformEntry := Plugin{Path: root, Entries: map[string]string{runtime.GOOS: "platform/tool"}}
	if got := pluginEntry(platformEntry); got != filepath.Join(root, "platform", "tool") {
		t.Fatalf("platform entry = %q", got)
	}
}
