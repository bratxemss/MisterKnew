

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional, List

# --- Attempt project imports early; fail gracefully with a dialog.
_missing_reason = None
try:
    from ai_agents.advance_ai_agent import AiAgentWorker
    from ai_agents_operator import Operator
    from ai_agents.tools.win_tools import run_shell_command, save_python_code  # noqa: F401 (used by os_worker tool list)
    from ai_agents.tools.web_tools import (
        init_browser_session,
        browser_navigate,
        browser_get_html_by_part,
        browser_use_console,
        browser_get_all_links,
        get_working_links,
        open_link_in_browser,
    )
    from utils.key_getter import extract_and_save_chrome_key
    from utils.db_decoder import extract_cookies_for_playwright
except Exception as e:  # noqa: BLE001
    _missing_reason = str(e)

# --- Tkinter only after dependency probe, so we can show a message box if needed.
import tkinter as tk
import tkinter.messagebox as mbox
from tkinter import filedialog

APP_TITLE = "MisterKnew — Multi-Agent UI"
DATA_DIR = Path(r"C:\Users\bratx\Desktop\MisterKnewData")  # matches your OS agent note
DATA_DIR.mkdir(parents=True, exist_ok=True)
HISTORY_PATH = DATA_DIR / "chat_history.json"

# ----------------------------- Theming --------------------------------- #
class Theme:
    """Centralized theme palette and dimensions."""
    bg = "#0f1216"
    bg_alt = "#131821"
    bg_elev = "#161b25"
    surface = "#1b2230"
    surface_alt = "#20283a"
    accent = "#4cc2ff"
    accent_soft = "#2b8bd1"
    good = "#4ee38d"
    warn = "#ffd166"
    bad = "#ff5c5c"
    text = "#e6edf3"
    text_dim = "#9aa4b2"
    code_bg = "#0b0f14"
    bubble_user = "#213044"
    bubble_bot = "#1f2a3a"
    outline = "#2a3547"
    shadow = "#0a0d12"

    radius = 14
    pad = 10
    gutter = 12


# ----------------------------- Models ---------------------------------- #
@dataclass
class ChatMessage:
    role: str  # "user" | "agent" | "system" | "error"
    content: str
    ts: float


# ----------------------------- Utils ----------------------------------- #
def round_rect(canvas: tk.Canvas, x1, y1, x2, y2, r, **kwargs):
    """Draw a rounded rectangle on a canvas using polygons + arcs."""
    r = min(r, abs(x2 - x1) / 2, abs(y2 - y1) / 2)
    items = []
    # core rect
    items.append(canvas.create_rectangle(x1 + r, y1, x2 - r, y2, **kwargs))
    items.append(canvas.create_rectangle(x1, y1 + r, x2, y2 - r, **kwargs))
    # corners
    items.append(canvas.create_arc(x1, y1, x1 + 2 * r, y1 + 2 * r, start=90, extent=90, style=tk.PIESLICE, **kwargs))
    items.append(canvas.create_arc(x2 - 2 * r, y1, x2, y1 + 2 * r, start=0, extent=90, style=tk.PIESLICE, **kwargs))
    items.append(canvas.create_arc(x1, y2 - 2 * r, x1 + 2 * r, y2, start=180, extent=90, style=tk.PIESLICE, **kwargs))
    items.append(canvas.create_arc(x2 - 2 * r, y2 - 2 * r, x2, y2, start=270, extent=90, style=tk.PIESLICE, **kwargs))
    return items


def ensure_history_file():
    if not HISTORY_PATH.exists():
        with open(HISTORY_PATH, "w", encoding="utf-8") as f:
            json.dump([], f)


def load_history() -> List[ChatMessage]:
    ensure_history_file()
    try:
        with open(HISTORY_PATH, "r", encoding="utf-8") as f:
            raw = json.load(f)
        return [ChatMessage(**m) for m in raw]
    except Exception:
        return []


