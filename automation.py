import os
import base64
import json
import re
import requests
from playwright.sync_api import sync_playwright

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL = "qwen2.5vl:3b"

SCREENSHOT_DIR = "screenshots"
REPORT_DIR = "reports"

os.makedirs(SCREENSHOT_DIR, exist_ok=True)
os.makedirs(REPORT_DIR, exist_ok=True)


# ---------------------------------------------------
# Encode image
# ---------------------------------------------------
def encode_image(path):
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode()


# ---------------------------------------------------
# Extract UI elements safely
# ---------------------------------------------------
def extract_ui_elements(page):

    selectors = "input,button,a,textarea,select"

    for _ in range(3):  # retry if navigation happens
        try:

            elements = page.query_selector_all(selectors)

            valid_elements = []
            ui_map = []

            for el in elements:

                try:

                    if not el.is_visible():
                        continue

                    tag = el.evaluate("e => e.tagName")

                    text = el.inner_text().strip()

                    placeholder = el.get_attribute("placeholder")

                    label = text or placeholder or tag

                    idx = len(valid_elements)

                    ui_map.append({
                        "index": idx,
                        "tag": tag,
                        "label": label[:60]
                    })

                    valid_elements.append(el)

                except:
                    pass

            return valid_elements, ui_map

        except:
            page.wait_for_timeout(2000)

    return [], []


# ---------------------------------------------------
# Highlight UI boxes
# ---------------------------------------------------
def highlight_elements(page):

    try:

        page.wait_for_load_state("domcontentloaded")

        boxes = []

        elements = page.query_selector_all("input,button,a,textarea,select")

        for el in elements[:40]:

            try:

                if not el.is_visible():
                    continue

                box = el.bounding_box()

                if box:
                    boxes.append(box)

            except:
                pass

        page.evaluate(
            """(boxes)=>{

            document.querySelectorAll('.ai-box').forEach(e=>e.remove())

            boxes.forEach((box,i)=>{

                const rect=document.createElement('div')

                rect.className='ai-box'

                rect.style.position='absolute'
                rect.style.left=box.x+'px'
                rect.style.top=box.y+'px'
                rect.style.width=box.width+'px'
                rect.style.height=box.height+'px'
                rect.style.border='3px solid red'
                rect.style.zIndex='999999'
                rect.style.pointerEvents='none'

                const label=document.createElement('span')

                label.innerText=i
                label.style.background='red'
                label.style.color='white'
                label.style.fontSize='12px'
                label.style.padding='2px'

                rect.appendChild(label)

                document.body.appendChild(rect)

            })

            }""",
            boxes
        )

    except:
        pass


# ---------------------------------------------------
# Parse LLM JSON safely
# ---------------------------------------------------
def parse_llm_json(text):

    try:

        match = re.search(r"\{[\s\S]*?\}", text)

        if match:
            return json.loads(match.group())

    except Exception as e:
        print("JSON parse error:", e)

    return {"action": "scroll"}


# ---------------------------------------------------
# Ask LLM what to do next
# ---------------------------------------------------
def plan_action(prompt, ui_map, screenshot, history):

    image_b64 = encode_image(screenshot)

    instruction = f"""
You are an AI browser automation agent.

Goal:
{prompt}

Previous actions:
{history}

Visible UI elements:
{json.dumps(ui_map, indent=2)}

Decide next step.

Return JSON only.

Example:
{{"action":"click","index":1}}
{{"action":"type","index":3,"text":"hello"}}
{{"action":"scroll"}}
{{"action":"done"}}
"""

    try:

        r = requests.post(
            OLLAMA_URL,
            json={
                "model": MODEL,
                "prompt": instruction,
                "images": [image_b64],
                "stream": False
            },
            timeout=600
        )

        data = r.json()

        print("OLLAMA RESPONSE:", data)

        if "response" not in data:
            return {"action": "scroll"}

        return parse_llm_json(data["response"])

    except Exception as e:

        print("LLM error:", e)

        return {"action": "scroll"}


# ---------------------------------------------------
# Execute browser action safely
# ---------------------------------------------------
def execute_action(page, elements, action):

    act = action.get("action")

    try:

        if act == "type":

            idx = action.get("index", -1)

            if idx < 0 or idx >= len(elements):
                return

            text = action.get("text", "")

            el = elements[idx]

            el.scroll_into_view_if_needed()

            el.click()

            el.fill(text)

        elif act == "click":

            idx = action.get("index", -1)

            if idx < 0 or idx >= len(elements):
                return

            el = elements[idx]

            el.scroll_into_view_if_needed()

            el.click()

            # wait if navigation happens
            try:
                page.wait_for_load_state("domcontentloaded", timeout=5000)
            except:
                pass

        elif act == "scroll":

            page.mouse.wheel(0, 800)

        page.wait_for_timeout(2000)

    except Exception as e:

        print("Action execution error:", e)

        page.wait_for_timeout(2000)


# ---------------------------------------------------
# MAIN AUTOMATION ENGINE
# ---------------------------------------------------
def run_test(url, prompt):

    results = []
    history = []

    with sync_playwright() as p:

        browser = p.chromium.launch(headless=False)

        page = browser.new_page()

        page.goto(url)

        page.wait_for_load_state("domcontentloaded")

        page.wait_for_timeout(4000)

        for step in range(10):

            print("STEP:", step)

            try:
                page.wait_for_load_state("domcontentloaded")
            except:
                pass

            page.wait_for_timeout(2000)

            highlight_elements(page)

            screenshot = f"{SCREENSHOT_DIR}/step_{step}.png"

            try:
                page.screenshot(path=screenshot)
            except:
                break

            elements, ui_map = extract_ui_elements(page)

            if not elements:
                break

            action = plan_action(prompt, ui_map, screenshot, history)

            print("ACTION:", action)

            if action.get("action") == "done":
                break

            try:

                execute_action(page, elements, action)

                history.append(action)

                results.append({
                    "step": f"Step {step+1}",
                    "status": "PASS",
                    "action": action,
                    "screenshot": screenshot
                })

            except Exception as e:

                results.append({
                    "step": f"Step {step+1}",
                    "status": f"FAIL {str(e)}",
                    "screenshot": screenshot
                })

        final_ss = f"{SCREENSHOT_DIR}/final.png"

        try:
            page.screenshot(path=final_ss)
        except:
            pass

        browser.close()

    # ---------------------------------------------------
    # HTML REPORT
    # ---------------------------------------------------

    report_path = f"{REPORT_DIR}/report.html"

    html = "<h1>AI Browser Automation Report</h1>"

    for r in results:

        html += f"""
        <div style='border:1px solid gray;padding:10px;margin:10px'>
        <h3>{r['step']}</h3>
        <p>Status: {r['status']}</p>
        <p>Action: {r.get('action','')}</p>
        """

        if r["screenshot"]:
            html += f"<img src='/screenshots/{os.path.basename(r['screenshot'])}' width='900'>"

        html += "</div>"

    with open(report_path, "w", encoding="utf-8") as f:
        f.write(html)

    return report_path