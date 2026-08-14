Feature: Checkout and logout flow for Sauce Demo

  Background:
    Given I navigate to "https://www.saucedemo.com"
    And I enter "standard_user" in "user-name"
    And I enter "secret_sauce" in "password"
    And I click "login-button"

  Scenario: Add a product to the cart and view cart
    When I click the "add-to-cart-sauce-labs-backpack" button
    And I click the "1" cart link
    Then I should be on the cart page
    And I should see "Sauce Labs Backpack" in the cart

  Scenario: Enter checkout information
    Given I am on the cart page
    When I click the "checkout" button
    And I enter "test" in the "firstName" field
    And I enter "test" in the "lastName" field
    And I enter "8796" in the "postalCode" field
    And I click the "continue" button
    Then I should be on the checkout overview page
    And the cart should contain "Sauce Labs Backpack" on the overview

  Scenario: Complete checkout and return to products
    Given I am on the checkout overview page
    When I click the "finish" button
    Then I should be on the checkout complete page
    When I click the "back-to-products" button
    Then I should be back on the products inventory page

  Scenario: Logout from the application
    Given I am on the products inventory page
    When I click the "react-burger-menu-btn" button
    And I click the "logout_sidebar_link" link
    Then I should be logged out and see the login page