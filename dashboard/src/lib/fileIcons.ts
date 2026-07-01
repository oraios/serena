import {
  Folder,
  FolderOpen,
  FileCode,
  Braces,
  FileText,
  Hash,
  Image,
  Database,
  SquareTerminal,
  FileArchive,
  File,
  Package,
  BookOpen,
  GitBranch,
  Container,
  Scale,
  FileCog,
  KeyRound,
  Hammer,
  FileLock,
} from '@lucide/svelte';
import type { Component } from 'svelte';

export interface FileIconMeta {
  icon: Component;
  colorVar: string; // CSS var name, e.g. '--chart-2'
  label: string; // accessible / tooltip label
}

// Extension category definitions.
const CODE: FileIconMeta = { icon: FileCode, colorVar: '--chart-2', label: 'Code' };
const DATA_CONFIG: FileIconMeta = { icon: Braces, colorVar: '--chart-6', label: 'Config' };
const DOCS: FileIconMeta = { icon: FileText, colorVar: '--text-muted', label: 'Document' };
const STYLES: FileIconMeta = { icon: Hash, colorVar: '--chart-5', label: 'Stylesheet' };
const IMAGES: FileIconMeta = { icon: Image, colorVar: '--chart-3', label: 'Image' };
const DATA_FILE: FileIconMeta = { icon: Database, colorVar: '--chart-4', label: 'Data' };
const SHELL: FileIconMeta = { icon: SquareTerminal, colorVar: '--chart-3', label: 'Shell script' };
const ARCHIVE: FileIconMeta = { icon: FileArchive, colorVar: '--text-muted', label: 'Archive' };
const FALLBACK: FileIconMeta = { icon: File, colorVar: '--text-muted', label: 'File' };

// extension (no dot, lowercase) -> category
const EXT_MAP: Record<string, FileIconMeta> = {};
function register(def: FileIconMeta, exts: string[]) {
  for (const e of exts) EXT_MAP[e] = def;
}
register(CODE, [
  'ts',
  'tsx',
  'js',
  'jsx',
  'mjs',
  'cjs',
  'py',
  'rs',
  'go',
  'java',
  'kt',
  'c',
  'h',
  'cpp',
  'hpp',
  'cs',
  'rb',
  'php',
  'swift',
  'svelte',
  'vue',
]);
register(DATA_CONFIG, ['json', 'yaml', 'yml', 'toml', 'ini', 'cfg']);
register(DOCS, ['md', 'markdown', 'txt', 'rst', 'adoc']);
register(STYLES, ['css', 'scss', 'sass', 'less']);
register(IMAGES, ['png', 'jpg', 'jpeg', 'gif', 'svg', 'webp', 'ico', 'bmp']);
register(DATA_FILE, ['sql', 'csv', 'tsv', 'db', 'sqlite', 'parquet']);
register(SHELL, ['sh', 'bash', 'zsh', 'fish', 'ps1', 'bat']);
register(ARCHIVE, ['zip', 'tar', 'gz', 'tgz', 'bz2', 'xz', '7z', 'rar']);

// Special filename rules, matched (case-insensitive) BEFORE the extension map.
interface SpecialRule extends FileIconMeta {
  match: (lowerName: string) => boolean;
}
const SPECIALS: SpecialRule[] = [
  {
    match: (n) => n === 'package.json',
    icon: Package,
    colorVar: '--chart-6',
    label: 'Package manifest',
  },
  {
    match: (n) => n.startsWith('readme'),
    icon: BookOpen,
    colorVar: '--text-muted',
    label: 'Readme',
  },
  {
    match: (n) => n === '.gitignore' || n === '.gitattributes',
    icon: GitBranch,
    colorVar: '--text-muted',
    label: 'Git config',
  },
  {
    match: (n) => n === 'dockerfile' || n.startsWith('docker-compose'),
    icon: Container,
    colorVar: '--chart-2',
    label: 'Docker',
  },
  {
    match: (n) => n.startsWith('license'),
    icon: Scale,
    colorVar: '--text-muted',
    label: 'License',
  },
  {
    match: (n) => n.startsWith('tsconfig') || /\.config\./.test(n),
    icon: FileCog,
    colorVar: '--chart-6',
    label: 'Config',
  },
  {
    match: (n) => n.startsWith('.env'),
    icon: KeyRound,
    colorVar: '--chart-4',
    label: 'Environment',
  },
  { match: (n) => n === 'makefile', icon: Hammer, colorVar: '--text-muted', label: 'Makefile' },
  {
    match: (n) => n.endsWith('.lock') || n.endsWith('-lock.json'),
    icon: FileLock,
    colorVar: '--text-muted',
    label: 'Lock file',
  },
];

export function getFileIconMeta(name: string, kind: 'dir' | 'file', open = false): FileIconMeta {
  if (kind === 'dir') {
    return { icon: open ? FolderOpen : Folder, colorVar: '--accent', label: 'Folder' };
  }
  const lower = name.toLowerCase();
  for (const s of SPECIALS) {
    if (s.match(lower)) return { icon: s.icon, colorVar: s.colorVar, label: s.label };
  }
  const dot = lower.lastIndexOf('.');
  const ext = dot > 0 ? lower.slice(dot + 1) : '';
  return EXT_MAP[ext] ?? FALLBACK;
}
