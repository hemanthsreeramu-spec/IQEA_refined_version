```java
package com.saucedemo.pages;

import org.openqa.selenium.WebDriver;
import org.openqa.selenium.WebElement;
import org.openqa.selenium.support.FindBy;
import org.openqa.selenium.support.How;
import org.openqa.selenium.support.PageFactory;

public class CheckoutStepOnePage {

    private WebDriver driver;

    @FindBy(how = How.XPATH, using = "//button[@id='react-burger-menu-btn' and text()='Open Menu']")
    private WebElement openMenuButton;

    @FindBy(how = How.XPATH, using = "//input[@id='postal-code']")
    private WebElement postalCodeInput;

    @FindBy(how = How.XPATH, using = "//input[@id='continue']")
    private WebElement continueButton;

    public CheckoutStepOnePage(WebDriver driver) {
        this.driver = driver;
        PageFactory.initElements(driver, this);
    }

    public void clickOpenMenuButton() {
        openMenuButton.click();
    }

    public void enterPostalCode(String postalCode) {
        postalCodeInput.sendKeys(postalCode);
    }

    public void clickContinueButton() {
        continueButton.click();
    }
}
```