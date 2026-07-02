import base64
import time
import json
import re
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager


def start_browser(url: str, headless: bool = False):
    """Open Chrome and navigate to the PBI report URL. Returns the Selenium driver."""
    options = Options()
    if headless:
        options.add_argument("--headless=new")
    options.add_argument("--start-maximized")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--disable-infobars")
    options.add_argument("--disable-extensions")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)

    driver = webdriver.Chrome(
        service=Service(ChromeDriverManager().install()),
        options=options
    )
    driver.maximize_window()
    driver.get(url)
    return driver


def is_driver_alive(driver) -> bool:
    """Check whether the Selenium driver session is still active."""
    try:
        _ = driver.current_url
        return True
    except Exception:
        return False


def take_screenshot(driver) -> tuple:
    """
    Take a screenshot of the current browser view.
    Returns (png_bytes, base64_string).
    """
    png_bytes = driver.get_screenshot_as_png()
    b64 = base64.b64encode(png_bytes).decode("utf-8")
    return png_bytes, b64


def extract_kpis_via_llm(screenshot_b64: str, client) -> list:
    """
    Send PBI screenshot to LLM vision and extract all visible KPI name/value pairs.
    Returns list of dicts: {visual_name, kpi_name, value, value_type}
    """
    prompt = (
        "You are a Power BI data extraction expert. "
        "Analyze this Power BI report screenshot and extract ALL visible KPI values, "
        "metrics, totals, and data points shown on screen.\n\n"
        "For each metric/KPI you can identify, return:\n"
        "- visual_name: the title or header of the chart/card it belongs to (use 'Unknown' if not visible)\n"
        "- kpi_name: the label or name of the metric (e.g. 'Total Revenue', 'YoY Growth', 'Active Users')\n"
        "- value: the displayed value exactly as shown (e.g. '$1.2M', '94.3%', '12,456')\n"
        "- value_type: one of 'currency', 'percentage', 'number', 'text', 'date'\n\n"
        "Be thorough — include ALL numbers, percentages, totals, subtotals, trend values, "
        "and KPI card values visible on screen.\n"
        "Do NOT include axis labels, page titles, filter labels, or navigation buttons.\n\n"
        "Return ONLY a valid JSON array with no markdown code fences, no explanation.\n"
        "Example: [{\"visual_name\": \"Revenue Card\", \"kpi_name\": \"Total Revenue\", "
        "\"value\": \"$1.2M\", \"value_type\": \"currency\"}]"
    )

    response = client.chat.completions.create(
        model="gpt-5-mini",
        messages=[{
            "role": "user",
            "content": [
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/png;base64,{screenshot_b64}",
                        "detail": "high"
                    }
                },
                {"type": "text", "text": prompt}
            ]
        }],
        max_tokens=4000,
        timeout=600,
    )

    raw = response.choices[0].message.content.strip()

    # Strip markdown fences if the model wraps the JSON
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)

    return json.loads(raw)