def save_history(messages: List[ChatMessage]):
    ensure_history_file()
    with open(HISTORY_PATH, "w", encoding="utf-8") as f:
        json.dump([asdict(m) for m in messages], f, ensure_ascii=False, indent=2)


def ts_hhmm(ts: float) -> str:
    return datetime.fromtimestamp(ts).strftime("%H:%M")


def clamp01(x: float) -> float:
    return 0.0 if x < 0 else 1.0 if x > 1 else x


# ----------------------------- Agent Setup ------------------------------ #
SYSTEM_INFO = r"""
Host Name:                     KOMPUKTER
OS Name:                       Майкрософт Windows 11 Pro
OS Version:                    10.0.26100 N/A Build 26100
OS Manufacturer:               Microsoft Corporation
OS Configuration:              Standalone Workstation
OS Build Type:                 Multiprocessor Free
Registered Owner:              bratxems@gmail.com
Registered Organization:       
Product ID:                    00331-10000-00001-AA133
System Manufacturer:           Gigabyte Technology Co., Ltd.
System Model:                  B650 AORUS ELITE AX V2
System Type:                   x64-based PC
Processor(s):                  1 Processor(s) Installed.
                                 [01]: AMD64 Family 25 Model 97 Stepping 2 AuthenticAMD ~4701 Mhz
BIOS Version:                  American Megatrends International, LLC. F32, 05.02.2025
Windows Directory:             C:\Windows
System Directory:              C:\Windows\system32
Boot Device:                   \Device\HarddiskVolume1
System Locale:                 ru;Russian
Input Locale:                  ru;Russian
Time Zone:                     (UTC+02:00) Helsinki, Kyiv, Riga, Sofia, Tallinn, Vilnius
"""

SUPERVISOR_PROMPT = (
    "You are a supervisor agent. Your job is to decompose complex tasks from the user into clear, "
    "executable subtasks which are to be run by other AI agents.\n"
    "You do not perform browser or data extraction actions yourself; you only plan and coordinate. "
    "If a task is simple or only needs your knowledge, answer it yourself.\n\n"

    "AUTOMATIC PLAN EXECUTION:\n"
    "- NEVER ask the user 'Would you like me to proceed?' If the task is well-defined, act directly.\n"
    "- Only ask for clarification if critical information is missing.\n"
    "- On failure (JS error, selector not found, no chat, etc.):\n"
    "  • Do not loop blindly. Analyze the error.\n"
    "  • If selectors are wrong/missing, try to extract and show all chat names for selection.\n"
    "  • Ask only for truly missing info; otherwise adapt and continue.\n\n"

    "AGENT COORDINATION:\n"
    "- Always check available agents via 'get_known_agents' before assigning tasks.\n"
    "- Use 'send_message' to dispatch structured steps to executor agents and expect progress or results.\n\n"

    "TOOLS:\n"
    "- Use 'create_agents_for_work' to spawn new agents if needed.\n"
    "- Use 'get_known_agents' and 'send_message' to coordinate sub-agents.\n\n"

    "COMMUNICATION:\n"
    "- All coordination must be explicit via 'get_known_agents' and 'send_message'.\n"
    "- Inform the user of the plan and provide updates as the executor completes steps.\n"
) + SYSTEM_INFO


