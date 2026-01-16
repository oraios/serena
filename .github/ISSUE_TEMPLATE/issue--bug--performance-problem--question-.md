---
name: Issue (bug, performance problem, etc.)
about: General Issue
title: ''
labels: ''
assignees: ''

---

I have:

- [ ] read the relevant parts of the documentation and verified that the issue cannot be solved by adjusting configuration
- [ ] understood that the Serena Dashboard can be disabled through the config
- [ ] understood that, by default, a client session will start a separate instance of a Serena server. 
- [ ] understood that, for multi-agent setups, the Streamable HTTP/SSE mode should be used.
- [ ] understood that non-project files are ignored using either .gitignore or the corresponding setting in `.serena/project.yml`
- [ ] looked for similar issues and discussions, including closed ones
- [ ] made sure it's an actual issue, not a question (use GitHub Discussions instead).

If you have encountered an actual issue:

- If using language servers (not the JetBrains plugin), 
  - [ ] I performed `<uv invocation> serena project health-check`
  - [ ] I indexed the project as described in the documentation
- [ ] I added sufficient explanation of my setup: the MCP client, the OS, the programming language(s), any config adjustments or relevant project specifics
- [ ] I explained how the issue arose and, where possible, added instructions on how to reproduce it
- [ ] If the issue happens on an open-source project, I have added the link
- [ ] I provided a meaningful title and description
