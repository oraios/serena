---
name: Issue Template
about: General Issue
title: ''
labels: ''
assignees: ''

---

I have:

- [ ] Read the readme and verified that the issue cannot be solved by adjusting configuration
- [ ] Understood that Serena's dashboard can be disabled through the config
- [ ] Understood that by default a client session will start a separate instance of a Serena server. 
- [ ] Understood that for multi-agent setups, the SSE mode should be used.
- [ ] Verified that non-project files are ignored using either gitignore or the corresponding setting in `.serena/project.yml`
- [ ] Have looked for similar issues and discussions, including closed ones
- [ ] Made sure it's an actual issue and not a question - those should be opened as discussion instead.

If you have encountered a real and new issue:

- [ ] I performed `<uv invocation> serena project health-check`
- [ ] I indexed the project as described in the readme
- [ ] Added sufficient explanation of my setup: the MCP client, the OS, the programming language, any config adjustments or relevant project specifics
- [ ] Explained how the issue arose, added instructions on how to reproduce it (if possible)
- [ ] If the issue happens on an open source project, I have added the link
- [ ] Wrote a meaningful title and description
