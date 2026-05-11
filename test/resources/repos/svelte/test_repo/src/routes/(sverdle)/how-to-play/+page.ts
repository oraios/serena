import { dev } from "$app/environment";
import { GAME_VERSION } from "$lib/game";

console.log(GAME_VERSION);

export const csr = dev;

export const prerender = true;
