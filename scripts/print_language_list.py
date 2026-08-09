"""
Prints the list of supported languages, for use in the project.yml template
"""

from solidlsp.ls_config import LanguageServerId

if __name__ == "__main__":
    lang_strings = sorted([l.value for l in LanguageServerId])
    max_len = max(len(s) for s in lang_strings)
    fmt = f"%-{max_len + 2}s"
    for i, l in enumerate(lang_strings):
        if i % 5 == 0:
            print("\n# ", end="")
        print("  " + fmt % l, end="")