def try_show_as_table(driver, wait_seconds: int = 6) -> list:
    """
    For every PBI visual on screen:
      1. Find visual containers via JavaScript
      2. Fire contextmenu event via JS (Selenium right-click is blocked by PBI published view)
      3. Find and click 'Show as a table' via JS
      4. Wait for Focus Mode to load (PBI opens a full page, NOT a modal)
      5. Scrape the focus-mode table with position-based JS extraction
      6. Click 'Back to report' to return before moving to the next visual
    Returns list of dicts: {visual_title, headers, rows}
    """
    _JS_FIND_VISUALS = """
        var selectors = [
            'visual-container-modern',
            'visual-container',
            '[class*="visualContainer"]',
            '[class*="visual-container"]'
        ];
        var found = [];
        selectors.forEach(function(sel) {
            Array.from(document.querySelectorAll(sel)).forEach(function(el) {
                var r = el.getBoundingClientRect();
                if (r.width > 50 && r.height > 50 && found.indexOf(el) === -1) {
                    found.push(el);
                }
            });
        });
        return found;
    """

    results = []

    # Count visuals once upfront — used only for the loop range.
    # Element references are re-fetched on EVERY iteration because
    # Focus Mode re-renders the entire DOM, making prior references stale.
    initial_visuals = driver.execute_script(_JS_FIND_VISUALS)
    total = len(initial_visuals)
    print(f"[PBI] Found {total} visible visual(s)")
    if total == 0:
        print("[PBI] No visual containers found")
        return results

    for idx in range(total):
        title = "Untitled"
        try:
            # Re-fetch fresh elements — previous references are invalid after
            # any Focus Mode round-trip (PBI re-renders the whole DOM on return)
            visuals = driver.execute_script(_JS_FIND_VISUALS)
            if idx >= len(visuals):
                print(f"[PBI] Visual {idx + 1} no longer in DOM — stopping")
                break

            visual = visuals[idx]
            title = _get_visual_title(visual)
            print(f"[PBI] Visual {idx + 1}/{total}: '{title}'")

            driver.execute_script(
                "arguments[0].scrollIntoView({block:'center', inline:'center'});", visual
            )
            time.sleep(0.5)

            # Fire contextmenu via JS — bypasses PBI's synthetic-event block
            driver.execute_script("""
                var el = arguments[0];
                var rect = el.getBoundingClientRect();
                var cx = rect.left + rect.width  / 2;
                var cy = rect.top  + rect.height / 2;
                ['mousedown', 'mouseup', 'contextmenu'].forEach(function(evtName) {
                    el.dispatchEvent(new MouseEvent(evtName, {
                        bubbles: true, cancelable: true, view: window,
                        button: 2, buttons: 2, clientX: cx, clientY: cy
                    }));
                });
            """, visual)
            time.sleep(1.2)

            # Find 'Show as a table' via JS — language/whitespace agnostic
            show_btn = driver.execute_script("""
                var kw = ['show as a table', 'show as table', 'show data'];
                return Array.from(document.querySelectorAll('*')).find(function(el) {
                    if (!el.offsetParent) return false;
                    if (el.children.length > 0) return false;
                    var t = (el.textContent || '').trim().toLowerCase();
                    return kw.indexOf(t) !== -1;
                }) || null;
            """)

            if not show_btn:
                print(f"[PBI]   → 'Show as a table' not in context menu — skipping")
                _dismiss_menu(driver)
                continue

            print(f"[PBI]   → Clicking 'Show as a table'")
            show_btn.click()

            # PBI opens Focus Mode (full page view) — wait for 'Back to report'
            try:
                WebDriverWait(driver, wait_seconds).until(
                    lambda d: d.find_elements(
                        By.XPATH, "//*[contains(text(),'Back to report')]"
                    )
                )
                print(f"[PBI]   → Focus mode loaded")
            except Exception:
                time.sleep(wait_seconds)

            time.sleep(1.5)  # let table fully render

            table_data = _scrape_focus_mode_table(driver)
            if table_data and (table_data.get("headers") or table_data.get("rows")):
                table_data["visual_title"] = title
                results.append(table_data)
                print(f"[PBI]   → {len(table_data.get('rows', []))} row(s) collected")
            else:
                print(f"[PBI]   → Focus mode loaded but no data scraped")

            # Navigate back — waits internally until visuals reappear
            _navigate_back_to_report(driver)

        except Exception as exc:
            print(f"[PBI]   → Error on '{title}': {exc}")
            _navigate_back_to_report(driver)
            continue

    print(f"[PBI] Done — {len(results)} table(s) extracted")
    return results


def _get_visual_title(visual_el) -> str:
    for selector in [".visualTitle", ".visual-title", "title", ".title"]:
        try:
            return visual_el.find_element(By.CSS_SELECTOR, selector).text.strip()
        except Exception:
            pass
    return "Untitled Visual"


def _dismiss_menu(driver):
    try:
        driver.find_element(By.TAG_NAME, "body").send_keys(Keys.ESCAPE)
        time.sleep(0.3)
    except Exception:
        pass


