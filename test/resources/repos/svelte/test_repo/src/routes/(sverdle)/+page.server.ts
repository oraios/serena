import { fail } from "@sveltejs/kit";
import { Game, GAME_VERSION } from "$lib/game.js";

console.log(GAME_VERSION);
import { count } from "$lib/components/Counter.svelte";

export const load = ({ cookies }) => {
  const game = new Game(cookies.get("sverdle"));

  return {
    startingCount: count.current,

    guesses: game.guesses,

    answers: game.answers,

    answer: game.answers.length >= 6 ? game.answer : null,
  };
};

export const actions = {
  update: async ({ request, cookies }) => {
    const game = new Game(cookies.get("sverdle"));

    const data = await request.formData();
    const key = data.get("key");

    const i = game.answers.length;

    if (key === "backspace") {
      game.guesses[i] = game.guesses[i].slice(0, -1);
    } else {
      game.guesses[i] += key;
    }

    cookies.set("sverdle", game.toString(), { path: "/" });
  },

  enter: async ({ request, cookies }) => {
    const game = new Game(cookies.get("sverdle"));

    const data = await request.formData();
    const guess = data.getAll("guess") as string[];

    if (!game.enter(guess)) {
      return fail(400, { badGuess: true });
    }

    cookies.set("sverdle", game.toString(), { path: "/" });
  },

  restart: async ({ cookies }) => {
    cookies.delete("sverdle", { path: "/" });
  },
};
