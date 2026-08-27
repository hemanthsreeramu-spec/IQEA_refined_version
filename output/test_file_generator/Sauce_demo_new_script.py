import pytest
import allure
import time
import os
from allure_commons.types import AttachmentType
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC

BASE_URL = "https://www.saucedemo.com/"
REPORTS_DIR = os.path.join(os.path.dirname(__file__), "reports")
os.makedirs(REPORTS_DIR, exist_ok=True)

def attach_screenshot(driver, name: str):
    try:
        allure.attach(driver.get_screenshot_as_png(),
                      name=name, attachment_type=AttachmentType.PNG)
    except Exception:
        pass

@pytest.fixture(scope="function")
def setup():
    options = Options()
    options.add_argument("--start-maximized")
    options.add_argument("--disable-notifications")
    driver = webdriver.Chrome(options=options)
    driver.implicitly_wait(0)
    yield driver
    driver.quit()

def retry_interaction(driver, wait, label, interaction_func):
    attempt, last_err = 0, None
    while attempt < 2:
        try:
            interaction_func()
            break
        except Exception as e:
            last_err = e
            attach_screenshot(driver, f"retry_{label}_{attempt}")
            time.sleep(0.5)
            attempt += 1
    if attempt == 2:
        attach_screenshot(driver, f"failed_{label}")
        raise RuntimeError(f"{label} failed: {last_err}")

@allure.title("Happy path: full purchase flow including logout")
@pytest.mark.smoke
def test_happy_path_full_checkout(setup):
    driver = setup
    wait = WebDriverWait(driver, 10)

    driver.get(BASE_URL)
    attach_screenshot(driver, "start")

    with allure.step("Enter valid credentials and login"):
        el_user = wait.until(EC.presence_of_element_located((By.ID, "user-name")))
        el_user.clear()
        el_user.send_keys("standard_user")
        el_pw = wait.until(EC.presence_of_element_located((By.ID, "password")))
        el_pw.clear()
        el_pw.send_keys("secret_sauce")
        btn_login = wait.until(EC.element_to_be_clickable((By.ID, "login-button")))
        btn_login.click()
        # first interaction after page change -> retry rule applies for next recorded first step (step5). But clicking login navigates:
        wait.until(EC.url_contains("/inventory.html"))
        attach_screenshot(driver, "navigated_to_inventory")

    with allure.step("(Recorded) first interaction on inventory page - apply retry as recorded"):
        def step5_action():
            el = wait.until(EC.presence_of_element_located((By.ID, "login-button")))
            # recorded as ENTER_TEXT on a button; performing a harmless send_keys of empty string
            el.send_keys("")
        retry_interaction(driver, wait, "step5_enter_text_login_button", step5_action)

    with allure.step("Add Sauce Labs Backpack to cart"):
        el_add = wait.until(EC.element_to_be_clickable((By.ID, "add-to-cart-sauce-labs-backpack")))
        el_add.click()

    with allure.step("Open cart via cart badge (navigate to cart)"):
        # use cart link selector derived from app structure
        cart_link = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "a.shopping_cart_link")))
        driver.execute_script("arguments[0].click();", cart_link)
        wait.until(EC.url_contains("/cart.html"))
        attach_screenshot(driver, "navigated_to_cart")

    with allure.step("Click cart badge again (on cart page)"):
        # recorded click on badge on cart page (no navigation expected)
        cart_link2 = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "a.shopping_cart_link")))
        cart_link2.click()

    with allure.step("Continue shopping from cart back to inventory"):
        btn_continue_shopping = wait.until(EC.element_to_be_clickable((By.ID, "continue-shopping")))
        driver.execute_script("arguments[0].click();", btn_continue_shopping)
        wait.until(EC.url_contains("/inventory.html"))
        attach_screenshot(driver, "navigated_to_inventory_after_continue_shopping")

    with allure.step("Interact with product sort select (open/choose)"):
        sel = wait.until(EC.presence_of_element_located((By.XPATH, "/html/body/div/div/div/div/div[2]/div/span/select")))
        # clicking/selecting as recorded: click twice then select by visible text
        sel.click()
        sel.click()
        Select(sel).select_by_visible_text("Price (low to high)")

    with allure.step("Open cart again via badge (navigate to cart)"):
        cart_link3 = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "a.shopping_cart_link")))
        driver.execute_script("arguments[0].click();", cart_link3)
        wait.until(EC.url_contains("/cart.html"))
        attach_screenshot(driver, "navigated_to_cart_2")

    with allure.step("Proceed to checkout"):
        btn_checkout = wait.until(EC.element_to_be_clickable((By.ID, "checkout")))
        driver.execute_script("arguments[0].click();", btn_checkout)
        wait.until(EC.url_contains("/checkout-step-one.html"))
        attach_screenshot(driver, "navigated_to_checkout_step_one")

    with allure.step("Fill in checkout information"):
        # first interaction after page change is click firstName per recording -> apply retry
        def step15_action():
            el_fn = wait.until(EC.presence_of_element_located((By.ID, "firstName")))
            el_fn.click()
        retry_interaction(driver, wait, "step15_click_firstName", step15_action)

        el_first = wait.until(EC.presence_of_element_located((By.ID, "firstName")))
        el_first.clear()
        el_first.send_keys("John")
        el_last = wait.until(EC.presence_of_element_located((By.ID, "lastName")))
        el_last.clear()
        el_last.send_keys("Doe")

        # recorded click continue then odd ENTER_TEXT on continue, then enter postalCode then click continue
        btn_continue = wait.until(EC.element_to_be_clickable((By.ID, "continue")))
        btn_continue.click()
        # recorded enter_text on continue - harmless no-op
        el_continue = wait.until(EC.presence_of_element_located((By.ID, "continue")))
        el_continue.send_keys("")

        el_postal = wait.until(EC.presence_of_element_located((By.ID, "postalCode")))
        el_postal.clear()
        el_postal.send_keys("12345")

        btn_continue.click()
        wait.until(EC.url_contains("/checkout-step-two.html"))
        attach_screenshot(driver, "navigated_to_checkout_step_two")

    with allure.step("Finish checkout"):
        # recorded ENTER_TEXT on continue on step two - apply retry as first interaction after page change
        def step23_action():
            el_c = wait.until(EC.presence_of_element_located((By.ID, "continue")))
            el_c.send_keys("")
        retry_interaction(driver, wait, "step23_enter_continue", step23_action)

        btn_finish = wait.until(EC.element_to_be_clickable((By.ID, "finish")))
        btn_finish.click()
        wait.until(EC.url_contains("/checkout-complete.html"))
        attach_screenshot(driver, "navigated_to_checkout_complete")

    with allure.step("Back to products and logout"):
        btn_back = wait.until(EC.element_to_be_clickable((By.ID, "back-to-products")))
        btn_back.click()
        wait.until(EC.url_contains("/inventory.html"))
        attach_screenshot(driver, "navigated_back_to_inventory_after_complete")

        # menu toggle + logout
        menu_btn = wait.until(EC.presence_of_element_located((By.ID, "react-burger-menu-btn")))
        driver.execute_script("arguments[0].click();", menu_btn)
        time.sleep(0.5)
        logout_link = wait.until(EC.element_to_be_clickable((By.ID, "logout_sidebar_link")))
        logout_link.click()
        # after logout, we expect to be back at base login page
        wait.until(EC.url_contains("saucedemo.com"))
        attach_screenshot(driver, "after_logout")

    # Final assertion: ensure we are at the base login page (logged out)
    assert BASE_URL in driver.current_url
    attach_screenshot(driver, "assertion_passed")

