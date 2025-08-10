from langchain_core.tools import tool
import webbrowser
import requests
from utils import log_return
from bs4 import BeautifulSoup, NavigableString
from ai_agents.tools.web_tools.session_for_tool import PlaywrightSessionAsync
import json

browser_session: PlaywrightSessionAsync | None = None

@tool
@log_return
async def init_browser_session():
    """
    Starts session initialization for the browser (for internal use only, not visible to the user)
    :return:
    """
    global browser_session

    if browser_session is None:
        browser_session = PlaywrightSessionAsync()
        await browser_session.__aenter__()
        return 'Browser initialized (new instance).'

    if browser_session.page is None:
        await browser_session.__aenter__()
        return 'Browser session reused, but page was missing — re-initialized.'

    return 'Browser already exists and page is ready.'

def ensure_browser_session():
    return browser_session

@tool
@log_return
async def browser_navigate(link: str):
    """
    The function switches to the transferred link for all ‘browser’ functions.
    All browser functions will work in the transferred link.
    :param link: url to page
    :return: result of redirection
    """
    session = ensure_browser_session()
    if not session:
        return "Browser session not initialized. Call init_browser_session() first."
    try:
        await session.goto_page(link)
        return f'You have successfully navigated to the page: {link}.'
    except Exception as ex:
        return f'Error: {ex}'


@tool
@log_return
async def browser_get_html_by_part(part_num: int = 0, chunk_size: int = 100) -> str:
    """
     Returns a chunk of elements whose DIRECT text (not from children) is non-empty and visible, as JSON.

     Args:
         part_num (int): Index of the elements chunk to return (0-based).
         chunk_size (int): Number of elements per chunk.

     Returns:
         str: JSON string with keys: total_parts, chunk, part_num, total_elements, error (if any)
     """
    session = ensure_browser_session()
    if not session:
        return json.dumps({"error": "Browser session not initialized. Call init_browser_session() first."})
    try:
        elements = await session.get_visible_text_elements()
        total_elements = len(elements)
        if chunk_size <= 0:
            chunk_size = 100
        total_parts = (total_elements + chunk_size - 1) // chunk_size
        if part_num < 0 or part_num >= total_parts:
            return json.dumps({
                "error": f"part_num {part_num} is out of range (total_parts={total_parts})",
                "total_parts": total_parts,
                "total_elements": total_elements,
            })

        start = part_num * chunk_size
        end = start + chunk_size
        chunk = elements[start:end]
        return json.dumps({
            "total_parts": total_parts,
            "part_num": part_num,
            "total_elements": total_elements,
            "chunk": chunk
        }, ensure_ascii=False, indent=2)
    except Exception as ex:
        return json.dumps({"error": str(ex)})

@tool
@log_return
async def browser_use_console(command: str):
    """
    Execute JavaScript code on the page and capture any console output.

    This runs the provided JavaScript string in the page context.
    Any messages sent to the browser's console will be collected and returned.

    :param
        command (str): A JavaScript expression or statement to evaluate.

    :return:
        srr: A list of console messages triggered during execution.
    """
    session = ensure_browser_session()
    if not session:
        return "Browser session not initialized. Call init_browser_session() first."
    try:
        return await session.eval_console(command)
    except Exception as ex:
        return f"Error: {ex}"


@tool
@log_return
async def browser_get_all_links(part_num:int) -> str:
    """
    Extract all hyperlink URLs from the current page.
    Link generator from a page
    :param part_num: element in a chunk from lists of links
    :return:
        str: A list of all href values from <a> tags on the page.
    """
    session = ensure_browser_session()
    if not session:
        return "Browser session not initialized. Call init_browser_session() first."
    try:
        links = await session.get_all_links()
        chunks = [links[i:i + 40] for i in range(0, len(links), 40)]
        if part_num < 0 or part_num > len(chunks):
            return f'Error: part_num: {part_num} out of range {len(chunks)}'
        return f'Length of links chunks: {len(chunks)}. The links part numbered {part_num}: {chunks[part_num]}'
    except Exception as ex:
        return f'Error: {ex}'




@tool
@log_return
def get_working_links(query: str, max_results: int = 50) -> str:
    """
    Perform a DuckDuckGo search and return result URLs as a newline-separated string.

    Args:
        query (str): Search query.
        max_results (int, optional): Maximum number of links to return. Defaults to 50.

    Returns:
        str: Newline-separated valid URLs, or an error message.
    """
    headers = {
        "User-Agent": "Mozilla/5.0"
    }
    params = {
        "q": query,
        "kl": "ru-ru",
    }
    url = "https://html.duckduckgo.com/html/"

    try:
        response = requests.post(url, headers=headers, data=params, timeout=10)
        response.raise_for_status()
    except requests.RequestException as e:
        return f"Search failed: {str(e)}"

    soup = BeautifulSoup(response.text, "html.parser")
    raw_links = [a["href"] for a in soup.find_all("a", class_="result__a", href=True)]

    banned_domains = [
        "https://okko.tv", "https://rutube.ru", "https://yandex.ru",
        "https://www.kinopoisk.ru", "https://www.netflix.com", "https://hd.kinopoisk.ru",
        "https://premier.one/", "https://2x2tv.ru", "https://www.crunchyroll.com"
    ]

    filtered_links = []
    for link in raw_links:
        if any(link.startswith(banned) for banned in banned_domains):
            continue
        if link not in filtered_links:
            filtered_links.append(link)
        if len(filtered_links) >= max_results:
            break

    if not filtered_links:
        return "No valid links found."

    return ", ".join(filtered_links)


@tool
@log_return
def open_link_in_browser(url: str):
    """
    Opens the specified URL in the user's default web browser.

    This function uses the `webbrowser` module from Python's standard library
    to launch the default browser and open the given URL in a new tab.
    It works across platforms, including Windows, macOS, and Linux.
    It is recommended to execute ‘fetch_page_html’ after performing this function and check the status of the page.

    :param:  url (str): The URL to be opened. Must be a valid HTTP or HTTPS link.

    :return:
        error: If the URL does not start with 'http://' or 'https://'.
    """
    if not url.startswith(("http://", "https://")):
        return "Error: URL must start with 'http://' or 'https://'"
    webbrowser.open_new_tab(url)
    return f"🔍 Открыл результаты поиска: {url}"
