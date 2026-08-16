import ast
import logging
import os
import re
from pathlib import Path
from typing import Optional, List

from sensai.util.string import TextBuilder

log = logging.getLogger(os.path.basename(__file__))

TOP_LEVEL_PACKAGE = "serena"
PROJECT_NAME = "Serena"

def module_template(module_qualname: str):
    title = module_qualname.replace("_", r"\_")
    return f"""{title}
{"=" * len(title)}

.. automodule:: {module_qualname}
   :members:
   :show-inheritance:
"""


def _module_is_documented(py_path) -> bool:
    """
    :param py_path: path to a Python module
    :return: whether the module carries any documentation worth publishing: a module docstring, or at
        least one public class or function with a docstring. Modules without either would render as a
        bare list of names, which communicates nothing; their pages are omitted entirely.
    """
    try:
        tree = ast.parse(Path(py_path).read_text(encoding="utf-8"))
    except (OSError, SyntaxError):
        return False
    if ast.get_docstring(tree):
        return True
    # top-level objects only, mirroring what autodoc renders: without :undoc-members:, an
    # undocumented class is skipped entirely, so docstrings on its methods cannot save the page
    for node in tree.body:
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and not node.name.startswith("_"):
            if ast.get_docstring(node):
                return True
    return False


def _module_summary(py_path) -> str:
    """
    :param py_path: path to a Python module
    :return: a one-line summary for navigation pages: the first line of the module docstring, or,
        where none exists, the names of the documented top-level objects the page will contain
    """
    try:
        tree = ast.parse(Path(py_path).read_text(encoding="utf-8"))
    except (OSError, SyntaxError):
        return ""
    doc = ast.get_docstring(tree)
    if doc:
        return doc.strip().split("\n")[0].strip()
    names = [
        node.name
        for node in tree.body
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
        and not node.name.startswith("_")
        and ast.get_docstring(node)
    ]
    if not names:
        return ""
    shown = ", ".join(f"``{n}``" for n in names[:4])
    return f"Defines {shown}" + (", …" if len(names) > 4 else "")


def _package_summary(dir_path) -> str:
    """
    :param dir_path: path to a package directory
    :return: a one-line summary: the package docstring's first line, or the names of its documented
        modules
    """
    init = Path(dir_path) / "__init__.py"
    if init.exists():
        doc = ast.get_docstring(ast.parse(init.read_text(encoding="utf-8")))
        if doc:
            return doc.strip().split("\n")[0].strip()
    modules = sorted(
        p.stem
        for p in Path(dir_path).glob("*.py")
        if not p.name.startswith("_") and _module_is_documented(p)
    )
    if not modules:
        return ""
    shown = ", ".join(f"``{m}``" for m in modules[:4])
    return f"Modules: {shown}" + (", …" if len(modules) > 4 else "")


def _package_is_documented(dir_path) -> bool:
    """
    :param dir_path: path to a package directory
    :return: whether any module beneath it (recursively) is documented; undocumented packages get no
        index page and no reference from their parent
    """
    return any(
        _module_is_documented(p)
        for p in Path(dir_path).rglob("*.py")
        if not p.name.startswith("_")
    )


def index_template(package_name: str, doc_references=None, text_prefix=""):
    lines = []
    for ref, summary in doc_references or []:
        lines.append(f"* :doc:`{ref}`" + (f" -- {summary}" if summary else ""))
    body = ("\n" + "\n".join(lines) + "\n") if lines else ""

    dirname = package_name.split(".")[-1]
    title = dirname.replace("_", r"\_")
    return f"{title}\n{'=' * len(title)}" + text_prefix + body


def write_to_file(content: str, path: str):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(content)
    os.chmod(path, 0o666)


