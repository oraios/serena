import type { Theme } from './stores/theme.svelte';

/**
 * A single banner entry as returned by the remote manifest.
 * Field names mirror the legacy manifest:
 *   `image`      — light-mode image URL (always present)
 *   `image_dark` — optional dark-mode image URL; falls back to `image`
 *   `link`       — click-through URL
 *   `alt`        — alt text
 */
export interface BannerEntry {
  image: string;
  image_dark?: string;
  link: string;
  alt?: string;
}

/**
 * Top-level manifest shape: banners are keyed by sponsorship tier.
 */
export interface BannerManifest {
  platinum?: BannerEntry[];
  gold?: BannerEntry[];
}

export const BANNER_MANIFEST_URL = 'https://oraios-software.de/serena-banners/manifest.php';

/** Return the banners for the given tier (empty array if the key is missing). */
export function selectBanners(
  manifest: BannerManifest,
  target: 'platinum' | 'gold',
): BannerEntry[] {
  return manifest[target] ?? [];
}

/** Pick the theme-appropriate image, falling back to the light image. */
export function pickVariant(entry: BannerEntry, theme: Theme): string {
  return theme === 'dark' ? (entry.image_dark ?? entry.image) : entry.image;
}

/** Fetch the manifest; resilient — returns an empty manifest on any failure. */
export async function loadManifest(): Promise<BannerManifest> {
  try {
    const res = await fetch(BANNER_MANIFEST_URL);
    if (!res.ok) return {};
    return (await res.json()) as BannerManifest;
  } catch {
    return {};
  }
}
