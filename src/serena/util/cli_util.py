def ask_yes_no(question: str, default: bool | None = None) -> bool:
    default_prompt = "Y/n" if default else "y/N"

    while True:
        answer = input(f"{question} [{default_prompt}] ").strip().lower()
        if answer == "" and default is not None:
            return default
        if answer in ("y", "yes"):
            return True
        if answer in ("n", "no"):
            return False
        print("Please answer yes/y or no/n.")
