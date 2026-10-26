"use strict";

const os = require("node:os");
const stateRoot = process.env.SERENA_SOLIDITY_STATE_DIR;

if (stateRoot) {
  // env-paths uses os.homedir() on Darwin and does not honor XDG_* variables.
  // Replace only this child process's view of the home directory; Serena's
  // parent environment and the user's HOME remain unchanged.
  os.homedir = () => stateRoot;
}
