import { settings } from "./types";
import type { Item } from "./types";
import { Polite } from "./index";

export const item: Item = { id: 1 };
export const port = settings.port;
export const msg = new Polite().greet("x");