def make_rst(src_root, rst_root, clean=False, overwrite=False, package_prefix=""):
    """Creates/updates documentation in form of rst files for modules and packages.

    The package tree is mirrored directly into ``rst_root``: a page per documented module, an index page
    per documented subpackage. The top-level package itself gets no index page — the section's
    hand-written intro is the landing page, and the navigation carries the listing. (Keeping the tree
    one level flatter also keeps every module page within the theme's sidebar depth, which renders
    four levels.)

    Without ``clean``, does not delete any existing rst files. Thus, rst files for packages or modules
    that have been removed or renamed should be deleted by hand.

    This method should be executed from the project's top-level directory

    :param src_root: path to library base directory, typically "src/<library_name>"
    :param rst_root: path to the root directory to which .rst files will be written
    :param clean: whether to remove all .rst files beneath the target directory beforehand (pages that are
        not generated — the hand-written intro — are left in place)
    :param overwrite: whether to overwrite existing rst files. This should be used with caution as it will delete
        all manual changes to documentation files
    :package_prefix: a prefix to prepend to each module (for the case where the src_root is not the base package),
        which, if not empty, should end with a "."
    :return:
    """
    rst_root = os.path.abspath(rst_root)

    if clean and os.path.isdir(rst_root):
        # the target directory also holds hand-written pages (the section intro), so cleaning
        # removes only what this generator produces: the .rst tree, and any directory it empties
        for rst_path in Path(rst_root).rglob("*.rst"):
            rst_path.unlink()
        for dir_path in sorted((p for p in Path(rst_root).rglob("*") if p.is_dir()), reverse=True):
            if not any(dir_path.iterdir()):
                dir_path.rmdir()

    for root, dirnames, filenames in os.walk(src_root):
        if os.path.basename(root).startswith("_"):
            continue
        base_package_relpath = os.path.relpath(root, start=src_root)
        base_package_qualname = package_prefix + os.path.relpath(
            root,
            start=os.path.dirname(src_root),
        ).replace(os.path.sep, ".")

        for dirname in dirnames:
            if dirname.startswith("_"):
                log.debug(f"Skipping {dirname}")
                continue
            if not _package_is_documented(os.path.join(root, dirname)):
                log.info(f"Skipping undocumented package {dirname}")
                continue
            files_in_dir = os.listdir(os.path.join(root, dirname))
            module_names = [
                (f[:-3], _module_summary(os.path.join(root, dirname, f)))
                for f in sorted(files_in_dir)
                if f.endswith(".py") and not f.startswith("_") and _module_is_documented(os.path.join(root, dirname, f))
            ]
            subdir_refs = [
                (f"{f}/index", _package_summary(os.path.join(root, dirname, f)))
                for f in sorted(files_in_dir)
                if os.path.isdir(os.path.join(root, dirname, f))
                and not f.startswith("_")
                and _package_is_documented(os.path.join(root, dirname, f))
            ]
            package_qualname = f"{base_package_qualname}.{dirname}"
            package_index_rst_path = os.path.join(
                rst_root,
                base_package_relpath,
                dirname,
                "index.rst",
            )
            log.info(f"Writing {package_index_rst_path}")
            write_to_file(
                index_template(package_qualname, doc_references=module_names + subdir_refs),
                package_index_rst_path,
            )

        for filename in filenames:
            base_name, ext = os.path.splitext(filename)
            if ext == ".py" and not filename.startswith("_"):
                if not _module_is_documented(os.path.join(root, filename)):
                    log.info(f"Skipping undocumented module {filename}")
                    continue
                module_qualname = f"{base_package_qualname}.{filename[:-3]}"

                module_rst_path = os.path.join(rst_root, base_package_relpath, f"{base_name}.rst")
                if os.path.exists(module_rst_path) and not overwrite:
                    log.debug(f"{module_rst_path} already exists, skipping it")
                    continue

                log.info(f"Writing module documentation to {module_rst_path}")
                write_to_file(module_template(module_qualname), module_rst_path)


def autogen_tool_list(target_filename = "01-about/035_tools.md"):
    from serena.tools import ToolRegistry

    target_file = Path(__file__).parent / target_filename
    with open(target_file, "w") as f:
        f.write("<!-- This file is auto-generated by docs/autogen_docs.py. Do not edit it manually. -->\n\n")
        f.write("# Tools\n\n")
        f.write("Find the full list of Serena's tools below.\n\n")
        f.write("Note that in most configurations, only a subset of these tools will be enabled simultaneously.\n")
        f.write("Tools marked as *optional* are disabled by default.\n\n")
        f.write("Tools marked as [BETA] were recently introduced and may not be fully robust yet.\n\n")
        tools_by_module = ToolRegistry().get_registered_tools_by_module()
        priority_modules = {"serena.tools.symbol_tools": 1, "serena.tools.jetbrains_tools": 2}

        text = TextBuilder()
        sorted_modules = sorted(tools_by_module.keys(), key=lambda m: (priority_modules.get(m, 3), m))
        for module in sorted_modules:
            tools = tools_by_module[module]
            module = module.replace("serena.tools.", "")
            text.with_line(f"* **{module}**")
            for tool in tools:
                info = ""
                if tool.is_optional:
                    info += " *(optional)*"
                if tool.is_beta:
                    info += " [BETA]"
                text.with_line(f"* `{tool.tool_name}`{info}: {tool.class_docstring}", indent=2)
        f.write(text.build())


