from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains

class EquHomePage:
    LOCATORS = {
        "place_alert_button": (By.XPATH, "//a[contains(@class, 'gcs-btn') and contains(text(), 'PLACE AN ALERT')]")
    }

    def __init__(self, driver):
        self.driver = driver
        self.wait = WebDriverWait(self.driver, 10)
        self.actions = ActionChains(self.driver)

    def wait_for_element(self, locator):
        return self.wait.until(EC.presence_of_element_located(locator))

    def click(self, locator):
        self.wait_for_element(locator).click()

    def enter_text(self, locator, text):
        element = self.wait_for_element(locator)
        element.clear()
        element.send_keys(text)

    def switch_to_window_by_index(self, index):
        handles = self.driver.window_handles
        if index < len(handles):
            self.driver.switch_to.window(handles[index])
        else:
            raise RuntimeError(f"Window index {index} is out of range. Available windows: {len(handles)}")

    def switch_to_window_by_handle(self, handle):
        handles = self.driver.window_handles
        if handle in handles:
            self.driver.switch_to.window(handle)
        else:
            raise RuntimeError(f"Window handle {handle} not found. Available handles: {handles}")

    def switch_to_window_matching_url(self, url):
        handles = self.driver.window_handles
        for handle in handles:
            self.driver.switch_to.window(handle)
            if self.driver.current_url == url:
                return
        raise RuntimeError(f"No window matching URL '{url}' was found.")

    def switch_to_new_window(self, url=None):
        handles_before = self.driver.window_handles
        self.wait.until(lambda driver: len(driver.window_handles) > len(handles_before))
        new_handles = [handle for handle in self.driver.window_handles if handle not in handles_before]
        if not new_handles:
            raise RuntimeError("No new window was detected.")
        self.driver.switch_to.window(new_handles[-1])
        if url and self.driver.current_url != url:
            raise RuntimeError(f"Switched to a window with an unexpected URL. Expected: {url}, Found: {self.driver.current_url}")

    def click_place_an_alert(self):
        self.wait_for_element(self.LOCATORS["place_alert_button"])
        self.click(self.LOCATORS["place_alert_button"])