def build_agents():
    """Create supervisor + specialized workers, apply prompts, and return (operator, [workers])."""
    # tool sets
    web_tools = [init_browser_session, browser_navigate, browser_get_html_by_part,
                 browser_use_console, browser_get_all_links, get_working_links, open_link_in_browser]
    os_tools = [run_shell_command, save_python_code]

    # workers
    supervisor = AiAgentWorker("MisterKnew", tools=[])
    web_worker = AiAgentWorker("web_worker", tools=web_tools)
    os_worker = AiAgentWorker("os_worker", tools=os_tools)

    # prompts
    supervisor.change_prompt(SUPERVISOR_PROMPT)

    os_worker.change_prompt("""
You are an expert agent in operating systems, scripting, and low-level automation.
- Working directory: "C:\\Users\\bratx\\Desktop\\MisterKnewData"
- Tools:
  • run_shell_command — for shell/terminal operations.
  • save_python_code — to create/update Python scripts.
- On each task:
  1) Break into minimal actionable steps using the available tools.
  2) Choose the optimal order and execute.
  3) If a command fails, analyze, adapt, and retry.
- Respond only to direct instructions from other agents.
- After completion, send a concise report (include errors/output) and call finish.
""")

    web_worker.change_prompt("""
You are an expert in search, data extraction, and browser automation.
- Wait for coordinator instructions; do not initiate messages.
- Prefer Russian-language queries and .ru resources; use English only when needed.
- Use only free resources unless told otherwise.
- If a site requires auth, you log in immediately.
- Tools:
  • get_working_links — main link retrieval tool.
  • open_link_in_browser — open final link for the user.
  • Browser tools (browser_navigate, browser_get_html_by_part, etc.) for scraping/automation.
- For each task:
  1) Analyze requirements and pick the single best, high-quality link (rarely up to two).
  2) Avoid duplicates, irrelevant, paid/promotional sources.
  3) Follow the supervisor's step-by-step plan precisely.
- If no site specified — call get_working_links with Russian params.
- On full completion: call open_link_in_browser, then finish; summarize actions and data retrieved.
""")

    # operator binds agents together
    operator = Operator([supervisor, web_worker, os_worker])
    supervisor.add_tool(operator.make_create_agents_for_work())
    return operator, [supervisor, web_worker, os_worker]


# ----------------------------- UI Widgets ------------------------------ #
class Toast(tk.Toplevel):
    """Floating toast notification with auto-fade."""
    def __init__(self, master, text: str, kind: str = "info", ms: int = 2200):
        super().__init__(master)
        self.attributes("-topmost", True)
        self.overrideredirect(True)
        self.configure(bg=Theme.shadow)

        fg = Theme.text
        bg = Theme.surface
        if kind == "success":
            bg = Theme.bubble_user
            fg = Theme.good
        elif kind == "error":
            bg = Theme.bubble_bot
            fg = Theme.bad

        label = tk.Label(self, text=text, bg=bg, fg=fg, padx=14, pady=8, font=("Segoe UI", 10))
        label.pack()
        self.update_idletasks()
        x = master.winfo_rootx() + master.winfo_width() - self.winfo_width() - 20
        y = master.winfo_rooty() + 20
        self.geometry(f"+{x}+{y}")
        self.after(ms, self.destroy)


class TypingDots(tk.Canvas):
    """Animated typing indicator (...)."""
    def __init__(self, master, **kw):
        super().__init__(master, width=44, height=16, highlightthickness=0, bg=Theme.bubble_bot, **kw)
        self._t = 0.0
        self._running = False
        self.dots = [self.create_oval(6 + i * 12, 6, 14 + i * 12, 14, fill=Theme.text_dim, outline="") for i in range(3)]

    def start(self):
        self._running = True
        self._animate()

    def stop(self):
        self._running = False

    def _animate(self):
        if not self._running:
            return
        self._t += 0.12
        for i, dot in enumerate(self.dots):
            phase = (self._t - i * 0.25) % 1.0
            yoff = int(2 * (1 - abs(2 * phase - 1)))
            self.move(dot, 0, -9999)  # reset
            x1, y1, x2, y2 = self.bbox(dot)
            self.coords(dot, 6 + i * 12, 6 - yoff, 14 + i * 12, 14 - yoff)
        self.after(60, self._animate)


class ChatScroll(tk.Frame):
    """Scroll container with Canvas + inner Frame for chat bubbles."""
    def __init__(self, master):
        super().__init__(master, bg=Theme.bg)
        self.canvas = tk.Canvas(self, bg=Theme.bg, highlightthickness=0)
        self.scrollbar = tk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.inner = tk.Frame(self.canvas, bg=Theme.bg)
        self.inner.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")),
        )
        self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.canvas.configure(yscrollcommand=self.scrollbar.set)

        self.canvas.pack(side="left", fill="both", expand=True)
        self.scrollbar.pack(side="right", fill="y")

    def scroll_to_end(self):
        self.update_idletasks()
        self.canvas.yview_moveto(1.0)