def _navigate_back_to_report(driver):
    """
    Exit PBI Focus Mode by clicking 'Back to report'.
    Never calls history.back() — that navigates away from PBI entirely.
    After clicking, waits until visual containers reappear so the next
    iteration gets fresh, valid element references.
    """
    clicked = False

    # Try JS find first
    try:
        back_btn = driver.execute_script("""
            return Array.from(document.querySelectorAll('*')).find(function(el) {
                if (!el.offsetParent) return false;
                var t = (el.textContent || '').trim().toLowerCase();
                return t === 'back to report';
            }) || null;
        """)
        if back_btn:
            back_btn.click()
            clicked = True
    except Exception:
        pass

    # XPath fallback
    if not clicked:
        try:
            btn = driver.find_element(
                By.XPATH, "//*[contains(text(),'Back to report')]"
            )
            btn.click()
            clicked = True
        except Exception:
            pass

    if not clicked:
        print("[PBI]   → 'Back to report' button not found — staying on current page")
        return

    # Wait until visual containers reappear (report fully restored)
    try:
        WebDriverWait(driver, 8).until(
            lambda d: d.execute_script("""
                var found = document.querySelectorAll(
                    'visual-container-modern, visual-container, [class*="visualContainer"]'
                );
                return found.length > 0;
            """)
        )
        print("[PBI]   → Back to report — visuals loaded")
    except Exception:
        time.sleep(2.0)  # fallback wait if WebDriverWait times out


