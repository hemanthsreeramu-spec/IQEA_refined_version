```java
import org.openqa.selenium.By;
import org.openqa.selenium.WebDriver;
import org.openqa.selenium.WebElement;
import org.openqa.selenium.support.FindBy;
import org.openqa.selenium.support.How;
import org.openqa.selenium.support.PageFactory;
import org.openqa.selenium.support.ui.ExpectedConditions;
import org.openqa.selenium.support.ui.WebDriverWait;

import java.util.ArrayList;
import java.util.List;
import java.util.Set;

public class Test {

    private WebDriver driver;
    private WebDriverWait wait;

    @FindBy(how = How.XPATH, using = "//input[@id='login-button']")
    private WebElement loginButton;

    @FindBy(how = How.XPATH, using = "//input[@id='user-name']")
    private WebElement userNameField;

    @FindBy(how = How.XPATH, using = "//button[text()='Add to cart']")
    private WebElement addToCartButton;

    @FindBy(how = How.XPATH, using = "//button[text()='Open Menu']")
    private WebElement openMenuButton;

    @FindBy(how = How.XPATH, using = "//button[@id='react-burger-menu-btn']")
    private WebElement reactBurgerMenuButton;

    public Test(WebDriver driver) {
        this.driver = driver;
        this.wait = new WebDriverWait(driver, 30); // Wait of 30 seconds
        PageFactory.initElements(driver, this);
    }

    private void waitForElement(WebElement element) {
        wait.until(ExpectedConditions.visibilityOf(element));
    }

    private void click(WebElement element) {
        waitForElement(element);
        element.click();
    }

    private void enterText(WebElement element, String text) {
        waitForElement(element);
        element.clear();
        element.sendKeys(text);
    }

    private void switchToWindowByIndex(int index) {
        List<String> windowHandles = new ArrayList<>(driver.getWindowHandles());
        if (index < windowHandles.size()) {
            driver.switchTo().window(windowHandles.get(index));
        } else {
            throw new RuntimeException("Window with index " + index + " does not exist.");
        }
    }

    private void switchToWindowByHandle(String handle) {
        Set<String> windowHandles = driver.getWindowHandles();
        if (windowHandles.contains(handle)) {
            driver.switchTo().window(handle);
        } else {
            throw new RuntimeException("Window with handle " + handle + " does not exist.");
        }
    }

    private void switchToWindowMatchingUrl(String url) {
        Set<String> windowHandles = driver.getWindowHandles();
        for (String handle : windowHandles) {
            driver.switchTo().window(handle);
            if (driver.getCurrentUrl().equals(url)) {
                return;
            }
        }
        throw new RuntimeException("No window matching URL " + url + " found.");
    }

    private void switchToNewWindow(String expectedUrl) {
        List<String> windowHandles = new ArrayList<>(driver.getWindowHandles());
        if (windowHandles.size() > 1) {
            driver.switchTo().window(windowHandles.get(windowHandles.size() - 1));
            if (!driver.getCurrentUrl().contains(expectedUrl)) {
                throw new RuntimeException("Switched to the new window, but URL does not match the expected URL: " + expectedUrl);
            }
        } else {
            throw new RuntimeException("No new window found to switch to.");
        }
    }

    public void clickLoginButton() {
        click(loginButton);
    }

    public void enterUserName(String username) {
        enterText(userNameField, username);
    }

    public void clickAddToCartButton() {
        click(addToCartButton);
    }

    public void clickOpenMenuButton() {
        click(openMenuButton);
    }

    public void clickReactBurgerMenuButton() {
        click(reactBurgerMenuButton);
    }

    public void completeLoginProcess(String username) {
        enterUserName(username);
        clickLoginButton();
    }

    public void switchToPersonalInfoWindow(String url) {
        switchToWindowMatchingUrl(url);
    }

    public void openAlertWindow(String expectedUrl) {
        switchToNewWindow(expectedUrl);
    }

    public void performMultiWindowActions() {
        // Example chained method: Open alert window, return to personal info, perform additional actions
        openAlertWindow("https://www.equifax.com/personal/credit-report-services/credit-fraud-alerts/");
        switchToPersonalInfoWindow("https://my.equifax.com/consumer-registration/UCSC/#/personal-info");
        clickAddToCartButton();
    }
}
```