class MessageBubble(tk.Frame):
    """Single chat bubble with timestamp and monospace code highlighting."""
    def __init__(self, master, msg: ChatMessage):
        super().__init__(master, bg=Theme.bg)
        is_user = msg.role == "user"
        is_error = msg.role == "error"
        side = "e" if is_user else "w"
        bubble_bg = Theme.bubble_user if is_user else Theme.bubble_bot
        if is_error:
            bubble_bg = Theme.bubble_bot

        # container for alignment
        container = tk.Frame(self, bg=Theme.bg)
        container.pack(fill="x", padx=12, pady=6)
        inner = tk.Frame(container, bg=bubble_bg)
        # rounded illusion with padding
        inner.pack(side=("right" if is_user else "left"), padx=(60, 6) if is_user else (6, 60))

        # header: icon + time
        head = tk.Frame(inner, bg=bubble_bg)
        head.pack(fill="x", padx=12, pady=(8, 0))
        role_txt = "Вы" if is_user else ("Агент" if not is_error else "Ошибка")
        fg_role = Theme.text if not is_error else Theme.bad
        tk.Label(head, text=role_txt, bg=bubble_bg, fg=fg_role, font=("Segoe UI Semibold", 9)).pack(side="left")
        tk.Label(head, text=ts_hhmm(msg.ts), bg=bubble_bg, fg=Theme.text_dim, font=("Segoe UI", 8)).pack(side="right")

        # body with basic formatting: code blocks (```), inline code (`..`)
        body = tk.Text(inner, bg=bubble_bg, fg=Theme.text, font=("Cascadia Code", 10),
                       relief="flat", padx=12, pady=8, height=1, wrap="word", cursor="arrow")
        body.insert("1.0", msg.content)
        body.configure(state="disabled")
        body.pack(fill="both", expand=True)

        # Style code blocks (simple heuristic)
        self._style_code(body, bubble_bg)

        # subtle entrance animation (slide-up)
        self.after(0, lambda: self._slide_in(inner))

    def _slide_in(self, widget, dy: int = 14, steps: int = 8):
        # Simple translate effect
        x = widget.winfo_x()
        y = widget.winfo_y()
        def step(i=0):
            if i >= steps:
                return
            widget.place_configure(x=x, y=y + (dy - int(dy * (i + 1) / steps)))
            widget.after(12, step, i + 1)
        widget.place(x=x, y=y + dy)
        step()

    def _style_code(self, text: tk.Text, bg_color: str):
        # Inline code: `code`
        text.tag_configure("inline", background=Theme.code_bg, foreground=Theme.accent, relief="flat")
        content = text.get("1.0", "end-1c")
        # Simple parsing — not full Markdown; sufficient for code blocks and inline ticks.
        # Code blocks: ```...\n```
        idx = 0
        while True:
            a = content.find("```", idx)
            if a == -1:
                break
            b = content.find("```", a + 3)
            if b == -1:
                break
            start = f"1.0+{a}c"
            end = f"1.0+{b+3}c"
            text.tag_add("codeblock", start, end)
            idx = b + 3
        text.tag_configure("codeblock", background=Theme.code_bg, foreground=Theme.text, lmargin1=16, lmargin2=16)

        # Inline code
        idx = 0
        toggle = False
        while True:
            p = content.find("`", idx)
            if p == -1:
                break
            idx = p + 1
            q = content.find("`", idx)
            if q == -1:
                break
            text.tag_add("inline", f"1.0+{p}c", f"1.0+{q+1}c")
            idx = q + 1


