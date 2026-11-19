def check(name: str, ok: bool, detail: str) -> dict:
    return {"check": name, "pass": bool(ok), "detail": detail}
