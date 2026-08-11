# This file intentionally references an undefined name so that starpls
# reports an error diagnostic ('"undefined_symbol" is not defined').

def broken():
    return undefined_symbol