def _scrape_focus_mode_table(driver) -> dict:
    """
    Scrape the data table from PBI Focus Mode.

    Focus Mode layout:
      - Top ~35% of viewport  → chart / visual
      - Bottom ~65% of viewport → data table (column headers + data rows)

    Three strategies tried in order:
      1. role-grid (lower-half scoped):
           Finds all grids then picks the one whose top >= 35% viewport so we
           get the DATA table, not the chart/KPI-card grid at the top.
           hasRowHeader is detected from DATA rows (non-empty rowheader = real
           dimension value like "APAC"; empty placeholder = KPI card).
      2. lower-half position scan:
           Same 35% cutoff. Detects dimension column headers by finding
           rowheader elements at the same Y position as the columnheaders.
      3. class-based: innerText of known PBI table container classes.

    innerText is used throughout (not textContent) so sibling text nodes are
    separated by whitespace and values like "Total Sales$12.64M" cannot occur.
    """
    result = driver.execute_script("""
        var cutoff = window.innerHeight * 0.35;

        function cellText(el) {
            return ((el.innerText || el.textContent) || '').trim();
        }

        // ── Strategy 1: role-grid scoped to lower-half viewport ───────────────
        var allGrids = Array.from(document.querySelectorAll(
            '[role="grid"], [role="table"], [role="treegrid"]'
        ));

        // Prefer grids whose top is in the lower half; fall back to last grid.
        var lowerGrids = allGrids.filter(function(g) {
            var r = g.getBoundingClientRect();
            return r.top >= cutoff && r.height > 30 && r.width > 50;
        });
        var grid = lowerGrids.length > 0 ? lowerGrids[0]
                 : allGrids.length > 0   ? allGrids[allGrids.length - 1]
                 : null;

        if (grid) {
            var gridRows = Array.from(grid.querySelectorAll('[role="row"]'));

            // Find the first row that owns a columnheader — that is the header row.
            var headerRow = null;
            for (var ri = 0; ri < gridRows.length; ri++) {
                if (gridRows[ri].querySelector('[role="columnheader"]')) {
                    headerRow = gridRows[ri];
                    break;
                }
            }

            // Build column header list (keep rowheader + columnheader from header row
            // so "MARKET" is captured regardless of which ARIA role PBI uses for it).
            var hdrs = headerRow
                ? Array.from(headerRow.querySelectorAll(
                      '[role="rowheader"], [role="columnheader"]'
                  )).map(cellText).filter(function(t) { return t.length > 0; })
                : Array.from(grid.querySelectorAll('[role="columnheader"]'))
                      .map(cellText).filter(function(t) { return t.length > 0; });

            // Detect hasRowHeader from DATA rows (not the header row).
            // PBI uses [role="rowheader"] for dimension values in data rows (e.g. "APAC",
            // "EU") but adds an EMPTY placeholder rowheader in pure-metric tables (KPI
            // cards). Checking rhText.length means:
            //   - "APAC" (len > 0) -> real dimension -> hasRowHeader = true, include it
            //   - ""     (len = 0) -> KPI card placeholder -> skip, collect only gridcells
            // This prevents both bugs:
            //   MARKET chart -> row[0]="APAC", kpi_name="Total Sales [APAC]"
            //   KPI card     -> all 6 gridcells aligned with 6 column headers (no shift)
            var dRows = [];
            var hasRowHeader = false;

            gridRows.forEach(function(row) {
                if (row.querySelector('[role="columnheader"]')) return; // skip header row

                var rhEl    = row.querySelector('[role="rowheader"]');
                var rhText  = rhEl ? cellText(rhEl) : '';
                var gcTexts = Array.from(
                    row.querySelectorAll('[role="gridcell"], [role="cell"]')
                ).map(cellText);

                if (rhText.length > 0) {
                    // Non-empty rowheader = real dimension value (e.g. "APAC", "EU")
                    hasRowHeader = true;
                    dRows.push([rhText].concat(gcTexts));
                } else if (gcTexts.length > 0) {
                    // Empty/absent rowheader = pure metric row (KPI cards) -> gridcells only
                    dRows.push(gcTexts);
                }
                // Both empty -> blank spacer row -> skip
            });

            if (dRows.length > 0) {
                return { headers: hdrs, rows: dRows,
                         has_row_header: hasRowHeader, strategy: 'role-grid+rowheader' };
            }
        }

        // ── Strategy 2: lower-half viewport position scan ─────────────────────
        function inTableArea(el) {
            var r = el.getBoundingClientRect();
            return r.top >= cutoff && r.width > 0 && r.height > 0;
        }

        var colHdrs   = Array.from(document.querySelectorAll('[role="columnheader"]')).filter(inTableArea);
        var rowHdrs   = Array.from(document.querySelectorAll('[role="rowheader"]')).filter(inTableArea);
        var dataCells = Array.from(document.querySelectorAll('[role="gridcell"]')).filter(inTableArea);

        if (colHdrs.length > 0) {
            // Rowheader elements at the same Y level as the colHdrs are dimension
            // column HEADERS (e.g. "MARKET"), not data values — separate them out.
            var colHdrTop = Math.min.apply(null, colHdrs.map(function(el) {
                return el.getBoundingClientRect().top;
            }));
            var dimHdrEls = rowHdrs.filter(function(el) {
                return Math.abs(el.getBoundingClientRect().top - colHdrTop) < 6;
            });
            var dataRowHdrs = rowHdrs.filter(function(el) {
                return dimHdrEls.indexOf(el) === -1;
            });

            // Dimension column exists only when a non-empty rowheader sits in the
            // header row (same Y level as the columnheaders).
            var hasRowHeader2 = dimHdrEls.length > 0;

            // Full header list: dimension col(s) first (if any), then metric cols.
            var dimHdrTexts    = dimHdrEls.map(cellText);
            var metricHdrTexts = colHdrs.map(cellText);
            var headers2 = hasRowHeader2
                ? dimHdrTexts.concat(metricHdrTexts)
                : metricHdrTexts;
            var numCols = headers2.length > 0 ? headers2.length : metricHdrTexts.length;

            // Pure-metric tables: skip dataRowHdrs (empty placeholder cells) and
            // use only gridcells so indices align with the metric-only header list.
            var cellSrc = hasRowHeader2
                ? dataRowHdrs.concat(dataCells)
                : dataCells;

            var allCells = cellSrc.sort(function(a, b) {
                var ra = a.getBoundingClientRect();
                var rb = b.getBoundingClientRect();
                var dy = Math.round((ra.top - rb.top) / 5) * 5;
                return dy !== 0 ? dy : ra.left - rb.left;
            }).map(cellText);

            var dataRows2 = [];
            for (var i = 0; i < allCells.length; i += numCols) {
                var chunk = allCells.slice(i, i + numCols);
                if (chunk.some(function(c) { return c.length > 0; })) {
                    dataRows2.push(chunk);
                }
            }

            if (dataRows2.length > 0) {
                return { headers: headers2, rows: dataRows2,
                         has_row_header: hasRowHeader2, strategy: 'lower-half' };
            }
        }

        // ── Strategy 3: PBI class-based table container ───────────────────────
        var tbl = document.querySelector(
            '[class*="dataTable"], [class*="tablixContainer"], ' +
            '[class*="matrixContainer"], [class*="tableContainer"]'
        );
        if (tbl) {
            var lines = (tbl.innerText || tbl.textContent).split('\\n')
                .map(function(l) { return l.trim(); })
                .filter(function(l) { return l.length > 0; });
            if (lines.length > 0) {
                return {
                    headers: [],
                    rows: lines.map(function(l) { return [l]; }),
                    strategy: 'class-innerText'
                };
            }
        }

        return null;
    """)

    if result:
        print(f"[PBI]   → Strategy: {result.get('strategy')} | "
              f"Headers: {result.get('headers')} | "
              f"Rows: {len(result.get('rows', []))}")

    return result or {}
