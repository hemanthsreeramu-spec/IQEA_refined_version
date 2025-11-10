from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.alert import Alert
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support.ui import Select
from selenium.webdriver.support import expected_conditions as EC

class EquPlaceOnAlert:
    LOCATORS = {
        "first_name": (By.XPATH, "//input[@id='firstNameId']"),
        "last_name": (By.XPATH, "//input[@id='lastName']"),
        "phone_number": (By.XPATH, "//input[@id='phoneNumber']"),
        "ssn": (By.XPATH, "//input[@id='ssn']"),
        "date_of_birth": (By.XPATH, "//input[@id='dateOfBirthMasked']"),
        "address_line1": (By.XPATH, "//input[@id='addressLine1']"),
        "city_name": (By.XPATH, "//input[@id='cityName']"),
        "address_line2": (By.XPATH, "//input[@id='addressLine2']"),
        "state_select": (By.XPATH, "//select[@id='stateSelect']"),
        "zip_code": (By.XPATH, "//input[@id='zipCode']")
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
        handles = self.driver.window_handles
        if index < len(handles):
            self.driver.switch_to.window(handles[index])
        else:
            raise RuntimeError(f"Window index {index} out of range.")

    def switch_to_window_by_handle(self, handle):
        self.driver.switch_to.window(handle)

    def switch_to_window_matching_url(self, url):
        for handle in self.driver.window_handles:
            self.driver.switch_to.window(handle)
            if self.driver.current_url == url:
                return
        raise RuntimeError(f"No window with URL {url} found.")

    def switch_to_new_window(self, expected_url=None):
        handles = self.driver.window_handles
        if len(handles) > 1:
            self.driver.switch_to.window(handles[-1])
            if expected_url and self.driver.current_url != expected_url:
                raise RuntimeError(f"Expected URL {expected_url} but got {self.driver.current_url}.")
        else:
            raise RuntimeError("No new window to switch to.")

    def enter_first_name(self, first_name):
        self.enter_text(self.LOCATORS["first_name"], first_name)

    def enter_last_name(self, last_name):
        self.enter_text(self.LOCATORS["last_name"], last_name)

    def enter_phone_number(self, phone_number):
        self.enter_text(self.LOCATORS["phone_number"], phone_number)

    def enter_ssn(self, ssn):
        self.enter_text(self.LOCATORS["ssn"], ssn)

    def enter_date_of_birth(self, date_of_birth):
        self.enter_text(self.LOCATORS["date_of_birth"], date_of_birth)

    def enter_address_line1(self, address_line1):
        self.enter_text(self.LOCATORS["address_line1"], address_line1)

    def enter_city_name(self, city_name):
        self.enter_text(self.LOCATORS["city_name"], city_name)

    def enter_address_line2(self, address_line2):
        self.enter_text(self.LOCATORS["address_line2"], address_line2)

    def select_state(self, state_value):
        element = self.wait_for_element(self.LOCATORS["state_select"])
        select = Select(element)
        select.select_by_visible_text(state_value)

    def enter_zip_code(self, zip_code):
        self.enter_text(self.LOCATORS["zip_code"], zip_code)

    def complete_form(self, first_name, last_name, phone_number, ssn, date_of_birth, address_line1, city_name, address_line2, state, zip_code):
        self.enter_first_name(first_name)
        self.enter_last_name(last_name)
        self.enter_phone_number(phone_number)
        self.enter_ssn(ssn)
        self.enter_date_of_birth(date_of_birth)
        self.enter_address_line1(address_line1)
        self.enter_city_name(city_name)
        self.enter_address_line2(address_line2)
        self.select_state(state)
        self.enter_zip_code(zip_code)