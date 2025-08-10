from langchain_core.tools import tool
import subprocess
import os
import shlex
from utils import log_return


BASE_DIR = r"C:\Users\bratx\Desktop\MisterKnewData"

@tool
@log_return
def run_shell_command(command: str) -> str:
    """
    Executes a shell command strictly within the allowed base directory.

    You may use any shell command (e.g., `mkdir`, `python`, `pip`, `echo`, etc.)
    — IF all paths used are inside BASE_DIR.

    Rules:
    - The command is executed with working directory set to BASE_DIR.
    - If any absolute path points outside BASE_DIR — command is rejected.
    - This includes paths used by commands like `python`, `pip`, `rm`, etc.

    Returns:c
        str: Command output or error.
    """
    try:
        tokens = shlex.split(command)
        path_sensitive_ops = {"rm", "mv", "python", "pip", "curl", "wget", ">", ">>", "|", "&", ";", "shutdown", "format"}

        for token in tokens:
            if os.path.isabs(token):
                norm = os.path.normpath(token)
                if not norm.startswith(os.path.abspath(BASE_DIR)):
                    return f"ERROR: Absolute path '{token}' is outside of {BASE_DIR}"

        for token in tokens:
            if token in path_sensitive_ops or any(op in token for op in path_sensitive_ops):
                for arg in tokens:
                    if not arg.startswith("-") and ("/" in arg or "\\" in arg or arg.endswith(".py")):
                        path = os.path.normpath(os.path.join(BASE_DIR, arg))
                        if not path.startswith(os.path.abspath(BASE_DIR)):
                            return f"ERROR: Operation on path '{arg}' is outside of {BASE_DIR}"

        result = subprocess.run(
            command,
            shell=True,
            cwd=BASE_DIR,
            capture_output=True,
            text=True,
            timeout=10
        )

        if result.returncode == 0:
            return result.stdout.strip() or "(no output)"
        else:
            return f"ERROR:\n{result.stderr.strip()}"

    except Exception as e:
        return f"Execution failed: {str(e)}"


@tool
@log_return
def save_python_code(filename: str, code: str) -> str:
    """
    Saves Python code to a file inside the MisterKnewData directory.

    Only paths inside BASE_DIR are allowed.

    Args:
        filename: Relative path (or name) of the file.
        code: Python code to save.

    Returns:
        Message about the result.
    """
    try:
        # Приводим к безопасному виду
        filename = os.path.normpath(filename)
        if os.path.isabs(filename):
            filename = os.path.basename(filename)  # запрещаем абсолютные пути

        full_path = os.path.abspath(os.path.join(BASE_DIR, filename))

        # Безопасность: файл должен быть строго внутри BASE_DIR
        if not full_path.startswith(os.path.abspath(BASE_DIR)):
            return f"ERROR: Access denied. File path must be inside {BASE_DIR}."

        os.makedirs(os.path.dirname(full_path), exist_ok=True)

        with open(full_path, "w", encoding="utf-8") as f:
            f.write(code)

        return f"Code saved to {full_path}"

    except Exception as e:
        return f"Failed to save file: {str(e)}"
