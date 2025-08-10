import asyncio
from playwright.async_api import async_playwright
import json

with open("ai_agents\\tools\\web_tools\\playwright_cookies.json", encoding="utf-8") as f:
    chrome_cookies = json.load(f)

class PlaywrightSessionAsync:
    def __init__(self, headless: bool = True):
        self.headless = headless
        self.playwright = None
        self.browser = None
        self.page = None
        self.headers = {
            'Accept': '*/*',
            'Connection': 'keep-alive',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36'
        }
        self.context = None
        self.cookies = chrome_cookies or []
        self.console_messages = []

    async def __aenter__(self):
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(headless=self.headless,
                                                             args=[
                                                                 "--disable-blink-features=AutomationControlled",
                                                                 "--window-size=1920,1080"
                                                             ]
                                                             )
        self.context = await self.browser.new_context(
            user_agent=self.headers["User-Agent"],
            viewport={"width": 1280, "height": 800}
        )
        if self.cookies:
            await self.context.add_cookies(self.cookies)
        self.page = await self.context.new_page()
        self.page.on("console", self._handle_console_msg)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.context:
            await self.context.close()
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()

    def _handle_console_msg(self, msg):
        self.console_messages.append(f"[{msg.type}] {msg.text}")

    async def goto_page(self, url: str):
        if self.page is None:
            raise RuntimeError("Page is not initialized")
        await self.page.goto(url)
        await asyncio.sleep(2)

    async def get_html(self) -> str:
        return await self.page.content()

    async def get_all_links(self) -> list[str]:
        links = await self.page.eval_on_selector_all("a", "elements => elements.map(e => e.href)")
        return links

    async def eval_console(self, code: str) -> str:
        self.console_messages.clear()

        wrapped_code = f"""
            try {{
                {code}
            }} catch (e) {{
                console.error("JS Error:", e.message);
            }}
        """
        await self.page.evaluate(wrapped_code)

        await asyncio.sleep(1)

        return "Console output:\n" + "\n".join(self.console_messages) if self.console_messages else "Console output: (no messages)"

    async def get_visible_text_elements(self) -> list[dict]:
        """
        Returns a list of dictionaries with info about all visible elements
        that have direct non-empty text nodes (not inherited from children).
        Each dict contains: type, class, id, value.
        """
        elements = await self.page.evaluate("""
            () => {
                function isVisible(elem) {
                    if (!elem) return false;
                    const style = window.getComputedStyle(elem);
                    if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') return false;
                    const rect = elem.getBoundingClientRect();
                    return !!(rect.width && rect.height);
                }
                // Elements to ignore
                const blacklist = ['html', 'body', 'head', 'script', 'style', 'meta', 'link', 'noscript', 'svg'];

                // Get only elements with direct visible text
                const nodes = Array.from(document.querySelectorAll('*')).filter(el => {
                    if (blacklist.includes(el.tagName.toLowerCase())) return false;
                    if (!isVisible(el)) return false;
                    // Get direct text nodes
                    let ownText = "";
                    for (const node of el.childNodes) {
                        if (node.nodeType === Node.TEXT_NODE) {
                            ownText += node.textContent;
                        }
                    }
                    ownText = ownText.trim();
                    return ownText.length > 0;
                });

                // Return info
                return nodes.map(el => {
                    let ownText = "";
                    for (const node of el.childNodes) {
                        if (node.nodeType === Node.TEXT_NODE) {
                            ownText += node.textContent;
                        }
                    }
                    return {
                        type: el.tagName.toLowerCase(),
                        class: el.className || null,
                        id: el.id || null,
                        value: ownText.trim()
                    }
                });
            }
        """)
        return elements