def autogen_about_intro_features():
    readme_path = Path(__file__).parent.parent / "README.md"
    with open(readme_path, "r", encoding="utf-8") as f:
        readme_contents = f.read()

    match = re.search(r"<h3.*?>(.*?)</h3>(.*?)^## Programming.*?^(## Features.*?)^## ", readme_contents, re.DOTALL | re.MULTILINE)
    assert match, f"Failed to extract about texts from README.md. {__file__} probably needs to be updated."

    tagline = match.group(1).strip()
    about_text = match.group(2).strip()
    features_text = match.group(3).strip()

    autogen_info = f"<!-- This section is auto-generated by {__file__} from the root README.md; do not edit. -->\n\n"

    with open(Path(__file__).parent / "01-about" / "000_intro.md", "w", encoding="utf-8") as f:
        f.write(autogen_info)
        f.write("# About Serena\n\n")
        f.write(f"**{tagline}**\n\n")

        # adjust link
        about_text = about_text.replace("resources/serena-block-diagram.svg", "https://raw.githubusercontent.com/oraios/serena/main/resources/serena-block-diagram.svg")

        # remove centred links
        about_text = re.subn(r'^<div align="center">.*?</div>\s*<br>$', "", about_text, flags=re.MULTILINE | re.DOTALL)[0]

        # remove statements with links to quick start guide
        about_text = re.subn(r"^.*\[Quick Start.*?$", r"", about_text, flags=re.MULTILINE)[0]

        # remove callouts
        about_text = re.subn(r"^> \[!\w+\]\s+(^>.*?$)+", "", about_text, flags=re.MULTILINE)[0]

        # replace "Quick Demo" with "Video Introduction", removing the short video
        about_text = about_text.replace("# Quick Demo", "# Video Introduction")
        about_text = re.subn(r"^https://github.com/user-attachments/.*?$", "", about_text, flags=re.MULTILINE)[0]
        about_text = about_text.replace(":tv: Longer video:", "Watch our video:")

        # remove emojis (e.g. :tv:)
        about_text = re.subn(r":\w+:\s+", "", about_text)[0]


        f.write(f"{about_text}\n\n")

        # a fast path to the most-welcomed contribution, placed by the generator so it
        # survives regeneration of this page from the README
        f.write(
            "```{admonition} Want your language supported?\n"
            ":class: tip\n"
            "A new language server is the contribution Serena is built to receive — no issue\n"
            "required, and the path is mapped end to end in\n"
            "[Adding Language Support](../06-contributing/030_adding-a-language).\n"
            "```\n\n"
        )

    jetbrains_marketplace_link = ('```{raw} html\n'
        '<p><a href="https://plugins.jetbrains.com/plugin/28946-serena/">'
        '<img style="background-color:transparent;" src="../_static/images/jetbrains-marketplace-button.png">'
        '</a></p>\n```')

    with open(Path(__file__).parent / "01-about" / "025_features.md", "w", encoding="utf-8") as f:
        f.write(autogen_info)
        features_text = re.subn(r"^#", r"", features_text, flags=re.MULTILINE)[0]
        features_text = re.subn(r"</?details>", "", features_text, flags=re.MULTILINE)[0]
        features_text = re.subn(r"<summary>.*?</summary>", "", features_text, flags=re.MULTILINE)[0]
        features_text = re.sub(r'<a href="https://plugins.jetbrains.com.*?</a>', jetbrains_marketplace_link, features_text, flags=re.DOTALL)
        f.write(f"{features_text}\n\n")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    docs_root = Path(__file__).parent

    autogen_about_intro_features()

    autogen_tool_list()

    make_rst(
        docs_root / ".." / "src" / "serena",
        docs_root / "06-contributing" / "code-reference",
        clean=True,
    )
