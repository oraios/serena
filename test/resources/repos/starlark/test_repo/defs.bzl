"""Shared build definitions for the test repository."""

TOOL_VERSION = "1.2.3"

def format_label(name):
    """Return a root-package label for the given target name."""
    return "//:" + name + "-" + TOOL_VERSION

def gen_files(name, srcs = []):
    """Macro stand-in used from BUILD files; validates and echoes its arguments."""
    labels = []
    for src in srcs:
        labels.append(format_label(src))
    return {"name": name, "labels": labels}
