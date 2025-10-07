from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains

class EquifixHome:
    LOCATORS = {
        "place_alert_button": (By.XPATH, "//a[@class='btn gcs-btn gcs-btn--secondary gcs-btn--pill gcs-btn--border mt-3 mx-1']")
    }

    def __init__(self, driver):
        self.driver = driver
        self.wait = WebDriverWait(driver, 10)

    def wait_for_element(self, locator):
        return self.wait.until(EC.presence_of_element_located(locator))

    def click(self, locator):
        element = self.wait_for_element(locator)
        element.click()

    def enter_text(self, locator, text):
        element = self.wait_for_element(locator)
        element.clear()
        element.send_keys(text)

    def switch_to_window_by_index(self, index):
        windows = self.driver.window_handles
        if index < len(windows):
            self.driver.switch_to.window(windows[index])
        else:
            raise RuntimeError(f"Window index {index} out of range. Total windows: {len(windows)}")

    def switch_to_window_by_handle(self, handle):
        windows = self.driver.window_handles
        if handle in windows:
            self.driver.switch_to.window(handle)
        else:
            raise RuntimeError(f"Window handle {handle} does not exist. Available handles: {windows}")

    def switch_to_window_matching_url(self, url):
        for handle in self.driver.window_handles:
            self.driver.switch_to.window(handle)
            if self.driver.current_url == url:
                return
        raise RuntimeError(f"No window with URL {url} found.")

    def switch_to_new_window(self, url=None):
        windows_before = set(self.driver.window_handles)
        WebDriverWait(self.driver, 10).until(lambda driver: len(set(driver.window_handles) - windows_before) > 0)
        new_window = (set(self.driver.window_handles) - windows_before).pop()
        self.driver.switch_to.window(new_window)
        if url and self.driver.current_url != url:
            raise RuntimeError(f"New window URL does not match expected URL: {url}")

    def click_place_an_alert_button(self):
        self.wait_for_element(self.LOCATORS["place_alert_button"])
        self.click(self.LOCATORS["place_alert_button"])