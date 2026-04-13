from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

URL = "https://www.primetherapeutics.com/quarterly-drug-pipeline-january-2026"
XPATH = "//div[@class='clearfix component-paragraph text-break']"

def scrape():
    options = Options()
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )

    driver = webdriver.Chrome(options=options)

    try:
        print(f"[*] Opening: {URL}")
        driver.get(URL)

        # Wait until at least one matching element is present (up to 15s)
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.XPATH, XPATH))
        )

        elements = driver.find_elements(By.XPATH, XPATH)
        print(f"[*] Found {len(elements)} matching element(s)\n")

        all_text_parts = []
        for i, el in enumerate(elements, start=1):
            text = el.text.strip()
            if text:
                all_text_parts.append(text)
                print(f"--- Element {i} ---\n{text}\n")

        combined = "\n\n".join(all_text_parts)
        print("=" * 60)
        print("COMBINED OUTPUT:")
        print("=" * 60)
        print(combined)

        # Save to file
        output_file = "pipeline_text.txt"
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(combined)
        print(f"\n[*] Text saved to: {output_file}")

    finally:
        driver.quit()

if __name__ == "__main__":
    scrape()