Haskell (HLS) support

Overview
- This integration uses haskell-language-server (HLS). We prefer the wrapper `haskell-language-server-wrapper` if available.
- Cross-platform behavior mirrors other language servers here: use a PATH-provided HLS (via ghcup) and document setup; optionally download a managed binary later if needed.

Prerequisites
- Install ghcup and HLS per https://www.haskell.org/ghcup/ and https://github.com/haskell/haskell-language-server#installation
- Ensure one of these is on PATH:
  - haskell-language-server-wrapper (preferred)
  - haskell-language-server

Ignored directories
- .stack-work, dist-newstyle, dist, .cabal-store, .hie, .ghc, node_modules

Notes
- Initialize uses standard LSP capabilities similar to other servers.
- First index may take time; timeouts are slightly higher.

CI hints (analogous to Swift/Elixir patterns)
- Use ghcup to install GHC and HLS in CI:
  - curl https://get-ghcup.haskell.org -sSf | sh -s -- -y
  - ghcup install ghc latest && ghcup set ghc latest
  - ghcup install hls latest && ghcup set hls latest
- Add $HOME/.ghcup/bin to PATH.
