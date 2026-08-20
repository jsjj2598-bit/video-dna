// Command prepare_ffmpeg installs the target FFmpeg tools under dist/tools.
package main

import (
	"compress/gzip"
	"context"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"fmt"
	"io"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"strings"
	"time"
)

const windowsReleaseBase = "https://github.com/eugeneware/ffmpeg-static/releases/download/b6.1.1"

var windowsAssets = []struct {
	name   string
	sha256 string
}{
	{name: "ffmpeg", sha256: "8883a3dffbd0a16cf4ef95206ea05283f78908dbfb118f73c83f4951dcc06d77"},
	{name: "ffprobe", sha256: "f309e6223ad89d2fe54bccd420a7709b66fd27540674e92309578ed491a43c8d"},
}

func main() {
	target := runtime.GOOS
	if len(os.Args) > 1 {
		target = os.Args[1]
	}
	if err := os.MkdirAll(filepath.Join("dist", "tools"), 0o755); err != nil {
		panic(err)
	}
	var err error
	if target == "windows" {
		err = prepareWindows()
	} else if target == runtime.GOOS {
		err = copyHostTools()
	} else {
		err = fmt.Errorf("暂不支持在 %s 上准备 %s FFmpeg，请手动复制到 dist/tools", runtime.GOOS, target)
	}
	if err != nil {
		panic(err)
	}
}

func prepareWindows() error {
	for _, name := range []string{"ffmpeg", "ffprobe"} {
		_ = os.Remove(filepath.Join("dist", "tools", name))
	}
	ctx, cancel := context.WithTimeout(context.Background(), 15*time.Minute)
	defer cancel()
	cacheRoot, err := os.UserCacheDir()
	if err != nil {
		return err
	}
	cacheDir := filepath.Join(cacheRoot, "video-dna-build", "ffmpeg-b6.1.1")
	if err := os.MkdirAll(cacheDir, 0o700); err != nil {
		return err
	}
	for _, asset := range windowsAssets {
		filename := asset.name + "-win32-x64.gz"
		url := windowsReleaseBase + "/" + filename
		cached := filepath.Join(cacheDir, filename)
		if verifyExpected(cached, asset.sha256) != nil {
			fmt.Printf("Downloading %s Windows static binary (cached for later builds)...\n", asset.name)
			temporary := cached + ".tmp"
			_ = os.Remove(temporary)
			if err := downloadTo(ctx, url, temporary); err != nil {
				_ = os.Remove(temporary)
				return err
			}
			if err := verifyExpected(temporary, asset.sha256); err != nil {
				_ = os.Remove(temporary)
				return err
			}
			if err := os.Rename(temporary, cached); err != nil {
				return err
			}
		}
		if err := decompressGzip(cached, filepath.Join("dist", "tools", asset.name+".exe")); err != nil {
			return err
		}
	}
	licensePath := filepath.Join("dist", "tools", "FFMPEG_LICENSE.txt")
	if _, err := os.Stat(licensePath); errors.Is(err, os.ErrNotExist) {
		_ = downloadTo(ctx, windowsReleaseBase+"/win32-x64.LICENSE", licensePath)
	}
	return nil
}

func copyHostTools() error {
	for _, name := range []string{"ffmpeg.exe", "ffprobe.exe", "FFMPEG_LICENSE.txt"} {
		_ = os.Remove(filepath.Join("dist", "tools", name))
	}
	for _, name := range []string{"ffmpeg", "ffprobe"} {
		source := os.Getenv("VIDEODNA_" + strings.ToUpper(name))
		if source == "" {
			var err error
			source, err = exec.LookPath(name)
			if err != nil {
				return fmt.Errorf("未找到 %s: %w", name, err)
			}
		}
		if err := copyFile(source, filepath.Join("dist", "tools", name)); err != nil {
			return err
		}
	}
	return nil
}

func downloadTo(ctx context.Context, url, path string) error {
	request, err := http.NewRequestWithContext(ctx, http.MethodGet, url, nil)
	if err != nil {
		return err
	}
	response, err := http.DefaultClient.Do(request)
	if err != nil {
		return err
	}
	defer response.Body.Close()
	if response.StatusCode != http.StatusOK {
		return fmt.Errorf("下载 %s 失败: HTTP %d", url, response.StatusCode)
	}
	file, err := os.OpenFile(path, os.O_CREATE|os.O_TRUNC|os.O_WRONLY, 0o600)
	if err != nil {
		return err
	}
	if _, err := io.Copy(file, response.Body); err != nil {
		_ = file.Close()
		return err
	}
	return file.Close()
}

func verifyExpected(path, expectedHex string) error {
	expected, err := hex.DecodeString(expectedHex)
	if err != nil || len(expected) != sha256.Size {
		return errors.New("FFmpeg SHA-256 配置无效")
	}
	file, err := os.Open(path)
	if err != nil {
		return err
	}
	defer file.Close()
	hash := sha256.New()
	if _, err := io.Copy(hash, file); err != nil {
		return err
	}
	if !equalBytes(hash.Sum(nil), expected) {
		return errors.New("FFmpeg 下载文件 SHA-256 校验失败")
	}
	return nil
}

func decompressGzip(sourcePath, destination string) error {
	file, err := os.Open(sourcePath)
	if err != nil {
		return err
	}
	defer file.Close()
	reader, err := gzip.NewReader(file)
	if err != nil {
		return err
	}
	defer reader.Close()
	output, err := os.OpenFile(destination, os.O_CREATE|os.O_TRUNC|os.O_WRONLY, 0o755)
	if err != nil {
		return err
	}
	_, copyErr := io.Copy(output, reader)
	return errors.Join(copyErr, output.Close())
}

func copyFile(source, destination string) error {
	input, err := os.Open(source)
	if err != nil {
		return err
	}
	defer input.Close()
	output, err := os.OpenFile(destination, os.O_CREATE|os.O_TRUNC|os.O_WRONLY, 0o755)
	if err != nil {
		return err
	}
	_, copyErr := io.Copy(output, input)
	return errors.Join(copyErr, output.Close())
}

func equalBytes(left, right []byte) bool {
	if len(left) != len(right) {
		return false
	}
	var difference byte
	for index := range left {
		difference |= left[index] ^ right[index]
	}
	return difference == 0
}
