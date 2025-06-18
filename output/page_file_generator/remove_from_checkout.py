```python
from selenium.webdriver.common.by import By
from selenium.webdriver.support.page_factory import PageFactory
from selenium.webdriver.remote.webdriver import WebDriver


class CheckoutPage:
    def __init__(self, driver: WebDriver):
        self.driver = driver
        PageFactory.init_elements(driver, self)

    @property
    def burger_menu_button(self):
        return self.driver.find_element(By.XPATH, "//button[@id='react-burger-menu-btn']")

    @property
    def cancel_button(self):
        return self.driver.find_element(By.XPATH, "//button[@id='cancel' and text()='Cancel']")

    @property
    def finish_button(self):
        return self.driver.find_element(By.XPATH, "//button[@id='finish' and @name='finish']")

    def add_items_to_cart(self, items):
        for item in items:
            self.driver.find_element(By.XPATH, f"//div[text()='{item}']//following-sibling::button").click()

    def click_cart_quantity(self, quantity):
        self.driver.find_element(By.XPATH, f"//span[text()='{quantity}']").click()

    def initiate_checkout(self):
        self.driver.find_element(By.XPATH, "//button[text()='Checkout']").click()

    def enter_user_details(self, first_name, last_name, postal_code):
        first_name_field = self.driver.find_element(By.XPATH, "//input[@id='first-name']")
        first_name_field.clear()
        first_name_field.send_keys(first_name)

        last_name_field = self.driver.find_element(By.XPATH, "//input[@id='last-name']")
        last_name_field.clear()
        last_name_field.send_keys(last_name)

        postal_code_field = self.driver.find_element(By.XPATH, "//input[@id='postal-code']")
        postal_code_field.clear()
        postal_code_field.send_keys(postal_code)

    def proceed_to_next_step(self):
        self.driver.find_element(By.XPATH, "//input[@id='continue']").click()
```