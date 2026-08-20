package registry

import (
	"path/filepath"
	"runtime"
	"testing"
)

func TestPluginEntryStaysInsidePluginDirectory(t *testing.T) {
	root := t.TempDir()
	valid := Plugin{Path: root, Entry: "bin/plugin"}
	if got := pluginEntry(valid); got != filepath.Join(root, "bin", "plugin") {
		t.Fatalf("valid entry = %q", got)
	}

	for _, entry := range []string{"../outside", "../../outside", filepath.Join(string(filepath.Separator), "outside")} {
		if got := pluginEntry(Plugin{Path: root, Entry: entry}); got != "" {
			t.Fatalf("unsafe entry %q resolved to %q", entry, got)
		}
	}

	platformEntry := Plugin{Path: root, Entries: map[string]string{runtime.GOOS: "platform/tool"}}
	if got := pluginEntry(platformEntry); got != filepath.Join(root, "platform", "tool") {
		t.Fatalf("platform entry = %q", got)
	}
}
