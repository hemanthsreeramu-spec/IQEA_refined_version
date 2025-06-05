```python
# test_checkout_page.py
import pytest
from checkout_page import CheckoutPage

@pytest.fixture
def setup_checkout_page(driver):
    # Initialize the CheckoutPage with the driver instance
    return CheckoutPage(driver)

@pytest.mark.usefixtures("setup_checkout_page")
class TestCheckoutPage:
    
    def test_add_sauce_labs_onesie_to_cart(self, setup_checkout_page):
        """
        Test case: Add “Sauce Labs Onesie” to Cart
        """
        # Add "Sauce Labs Onesie" to the cart
        setup_checkout_page.add_sauce_labs_onesie_to_cart()
        
        # Validate that the cart items count increased
        cart_count = setup_checkout_page.get_cart_items_count()
        assert cart_count == 1, f"Expected 1 item in the cart, but got {cart_count}."
    
    def test_add_test_all_tshirt_to_cart(self, setup_checkout_page):
        """
        Test case: Add “Test.allTheThings() T-Shirt (Red)” to Cart
        """
        # Add "Test.allTheThings() T-Shirt (Red)" to the cart
        setup_checkout_page.add_test_all_tshirt_to_cart()
        
        # Validate that the cart items count increased
        cart_count = setup_checkout_page.get_cart_items_count()
        assert cart_count == 1, f"Expected 1 item in the cart, but got {cart_count}."
```