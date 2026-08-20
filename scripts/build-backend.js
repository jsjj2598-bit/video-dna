#!/usr/bin/env node
'use strict';

const { mkdirSync, rmSync } = require('fs');
const { spawnSync } = require('child_process');
const path = require('path');

const targetOS = process.argv[2] || process.platform;
const targetArch = process.argv[3] || ({ x64: 'amd64', arm64: 'arm64' }[process.arch] || process.arch);
const normalizedOS = targetOS === 'win32' ? 'windows' : targetOS;
const output = path.join('dist', normalizedOS === 'windows' ? 'backend.exe' : 'backend');
const incompatibleOutput = path.join('dist', normalizedOS === 'windows' ? 'backend' : 'backend.exe');

mkdirSync('dist', { recursive: true });
// electron-builder 的 extraResources 会匹配两种后端名称；只保留目标平台文件。
rmSync(incompatibleOutput, { force: true });
const result = spawnSync('go', [
  'build', '-trimpath', '-ldflags=-s -w', '-o', output, './service/videodna/api',
], {
  stdio: 'inherit',
  env: { ...process.env, CGO_ENABLED: '0', GOOS: normalizedOS, GOARCH: targetArch },
});
if (result.error) {
  console.error(`Go build failed: ${result.error.message}`);
  process.exit(1);
}
process.exit(result.status ?? 1);
