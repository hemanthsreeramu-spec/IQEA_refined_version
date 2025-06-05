```python
from selenium.webdriver.common.by import By
from selenium.webdriver.support.page_factory import PageFactory
from selenium.webdriver.remote.webdriver import WebDriver

class InventoryPage:
    def __init__(self, driver: WebDriver):
        self.driver = driver
        PageFactory.init_elements(self.driver, self)

    # Elements
    burger_menu_button = (By.XPATH, "//button[@id='react-burger-menu-btn' and text()='Open Menu']")
    test_all_tshirt_add_button = (By.XPATH, "//div[text()='Test.allTheThings() T-Shirt (Red)']/following-sibling::div/button")
    sauce_labs_onesie_add_button = (By.XPATH, "//div[text()='Sauce Labs Onesie']/following-sibling::div/button")
    
    # Methods
    def add_test_all_tshirt_to_cart(self):
        self.driver.find_element(*self.test_all_tshirt_add_button).click()

    def add_sauce_labs_onesie_to_cart(self):
        self.driver.find_element(*self.sauce_labs_onesie_add_button).click()


class CartPage:
    def __init__(self, driver: WebDriver):
        self.driver = driver
        PageFactory.init_elements(self.driver, self)

    # Elements
    burger_menu_button = (By.XPATH, "//button[@id='react-burger-menu-btn' and text()='Open Menu']")
    cart_items = (By.XPATH, "//div[@class='cart_item']")  # Assuming it selects each item row

    # Methods
    def get_cart_items_count(self):
        return len(self.driver.find_elements(*self.cart_items))


class CheckoutStepOnePage:
    def __init__(self, driver: WebDriver):
        self.driver = driver
        PageFactory.init_elements(self.driver, self)

    # Elements
    burger_menu_button = (By.XPATH, "//button[@id='react-burger-menu-btn' and text()='Open Menu']")
    postal_code_input = (By.XPATH, "//input[@id='postal-code']")
    continue_button = (By.XPATH, "//input[@id='continue']")
    
    # Methods
    def enter_postal_code(self, postal_code):
        self.driver.find_element(*self.postal_code_input).send_keys(postal_code)

    def click_continue_button(self):
        self.driver.find_element(*self.continue_button).click()
```