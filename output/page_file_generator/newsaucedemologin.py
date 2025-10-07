from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.remote.webdriver import WebDriver

class NewSauceDemoLogin:
    LOCATORS = {
        "user_name": (By.XPATH, "//input[@id='user-name']"),
        "password": (By.XPATH, "//input[@id='password']"),
        "login_button": (By.XPATH, "//input[@id='login-button']")
    }

    def __init__(self, driver: WebDriver, wait_timeout: int = 10):
        self.driver = driver
        self.wait = WebDriverWait(self.driver, wait_timeout)

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
            raise IndexError("Window index out of bounds")

    def switch_to_window_by_handle(self, handle):
        self.driver.switch_to.window(handle)

    def switch_to_window_matching_url(self, url):
        for handle in self.driver.window_handles:
            self.driver.switch_to.window(handle)
            if self.driver.current_url == url:
                return
        raise RuntimeError(f"No window found with URL: {url}")

    def switch_to_new_window(self, url=None):
        current_handles = self.driver.window_handles
        if len(current_handles) > 1:
            self.driver.switch_to.window(current_handles[-1])
            if url and self.driver.current_url != url:
                raise RuntimeError(f"URL mismatch after switching windows. Expected: {url}, Found: {self.driver.current_url}")
        else:
            raise RuntimeError("No new window available to switch to")

    def perform_login(self, username, password):
        self.wait_for_element(self.LOCATORS["user_name"])
        self.click(self.LOCATORS["user_name"])
        self.enter_text(self.LOCATORS["user_name"], username)

        self.wait_for_element(self.LOCATORS["password"])
        self.click(self.LOCATORS["password"])
        self.enter_text(self.LOCATORS["password"], password)

        self.wait_for_element(self.LOCATORS["login_button"])
        self.click(self.LOCATORS["login_button"])