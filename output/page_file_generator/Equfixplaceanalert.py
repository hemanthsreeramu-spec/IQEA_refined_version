from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import Select

class Equfixplaceanalert:
    LOCATORS = {
        "first_name": (By.XPATH, "//input[@id='firstNameId']"),
        "last_name": (By.XPATH, "//input[@id='lastName']"),
        "dob": (By.XPATH, "//input[@id='dob']"),
        "ssn": (By.XPATH, "//input[@id='ssn']"),
        "phone_number": (By.XPATH, "//input[@id='phoneNumber']"),
        "address_line1": (By.XPATH, "//input[@id='address']"),
        "address_line2": (By.XPATH, "//input[@id='addressLine2Id']"),
        "city": (By.XPATH, "//input[@id='city']"),
        "zip": (By.XPATH, "//input[@id='zip']"),
        "state_dropdown": (By.XPATH, "//button[starts-with(@id, 'efx-dropdown-label')]"),
        "continue_button": (By.XPATH, "//button[@id='continue-button']"),
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
        self.driver.switch_to.window(windows[index])
    
    def switch_to_window_by_handle(self, handle):
        self.driver.switch_to.window(handle)
    
    def switch_to_window_matching_url(self, url):
        for handle in self.driver.window_handles:
            self.driver.switch_to.window(handle)
            if self.driver.current_url == url:
                return
        raise RuntimeError("No window found with URL: {}".format(url))
    
    def switch_to_new_window(self, url):
        current_handles = set(self.driver.window_handles)
        new_handles = current_handles
        while len(new_handles) == len(current_handles):
            new_handles = set(self.driver.window_handles)
        new_window = list(new_handles - current_handles)[0]
        self.driver.switch_to.window(new_window)
        if self.driver.current_url != url:
            raise RuntimeError("New window URL does not match the expected URL: {}".format(url))
    
    def click_place_alert(self):
        self.switch_to_window_matching_url("https://www.equifax.com/personal/credit-report-services/credit-fraud-alerts/")
        # Assuming button/icon locators are missing, raising error instead.
        raise RuntimeError("Locator for 'Place an Alert' button is missing")
    
    def switch_to_registration_window(self):
        self.switch_to_window_by_index(1)
    
    def enter_ssn(self, ssn):
        self.switch_to_window_matching_url("https://my.equifax.com/consumer-registration/UCSC/#/personal-info")
        self.enter_text(self.LOCATORS["ssn"], ssn)
    
    def enter_last_name(self, last_name):
        self.enter_text(self.LOCATORS["last_name"], last_name)
    
    def enter_phone_number(self, phone_number):
        self.enter_text(self.LOCATORS["phone_number"], phone_number)
    
    def enter_date_of_birth(self, dob):
        self.enter_text(self.LOCATORS["dob"], dob)
    
    def enter_address_line1(self, address_line1):
        self.enter_text(self.LOCATORS["address_line1"], address_line1)
    
    def enter_address_line2(self, address_line2):
        self.enter_text(self.LOCATORS["address_line2"], address_line2)
    
    def enter_city(self, city):
        self.enter_text(self.LOCATORS["city"], city)
    
    def select_state(self, state_name):
        self.click(self.LOCATORS["state_dropdown"])
        state_option = (By.XPATH, f"//button[normalize-space()='{state_name}']")
        self.click(state_option)
    
    def enter_zip_code(self, zip_code):
        self.enter_text(self.LOCATORS["zip"], zip_code)
    
    def proceed_to_next_step(self):
        self.click(self.LOCATORS["continue_button"])