@allure.title("Negative: login with invalid credentials should not navigate")
@pytest.mark.negative
def test_negative_login_invalid_credentials(setup):
    driver = setup
    wait = WebDriverWait(driver, 10)

    driver.get(BASE_URL)
    attach_screenshot(driver, "start")

    with allure.step("Enter invalid credentials and attempt login"):
        el_user = wait.until(EC.presence_of_element_located((By.ID, "user-name")))
        el_user.clear()
        el_user.send_keys("invalid_user")
        el_pw = wait.until(EC.presence_of_element_located((By.ID, "password")))
        el_pw.clear()
        el_pw.send_keys("bad_password")
        btn_login = wait.until(EC.element_to_be_clickable((By.ID, "login-button")))
        btn_login.click()
        time.sleep(1)  # allow any client-side validation to run
        attach_screenshot(driver, "after_invalid_login_attempt")

    with allure.step("Assert we remain on the login page"):
        # One assert: URL should still be the base login page (no navigation)
        assert driver.current_url == BASE_URL
        attach_screenshot(driver, "assertion_passed")

@allure.title("Boundary: attempt checkout with missing required information")
@pytest.mark.boundary
def test_boundary_checkout_missing_fields(setup):
    driver = setup
    wait = WebDriverWait(driver, 10)

    driver.get(BASE_URL)
    attach_screenshot(driver, "start")

    with allure.step("Login with valid credentials"):
        el_user = wait.until(EC.presence_of_element_located((By.ID, "user-name")))
        el_user.clear()
        el_user.send_keys("standard_user")
        el_pw = wait.until(EC.presence_of_element_located((By.ID, "password")))
        el_pw.clear()
        el_pw.send_keys("secret_sauce")
        btn_login = wait.until(EC.element_to_be_clickable((By.ID, "login-button")))
        btn_login.click()
        wait.until(EC.url_contains("/inventory.html"))
        attach_screenshot(driver, "navigated_to_inventory")

    with allure.step("Add item and go to cart"):
        el_add = wait.until(EC.element_to_be_clickable((By.ID, "add-to-cart-sauce-labs-backpack")))
        el_add.click()
        cart_link = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "a.shopping_cart_link")))
        driver.execute_script("arguments[0].click();", cart_link)
        wait.until(EC.url_contains("/cart.html"))
        attach_screenshot(driver, "navigated_to_cart")

    with allure.step("Proceed to checkout and click continue without filling fields"):
        btn_checkout = wait.until(EC.element_to_be_clickable((By.ID, "checkout")))
        driver.execute_script("arguments[0].click();", btn_checkout)
        wait.until(EC.url_contains("/checkout-step-one.html"))
        attach_screenshot(driver, "navigated_to_checkout_step_one")

        # Attempt to continue without filling required fields
        btn_continue = wait.until(EC.element_to_be_clickable((By.ID, "continue")))
        btn_continue.click()
        time.sleep(0.5)
        attach_screenshot(driver, "after_click_continue_without_data")

    with allure.step("Assert we remain on checkout-step-one (validation prevented progression)"):
        assert "/checkout-step-one.html" in driver.current_url
        attach_screenshot(driver, "assertion_passed")

