import os
import re
import sys
import tokenize
from io import BytesIO

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

TEXT_EXTENSIONS = {".py", ".html", ".htm", ".css", ".js"}

EMOJI_PATTERN = re.compile(
    "[\U0001F300-\U0001F5FF]"  # symbols & pictographs
    "|[\U0001F600-\U0001F64F]"  # emoticons
    "|[\U0001F680-\U0001F6FF]"  # transport & map
    "|[\U0001F700-\U0001F77F]"  # alchemical
    "|[\U0001F780-\U0001F7FF]"  # geometric
    "|[\U0001F800-\U0001F8FF]"  # arrows
    "|[\U0001F900-\U0001F9FF]"  # supplemental symbols and pictographs
    "|[\U0001FA00-\U0001FA6F]"  # chess, symbols
    "|[\U0001FA70-\U0001FAFF]"  # symbols
    "|[\u2600-\u26FF]"          # misc symbols
    "|[\u2700-\u27BF]",         # dingbats
    flags=re.UNICODE,
)


def remove_emojis(text: str) -> str:
    return EMOJI_PATTERN.sub("", text)


def strip_python_comments(source: str) -> str:
    try:
        tokens = list(tokenize.tokenize(BytesIO(source.encode("utf-8")).readline))
    except tokenize.TokenError:
        return source

    new_tokens = []
    for tok in tokens:
        if tok.type == tokenize.COMMENT:
            continue
        if tok.type == tokenize.NL:
            continue
        new_tokens.append(tok)

    try:
        new_bytes = tokenize.untokenize(new_tokens)
    except Exception:
        return source

    return new_bytes.decode("utf-8") if isinstance(new_bytes, (bytes, bytearray)) else new_bytes


HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
CSS_JS_BLOCK_COMMENT_RE = re.compile(r"/\*.*?\*/", re.DOTALL)
JS_LINE_COMMENT_RE = re.compile(r"(^|[^:\\])//.*?$", re.MULTILINE)


def strip_web_comments(content: str, ext: str) -> str:
    if ext in {".html", ".htm"}:
        return HTML_COMMENT_RE.sub("", content)

    if ext in {".css", ".js"}:
        content = CSS_JS_BLOCK_COMMENT_RE.sub("", content)
        content = JS_LINE_COMMENT_RE.sub(lambda m: m.group(1), content)
        return content

    return content


def process_file(path: str) -> None:
    _, ext = os.path.splitext(path)
    if ext.lower() not in TEXT_EXTENSIONS:
        return

    try:
        with open(path, "r", encoding="utf-8") as f:
            original = f.read()
    except (UnicodeDecodeError, OSError):
        return

    processed = original

    if ext.lower() == ".py":
        processed = strip_python_comments(processed)
    else:
        processed = strip_web_comments(processed, ext.lower())

    processed = remove_emojis(processed)

    if processed != original:
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write(processed)
        print(f"Limpio: {os.path.relpath(path, BASE_DIR)}")


def walk_and_clean(root: str) -> None:
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d != "__pycache__" and not d.startswith(".")]
        for name in filenames:
            path = os.path.join(dirpath, name)
            if name.endswith(".pyc") or name.endswith(".pyo"):
                continue
            process_file(path)


def main() -> None:
    print("Iniciando limpieza de comentarios y emojis en backend y frontend...")
    for sub in ("backend", "frontend"):
        path = os.path.join(BASE_DIR, sub)
        if os.path.isdir(path):
            print(f"Escaneando: {sub}")
            walk_and_clean(path)
        else:
            print(f"Carpeta no encontrada, se omite: {sub}")
    print("Limpieza completada.")


if __name__ == "__main__":
    main()
