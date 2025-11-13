# The Project Workflow

Serena uses a project-based workflow.
A **project** is simply a directory on your filesystem that contains code and other files
that you want Serena to work with.

Assuming that you have project you want to work with (which may initially be empty),
setting up a project with Serena typically involves the following steps:

1. **Project creation**: Configuring project settings for Serena (and indexing the project, if desired)
2. **Project activation**: Making Serena aware of the project you want to work with
3. **Onboarding**: Getting Serena familiar with the project (creating memories)
4. **Working on coding tasks**: Using Serena to help you with actual coding tasks in the project

## Project Creation & Indexing

You can create a project either  
 * implicitly, by just activating a directory as a project while already in a conversation; this will use default settings for your project (skip to the next section).
 * explicitly, using the project creation command, or

### Explicit Project Creation

To explicitly create a project, use the following command while in the project directory:

    <serena> project create [options]

For instance, when using `uvx`, run

    uvx --from git+https://github.com/oraios/serena serena project create [options]

 * For an empty project, you will need to specify the programming language
   (e.g., `--language python`). 
 * For an existing project, the main programming language will be detected automatically,
   but you can choose to explicitly specify multiple languages by passing the `--language` parameter
   multiple times (e.g. `--language python --language typescript`).
 * You can optionally specify a custom project name with `--name "My Project"`.
 * You can immediately index the project after creation with `--index`.

After creation, you can adjust the project settings in the generated `.serena/project.yml` file.

(indexing)=
### Indexing

Especially for larger project, it is advisable to index the project after creation (in order to avoid
delays during MCP server startup or the first tool application):

While in the project directory, run this command:
   
    <serena> project index

Indexing has to be called only once. During regular usage, Serena will automatically update the index whenever files change.

## Project Activation
   
Project activation makes Serena aware of the project you want to work with.
You can either choose to do this
 * while in a conversation, by telling the model to activate a project, e.g.,
       
      * "Activate the project /path/to/my_project" (for first-time activation with auto-creation)
      * "Activate the project my_project"
   
   Note that this option requires the `activate_project` tool to be active (which it isn't in context `ide-assistant` where t.        

 * when the MCP server starts, by passing the project path or name as a command-line argument
   (e.g. when working on a fixed project in `ide-assistant` mode): `--project <path|name>`


## Onboarding & Memories

By default, Serena will perform an **onboarding process** when
it is started for the first time for a project.
The goal of the onboarding is for Serena to get familiar with the project
and to store memories, which it can then draw upon in future interactions.
If an LLM should fail to complete the onboarding and does not actually write the
respective memories to disk, you may need to ask it to do so explicitly.

The onboarding will usually read a lot of content from the project, thus filling
up the context. It can therefore be advisable to switch to another conversation
once the onboarding is complete.
After the onboarding, we recommend that you have a quick look at the memories and,
if necessary, edit them or add additional ones.

**Memories** are files stored in `.serena/memories/` in the project directory,
which the agent can choose to read in subsequent interactions.
Feel free to read and adjust them as needed; you can also add new ones manually.
Every file in the `.serena/memories/` directory is a memory file.
Whenever Serena starts working on a project, the list of memories is
provided, and the agent can decide to read them.
We found that memories can significantly improve the user experience with Serena.


## Preparing Your Project

When using Serena to work on your project, it can be helpful to follow a few best practices.

### Structure Your Codebase

Serena uses the code structure for finding, reading and editing code. This means that it will
work well with well-structured code but may perform poorly on fully unstructured one (like a "God class"
with enormous, non-modular functions).

Furthermore, for languages that are not statically typed, the use of type annotations (if supported) 
are highly beneficial.

### Start from a Clean State

It is best to start a code generation task from a clean git state. Not only will
this make it easier for you to inspect the changes, but also the model itself will
have a chance of seeing what it has changed by calling `git diff` and thereby
correct itself or continue working in a followup conversation if needed.

### Use Platform-Native Line Endings

**Important**: since Serena will write to files using the system-native line endings
and it might want to look at the git diff, it is important to
set `git config core.autocrlf` to `true` on Windows.
With `git config core.autocrlf` set to `false` on Windows, you may end up with huge diffs
due to line endings only. 
It is generally a good idea to globally enable this git setting on Windows:

```shell
git config --global core.autocrlf true
```

### Logging, Linting, and Automated Tests

Serena can successfully complete tasks in an _agent loop_, where it iteratively
acquires information, performs actions, and reflects on the results.
However, Serena cannot use a debugger; it must rely on the results of program executions,
linting results, and test results to assess the correctness of its actions.
Therefore, software that is designed to meaningful interpretable outputs (e.g. log messages)
and that has a good test coverage is much easier to work with for Serena.

We generally recommend to start an editing task from a state where all linting checks and tests pass.