# License

Serena is **licensed per component**. The authoritative overview is the
[`LICENSE`](https://github.com/oraios/serena/blob/main/LICENSE) file in the repository,
and the full license texts are in [`LICENSES/`](https://github.com/oraios/serena/tree/main/LICENSES).

| Component | Location | License |
|---|---|---|
| **SolidLSP** – language-server client library, the basis of Serena's free code-intelligence backend | `src/solidlsp`, `test/solidlsp`, `test/resources` | [MIT](https://github.com/oraios/serena/blob/main/LICENSES/MIT.txt) |
| **Serena application** – everything else (agent, tools, MCP server, prompts, scripts, tests, docs) | `src/serena`, `src/interprompt`, `test/serena`, `scripts`, … | [GPL-3.0-or-later](https://github.com/oraios/serena/blob/main/LICENSES/GPL-3.0-or-later.txt) |

Every source file carries an `SPDX-License-Identifier` line stating which license applies to it.

Because MIT is compatible with the GPL, a distribution that combines both — such as the `serena-agent` package —
is **as a whole subject to GPL-3.0-or-later**. This does not change the license of the SolidLSP files themselves:
they remain MIT-licensed and can be extracted and used separately under MIT terms.

## SolidLSP: permissive, reusable infrastructure

SolidLSP is deliberately kept under the permissive MIT license so that it can be reused independently of Serena,
in any project and under any license. Serena's licensing does not affect SolidLSP.

## Serena: an application that stays free

Starting with the **v2 licensing transition**, the Serena application is licensed under the
GNU General Public License, version 3 or (at your option) any later version.

### Why the change?

Serena originally began under the GPL. It was later changed to MIT following community requests.
We have come to consider that change a mistake.

Version 2 introduces substantial architectural and code changes, which made this the appropriate time to reconsider.
The central principle behind the decision is simple:

> **We want the best version of Serena to remain free.**

The GPL ensures that anyone who redistributes a derivative version of Serena must preserve the same software freedoms
for its users that they received themselves.

### The change is not retroactive

* All Serena releases and commits up to the historical cutoff documented in `LICENSE` were released under MIT and
  remain available under MIT.
* Serena v2 and later application code are GPL-3.0-or-later.
* Contributions that entered the application under MIT before the cutoff remain incorporated in the GPL-licensed
  application; the MIT notice continues to apply to that historical code as required by its terms.

## Contributing

Contributions require acceptance of our
[Contributor License Agreement](https://github.com/oraios/serena/blob/main/CLA.md), which lets you keep your
copyright while granting the maintainers the rights needed to maintain and relicense Serena (including under
commercial terms) in the future. Acceptance is a one-time click via the CLA assistant bot on your first pull request.
See [CONTRIBUTING.md](https://github.com/oraios/serena/blob/main/CONTRIBUTING.md) for details.
