from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


class Mckesson_home_1:
    LOCATORS = {
        "gloves_link": (By.XPATH, "//a[text()='Gloves']"),
        "privacy_statement_link": (By.XPATH, "//a[text()='More information about your privacy, opens in a new tab']"),
        "accept_cookies_button": (By.XPATH, "//button[@id='onetrust-accept-btn-handler']"),
        "compression_gloves_link": (By.XPATH, "//a[text()='Compression Gloves (99)']"),
        "exam_gloves_link": (By.XPATH, "//a[text()='Exam Gloves (828)']"),
        "finger_cots_link": (By.XPATH, "//a[text()='Finger Cots (17)']"),
        "glove_liners_link": (By.XPATH, "//a[text()='Glove Liners (57)']"),
        "beige_item_link": (By.XPATH, "//a[text()='Beige (1)']")
    }

    def __init__(self, driver):
        self.driver = driver
        self.wait = WebDriverWait(driver, 20)

    def get_element(self, key):
        if key not in self.LOCATORS:
            raise RuntimeError(f"Locator '{key}' not found in LOCATORS")
        return self.wait.until(EC.presence_of_element_located(self.LOCATORS[key]))