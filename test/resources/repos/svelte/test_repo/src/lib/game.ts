import { allowed } from "../routes/(sverdle)/words.server.ts";
import { words } from "$lib/components/Words.svelte";

export const GAME_VERSION = "1.0";

export class Game {
  index: number;
  guesses: string[];
  answers: string[];
  answer: string;

  constructor(serialized: string | undefined = undefined) {
    if (serialized) {
      const [index, guesses, answers] = serialized.split("-");

      this.index = +index;
      this.guesses = guesses ? guesses.split(" ") : [];
      this.answers = answers ? answers.split(" ") : [];
    } else {
      this.index = Math.floor(Math.random() * words.length);
      this.guesses = ["", "", "", "", "", ""];
      this.answers = [];
    }

    this.answer = words[this.index];
  }

  enter(letters: string[]) {
    const word = letters.join("");
    const valid = allowed.has(word);

    if (!valid) return false;

    this.guesses[this.answers.length] = word;

    const available = Array.from(this.answer);
    const answer = Array(5).fill("_");

    for (let i = 0; i < 5; i += 1) {
      if (letters[i] === available[i]) {
        answer[i] = "x";
        available[i] = " ";
      }
    }

    for (let i = 0; i < 5; i += 1) {
      if (answer[i] === "_") {
        const index = available.indexOf(letters[i]);
        if (index !== -1) {
          answer[i] = "c";
          available[index] = " ";
        }
      }
    }

    this.answers.push(answer.join(""));

    return true;
  }

  toString() {
    return `${this.index}-${this.guesses.join(" ")}-${this.answers.join(" ")}`;
  }
}
