from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

class NewSauceDemoLogin:
    LOCATORS = {
        "user_name": (By.XPATH, "//input[@id='user-name']"),
        "password": (By.XPATH, "//input[@id='password']"),
        "login_button": (By.XPATH, "//input[@id='login-button']"),
    }

    def __init__(self, driver, wait_timeout=10):
        self.driver = driver
        self.wait = WebDriverWait(driver, wait_timeout)

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
        handles = self.driver.window_handles
        if index < len(handles):
            self.driver.switch_to.window(handles[index])
        else:
            raise RuntimeError(f"Invalid window index: {index}")

    def switch_to_window_by_handle(self, handle):
        if handle in self.driver.window_handles:
            self.driver.switch_to.window(handle)
        else:
            raise RuntimeError(f"Invalid window handle: {handle}")

    def switch_to_window_matching_url(self, url):
        for handle in self.driver.window_handles:
            self.driver.switch_to.window(handle)
            if self.driver.current_url == url:
                return
        raise RuntimeError(f"No window with URL: {url}")

    def switch_to_new_window(self, url=None):
        handles_before = set(self.driver.window_handles)
        handles_now = set(self.driver.window_handles)
        new_handles = handles_now - handles_before

        if len(new_handles) != 1:
            raise RuntimeError("Failed to identify the new window reliably")

        new_handle = new_handles.pop()
        self.driver.switch_to.window(new_handle)

        if url and self.driver.current_url != url:
            raise RuntimeError(f"URL mismatch: expected '{url}', found '{self.driver.current_url}'")

    def enter_user_name(self, username):
        self.wait_for_element(self.LOCATORS["user_name"])
        self.enter_text(self.LOCATORS["user_name"], username)

    def enter_password(self, password):
        self.wait_for_element(self.LOCATORS["password"])
        self.enter_text(self.LOCATORS["password"], password)

    def click_login_button(self):
        self.wait_for_element(self.LOCATORS["login_button"])
        self.click(self.LOCATORS["login_button"])

    def perform_login(self, username, password):
        self.enter_user_name(username)
        self.enter_password(password)
        self.click_login_button()