# ----------------------------- Main Application ------------------------ #
class App:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title(APP_TITLE)
        self.root.configure(bg=Theme.bg)
        self.root.geometry("1080x700")
        self.root.minsize(980, 600)

        if _missing_reason:
            mbox.showerror("Импорт не удался",
                           f"Не удалось загрузить зависимости проекта:\n{_missing_reason}\n\n"
                           f"Убедись, что виртуальное окружение активно и пакеты установлены.")
            self.root.destroy()
            sys.exit(1)

        # Async state
        self.loop = asyncio.get_event_loop()
        self.current_task: Optional[asyncio.Task] = None
        self.running = True

        # Agent state
        self.operator = None
        self.supervisor: Optional[AiAgentWorker] = None
        self.web_worker: Optional[AiAgentWorker] = None
        self.os_worker: Optional[AiAgentWorker] = None

        # History
        self.messages: List[ChatMessage] = load_history()

        # UI build
        self._build_ui()

        # Start async bootstrap
        self.loop.create_task(self._bootstrap())

        # Drive both tkinter & asyncio in one thread
        self.loop.create_task(self._tk_pump())

    # ------------------ UI Composition ------------------ #
    def _build_ui(self):
        # Header
        header = tk.Frame(self.root, bg=Theme.bg_alt)
        header.pack(fill="x", side="top")
        self._build_header(header)

        # Body: Sidebar + Chat + Right panel
        body = tk.Frame(self.root, bg=Theme.bg)
        body.pack(fill="both", expand=True)

        self.sidebar = tk.Frame(body, width=240, bg=Theme.bg_alt)
        self.sidebar.pack(side="left", fill="y")
        self._build_sidebar(self.sidebar)

        # Chat area
        center = tk.Frame(body, bg=Theme.bg)
        center.pack(side="left", fill="both", expand=True)
        self.chat = ChatScroll(center)
        self.chat.pack(fill="both", expand=True)

        # Input area
        input_bar = tk.Frame(center, bg=Theme.bg)
        input_bar.pack(fill="x")
        self._build_input(input_bar)

        # Render previous history
        for m in self.messages:
            self._append_message(m)

        self._status("Готово.")

    def _build_header(self, parent: tk.Frame):
        # Title + actions
        title = tk.Label(parent, text="🤖 MisterKnew · мультиагентная панель",
                         bg=Theme.bg_alt, fg=Theme.text, font=("Segoe UI Semibold", 12))
        title.pack(side="left", padx=12, pady=8)

        self.preflight_label = tk.Label(parent, text="Подготовка окружения…", bg=Theme.bg_alt,
                                        fg=Theme.text_dim, font=("Segoe UI", 9))
        self.preflight_label.pack(side="left", padx=12)

        spacer = tk.Frame(parent, bg=Theme.bg_alt)
        spacer.pack(side="left", expand=True, fill="x")

        export_btn = tk.Button(parent, text="Экспорт .md", command=self._export_md,
                               bg=Theme.surface, fg=Theme.text, activebackground=Theme.surface_alt,
                               relief="flat", padx=10, pady=4)
        export_btn.pack(side="right", padx=8, pady=6)

        clear_btn = tk.Button(parent, text="Очистить", command=self._clear_chat,
                              bg=Theme.surface, fg=Theme.text, activebackground=Theme.surface_alt,
                              relief="flat", padx=10, pady=4)
        clear_btn.pack(side="right", padx=8, pady=6)

    def _build_sidebar(self, parent: tk.Frame):
        tk.Label(parent, text="Агенты", bg=Theme.bg_alt, fg=Theme.text_dim,
                 font=("Segoe UI Semibold", 10)).pack(anchor="w", padx=12, pady=(12, 6))

        self.agent_list = tk.Listbox(parent, bg=Theme.surface, fg=Theme.text, bd=0,
                                     highlightthickness=0, activestyle="none",
                                     selectbackground=Theme.accent_soft, selectforeground=Theme.text)
        self.agent_list.pack(fill="x", padx=12)
        for name in ["MisterKnew (supervisor)", "web_worker", "os_worker"]:
            self.agent_list.insert("end", name)
        self.agent_list.selection_set(0)

        sep = tk.Frame(parent, height=1, bg=Theme.outline)
        sep.pack(fill="x", padx=12, pady=12)

        tk.Label(parent, text="Быстрые действия", bg=Theme.bg_alt, fg=Theme.text_dim,
                 font=("Segoe UI Semibold", 10)).pack(anchor="w", padx=12)

        btn1 = tk.Button(parent, text="Открыть итоговую ссылку", command=self._open_last_link,
                         bg=Theme.surface, fg=Theme.text, relief="flat")
        btn1.pack(fill="x", padx=12, pady=(8, 4))

        btn2 = tk.Button(parent, text="Папка данных", command=lambda: os.startfile(DATA_DIR),
                         bg=Theme.surface, fg=Theme.text, relief="flat")
        btn2.pack(fill="x", padx=12, pady=4)

        self.status_label = tk.Label(parent, text="Статус: —", bg=Theme.bg_alt, fg=Theme.text_dim,
                                     font=("Segoe UI", 9), justify="left", wraplength=220)
        self.status_label.pack(anchor="w", padx=12, pady=12)

    def _build_input(self, parent: tk.Frame):
        self.entry = tk.Text(parent, height=3, bg=Theme.surface, fg=Theme.text,
                             insertbackground=Theme.text, wrap="word",
                             font=("Segoe UI", 11), relief="flat", padx=10, pady=10)
        self.entry.pack(side="left", fill="x", expand=True, padx=(12, 6), pady=10)

        btn_send = tk.Button(parent, text="Отправить (Ctrl+Enter)", command=self._send_clicked,
                             bg=Theme.accent_soft, fg="white", relief="flat", padx=14, pady=8)
        btn_send.pack(side="left", padx=(6, 6), pady=10)

        self.btn_stop = tk.Button(parent, text="Стоп", command=self._stop_clicked,
                                  bg=Theme.surface, fg=Theme.bad, relief="flat", padx=14, pady=8, state="disabled")
        self.btn_stop.pack(side="left", padx=(0, 12), pady=10)

        self.entry.bind("<Control-Return>", lambda e: (self._send_clicked(), "break"))
        self.entry.bind("<Escape>", lambda e: (self.entry.delete("1.0", "end"), "break"))

        self.typing = TypingDots(parent)
        self.typing.pack_forget()  # attach later in flow

    # ------------------ Actions ------------------ #
    def _status(self, text: str):
        self.status_label.configure(text=f"Статус: {text}")

    def _append_message(self, msg: ChatMessage):
        bubble = MessageBubble(self.chat.inner, msg)
        bubble.pack(fill="x")
        self.chat.scroll_to_end()

    def _add_user_message(self, content: str):
        msg = ChatMessage("user", content, time.time())
        self.messages.append(msg)
        self._append_message(msg)
        save_history(self.messages)

    def _add_agent_message(self, content: str):
        msg = ChatMessage("agent", content, time.time())
        self.messages.append(msg)
        self._append_message(msg)
        save_history(self.messages)

    def _add_error_message(self, content: str):
        msg = ChatMessage("error", content, time.time())
        self.messages.append(msg)
        self._append_message(msg)
        save_history(self.messages)

    def _export_md(self):
        if not self.messages:
            Toast(self.root, "Нет сообщений для экспорта", "error")
            return
        path = filedialog.asksaveasfilename(defaultextension=".md", filetypes=[("Markdown", "*.md")])
        if not path:
            return
        with open(path, "w", encoding="utf-8") as f:
            f.write(f"# {APP_TITLE}\n\n")
            for m in self.messages:
                stamp = datetime.fromtimestamp(m.ts).isoformat(sep=" ", timespec="minutes")
                role = {"user": "Вы", "agent": "Агент", "error": "Ошибка"}.get(m.role, m.role)
                f.write(f"**{role}** [{stamp}]\n\n{m.content}\n\n---\n\n")
        Toast(self.root, "Экспортировано", "success")

    def _clear_chat(self):
        if not mbox.askyesno("Подтверждение", "Очистить историю чата? Это действие необратимо."):
            return
        self.messages.clear()
        save_history(self.messages)
        for w in list(self.chat.inner.children.values()):
            w.destroy()
        Toast(self.root, "История очищена", "success")

    def _open_last_link(self):
        # This button is a convenience: your web_worker usually calls open_link_in_browser itself.
        # We leave it here as a placeholder hook if you later persist a 'last_link.txt' in DATA_DIR.
        path = DATA_DIR / "last_link.txt"
        if path.exists():
            url = path.read_text(encoding="utf-8").strip()
            try:
                os.startfile(url)
                Toast(self.root, "Открываю ссылку…", "success")
            except Exception as e:  # noqa: BLE001
                self._add_error_message(f"Не удалось открыть ссылку: {e}")
        else:
            Toast(self.root, "Ссылка не найдена", "error")

    def _send_clicked(self):
        if self.current_task and not self.current_task.done():
            Toast(self.root, "Дождитесь завершения текущего запроса или нажмите Стоп", "error")
            return
        content = self.entry.get("1.0", "end").strip()
        if not content:
            return
        self.entry.delete("1.0", "end")
        self._add_user_message(content)
        self.btn_stop.configure(state="normal")
        self.typing.pack(side="left", padx=(0, 8))
        self.typing.start()
        self._status("Агент обрабатывает запрос…")

        self.current_task = self.loop.create_task(self._ask_supervisor(content))

    def _stop_clicked(self):
        if self.current_task and not self.current_task.done():
            self.current_task.cancel()
            self._status("Отмена…")
            self.btn_stop.configure(state="disabled")

    # ------------------ Async Tasks ------------------ #
    async def _bootstrap(self):
        """Activate agents and run preflight (Chrome key + cookies) without blocking UI."""
        try:
            self._status("Инициализация агентов…")
            operator, workers = build_agents()
            self.operator = operator
            self.supervisor, self.web_worker, self.os_worker = workers
            await self.operator.activate_all()

            self.preflight_label.configure(text="Получение ключа и cookies…")
            # Run preflight in thread (may do IO)
            await asyncio.to_thread(extract_and_save_chrome_key)
            await asyncio.to_thread(extract_cookies_for_playwright)

            self.preflight_label.configure(text="Окружение готово ✓")
            self._status("Готово.")
            Toast(self.root, "Инициализация завершена", "success")
        except Exception as e:  # noqa: BLE001
            self._status("Ошибка инициализации")
            self._add_error_message(f"Bootstrap error: {e}")
            Toast(self.root, "Ошибка инициализации", "error")

    async def _ask_supervisor(self, text: str):
        """Send a user query to the supervisor and stream back the final message."""
        try:
            # Directly ask the supervisor; it orchestrates subagents.
            # silent=True to avoid extra noise, but your worker should still return textual report.
            resp: str = await self.supervisor.ainvoke(text, silent=True)  # type: ignore[union-attr]
            self._add_agent_message(resp)
            if "[FINISHED]" in resp.upper():
                Toast(self.root, "Задача завершена", "success")
                self._status("Агент сообщил о завершении задачи.")
            else:
                self._status("Готово.")
        except asyncio.CancelledError:
            self._add_error_message("Операция отменена пользователем.")
            self._status("Отменено.")
        except Exception as e:  # noqa: BLE001
            self._add_error_message(f"Ошибка во время выполнения: {e}")
            self._status("Ошибка.")
        finally:
            self.btn_stop.configure(state="disabled")
            self.typing.stop()
            self.typing.pack_forget()

    async def _tk_pump(self):
        """Drive tkinter and asyncio together."""
        while self.running:
            try:
                self.root.update()
            except tk.TclError:
                # Window closed
                self.running = False
                break
            await asyncio.sleep(0.01)


# ----------------------------- Entrypoint ------------------------------- #
def main():
    # Prefer running in an asyncio event loop
    try:
        app = App()
        loop = asyncio.get_event_loop()
        loop.run_forever()
    except KeyboardInterrupt:
        pass
    finally:
        try:
            asyncio.get_event_loop().stop()
        except Exception:
            pass


if __name__ == "__main__":
    main()
