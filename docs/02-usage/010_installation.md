# Installation 

## Prerequisites

**Package Manager: uv**

Serena is managed by `uv`.
If you do not have it yet, install it following the instructions [here](https://docs.astral.sh/uv/getting-started/installation/).

**Language-Specific Requirements**

When using the language server backend, some additional dependencies may need to be installed 
to support certain languages.
See the [Language Support](language-servers) page for the list of supported languages.
Many dependencies are installed by Serena on the fly, but if a language requires dependencies 
to be provided manually, this is mentioned in the notes below the respective language.

(install-serena)=
## Installing and Initialising Serena

With `uv` installed and on your PATH, install Serena with this command:

    uv tool install -p 3.13 serena-agent@latest --prerelease=allow

Upon completion, the command `serena` should be available in your terminal.

To test the installation and initialise Serena, run one of the following commands:

  * `serena init`  
    if you intend to use the default language intelligence backend (language servers)
  * `serena init -b JetBrains`  
    if you intend to use the JetBrains backend (which uses the [JetBrains plugin](025_jetbrains_plugin))

Note that you can switch backends at any time via Serena's [configuration](050_configuration). 

## Updating Serena

To update Serena to the latest version, run:

    uv tool upgrade serena-agent --prerelease=allow

:::{tip}
To keep informed about updates, make sure you regularly open [Serena's Dashboard](060_dashboard),
where we will announce releases along with the new features and improvements they bring.
:::

## Uninstalling Serena

Serena can be uninstalled with the following command:

    uv tool uninstall serena-agent
