import { describe, it, expect } from 'vitest';
import { getFileIconMeta } from '../src/lib/fileIcons';
import {
  Folder,
  FolderOpen,
  FileCode,
  Braces,
  Image,
  File,
  Package,
  FileLock,
  FileCog,
} from '@lucide/svelte';

describe('getFileIconMeta', () => {
  it('returns a closed folder for a collapsed directory', () => {
    const m = getFileIconMeta('src', 'dir', false);
    expect(m.icon).toBe(Folder);
    expect(m.colorVar).toBe('--accent');
    expect(m.label).toBe('Folder');
  });

  it('returns an open folder for an expanded directory', () => {
    expect(getFileIconMeta('src', 'dir', true).icon).toBe(FolderOpen);
  });

  it('maps code extensions to FileCode / --chart-2', () => {
    const m = getFileIconMeta('main.ts', 'file');
    expect(m.icon).toBe(FileCode);
    expect(m.colorVar).toBe('--chart-2');
  });

  it('maps JSON to Braces', () => {
    expect(getFileIconMeta('data.json', 'file').icon).toBe(Braces);
  });

  it('maps images case-insensitively to Image', () => {
    expect(getFileIconMeta('logo.PNG', 'file').icon).toBe(Image);
  });

  it('lets a special filename win over its extension (package.json -> Package)', () => {
    expect(getFileIconMeta('package.json', 'file').icon).toBe(Package);
  });

  it('maps lock files to FileLock', () => {
    expect(getFileIconMeta('package-lock.json', 'file').icon).toBe(FileLock);
    expect(getFileIconMeta('yarn.lock', 'file').icon).toBe(FileLock);
  });

  it('maps *.config.* to FileCog', () => {
    expect(getFileIconMeta('vite.config.ts', 'file').icon).toBe(FileCog);
  });

  it('matches special names case-insensitively', () => {
    expect(getFileIconMeta('README.md', 'file').label).toBe('Readme');
  });

  it('falls back to File / --text-muted for unknown extensions', () => {
    const m = getFileIconMeta('mystery.xyz', 'file');
    expect(m.icon).toBe(File);
    expect(m.colorVar).toBe('--text-muted');
  });
});