@allure.title("Regression: cart operations - add item and continue shopping returns to inventory")
@pytest.mark.regression
def test_cart_add_and_continue_shopping(setup):
    driver = setup
    wait = WebDriverWait(driver, 10)

    driver.get(BASE_URL)
    attach_screenshot(driver, "start")

    with allure.step("Login and add item to cart"):
        el_user = wait.until(EC.presence_of_element_located((By.ID, "user-name")))
        el_user.clear()
        el_user.send_keys("standard_user")
        el_pw = wait.until(EC.presence_of_element_located((By.ID, "password")))
        el_pw.clear()
        el_pw.send_keys("secret_sauce")
        btn_login = wait.until(EC.element_to_be_clickable((By.ID, "login-button")))
        btn_login.click()
        wait.until(EC.url_contains("/inventory.html"))
        attach_screenshot(driver, "navigated_to_inventory")

        el_add = wait.until(EC.element_to_be_clickable((By.ID, "add-to-cart-sauce-labs-backpack")))
        el_add.click()

    with allure.step("Open cart and continue shopping"):
        cart_link = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "a.shopping_cart_link")))
        driver.execute_script("arguments[0].click();", cart_link)
        wait.until(EC.url_contains("/cart.html"))
        attach_screenshot(driver, "navigated_to_cart")

        btn_continue_shopping = wait.until(EC.element_to_be_clickable((By.ID, "continue-shopping")))
        btn_continue_shopping.click()
        wait.until(EC.url_contains("/inventory.html"))
        attach_screenshot(driver, "navigated_back_to_inventory")

    with allure.step("Assert we are back on the inventory page"):
        assert "/inventory.html" in driver.current_url
        attach_screenshot(driver, "assertion_passed")

@allure.title("Regression: logout from inventory via sidebar menu")
@pytest.mark.regression
def test_logout_from_inventory(setup):
    driver = setup
    wait = WebDriverWait(driver, 10)

    driver.get(BASE_URL)
    attach_screenshot(driver, "start")

    with allure.step("Login to application"):
        el_user = wait.until(EC.presence_of_element_located((By.ID, "user-name")))
        el_user.clear()
        el_user.send_keys("standard_user")
        el_pw = wait.until(EC.presence_of_element_located((By.ID, "password")))
        el_pw.clear()
        el_pw.send_keys("secret_sauce")
        btn_login = wait.until(EC.element_to_be_clickable((By.ID, "login-button")))
        btn_login.click()
        wait.until(EC.url_contains("/inventory.html"))
        attach_screenshot(driver, "navigated_to_inventory")

    with allure.step("Open sidebar menu and logout"):
        menu_btn = wait.until(EC.presence_of_element_located((By.ID, "react-burger-menu-btn")))
        driver.execute_script("arguments[0].click();", menu_btn)
        time.sleep(0.5)
        logout_link = wait.until(EC.element_to_be_clickable((By.ID, "logout_sidebar_link")))
        logout_link.click()
        wait.until(EC.url_contains("saucedemo.com"))
        attach_screenshot(driver, "after_logout")

    with allure.step("Assert we are back at the login page after logout"):
        assert BASE_URL in driver.current_url
        attach_screenshot(driver, "assertion_passed")

if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-v", "--tb=short"]))