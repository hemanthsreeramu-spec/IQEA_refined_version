const fs = require('fs');
const path = require('path');
const { webkit } = require('playwright');

(async () => {
  const domList = [];
  const outputDomDir = path.join('output', 'Dom_details');
  const outputScriptDir = path.join('output', 'Dom_script');
  const domFilePath = path.join(outputDomDir, 'all_page_dom_details.json');
  const scriptFilePath = path.join(outputScriptDir, 'dom_collector.js');

  try {
    fs.mkdirSync(outputDomDir, { recursive: true });
    fs.mkdirSync(outputScriptDir, { recursive: true });
  } catch (e) {
    console.warn('Could not create output directories:', e.message);
  }

  const browser = await webkit.launch({ headless: false });
  const context = await browser.newContext();
  const page = await context.newPage();

  // Helper: safe click
  async function clickSafe(selector, options = {}) {
    try {
      await page.waitForSelector(selector, { timeout: 5000 });
      await page.click(selector, options);
      return true;
    } catch (e) {
      console.warn(`clickSafe: Element not found or not clickable: ${selector}`);
      return false;
    }
  }

  // Helper: safe type/fill
  async function typeSafe(selector, text) {
    try {
      await page.waitForSelector(selector, { timeout: 5000 });
      await page.fill(selector, text);
      return true;
    } catch (e) {
      console.warn(`typeSafe: Element not found or not fillable: ${selector}`);
      return false;
    }
  }

  // Helper: safe select
  async function selectSafe(selector, optionTextOrValue) {
    try {
      await page.waitForSelector(selector, { timeout: 5000 });
      const chosen = await page.evaluate(
        ({ selector, optionTextOrValue }) => {
          const sel = document.querySelector(selector);
          if (!sel) return null;
          // If provided, try to select by value first, then by visible text
          if (optionTextOrValue) {
            for (const opt of Array.from(sel.options)) {
              if (opt.value === optionTextOrValue || opt.text === optionTextOrValue) {
                sel.value = opt.value;
                sel.dispatchEvent(new Event('change', { bubbles: true }));
                return opt.value;
              }
            }
          }
          // No explicit option provided or not found: choose first non-default option
          for (const opt of Array.from(sel.options)) {
            const val = (opt.value || '').trim();
            const txt = (opt.text || '').trim().toLowerCase();
            if (val && val !== '0' && txt !== 'select' && txt !== 'choose') {
              sel.value = opt.value;
              sel.dispatchEvent(new Event('change', { bubbles: true }));
              return opt.value;
            }
          }
          // Fallback to first option
          if (sel.options.length > 0) {
            sel.value = sel.options[0].value;
            sel.dispatchEvent(new Event('change', { bubbles: true }));
            return sel.options[0].value;
          }
          return null;
        },
        { selector, optionTextOrValue }
      );
      if (!chosen) {
        console.warn(`selectSafe: No option chosen for ${selector}`);
        return false;
      }
      return true;
    } catch (e) {
      console.warn(`selectSafe: Error selecting option for ${selector}: ${e.message}`);
      return false;
    }
  }

  // Mapping of stable selectors per page name
  const stableSelector = {
    login: '#login-button',
    inventory: '.inventory_list, .inventory_container, .inventory_item',
    cart: '.cart_list, .cart_item',
    checkout_info: '#continue, #firstName',
    checkout_overview: '.checkout_summary_container, #finish',
    checkout_complete: '.complete-header, .checkout_complete_container',
    inventory_after_finish: '.inventory_list, .inventory_container',
    login_after_logout: '#login-button',
  };

  // Helper: try to accept cookies if any prompts exist (non-blocking)
  async function tryAcceptCookies() {
    const cookieSelectors = [
      'button#accept-cookies',
      'button.cookie-accept',
      'button[aria-label="accept cookies"]',
      '.onetrust-accept-btn-handler',
      '.cookie-consent-accept',
      'button.accept',
      'button[data-testid="accept-cookies"]',
    ];
    for (const sel of cookieSelectors) {
      try {
        const el = await page.$(sel);
        if (el) {
          try {
            await el.click();
            return true;
          } catch {
            // ignore
          }
        }
      } catch {
        // ignore
      }
    }
    return false;
  }

  // Helper: try to close overlays/popups
  async function tryDismissOverlays() {
    const closeSelectors = [
      '.modal .close',
      '.modal button.close',
      '.overlay .close-button',
      '.popup-close',
      '.close',
      'button[aria-label="Close"]',
      '.react-modal__close',
      '.close-modal',
    ];
    for (const sel of closeSelectors) {
      try {
        const el = await page.$(sel);
        if (el) {
          try {
            await el.click();
            // small pause to let UI update
            try {
              await page.waitForTimeout(300);
            } catch {}
          } catch {
            // ignore
          }
        }
      } catch {
        // ignore
      }
    }
  }

  // captureDom: waits for networkidle and a stable selector then saves DOM
  async function captureDom(pageName) {
    try {
      // Wait for network to be idle - non-critical
      try {
        await page.waitForLoadState('networkidle', { timeout: 5000 });
      } catch (e) {
        // ignore non-critical timeout
      }

      // Wait for page-specific stable element if known
      const sel = stableSelector[pageName];
      if (sel) {
        try {
          await page.waitForSelector(sel, { timeout: 7000 });
        } catch (e) {
          // non-critical
          console.warn(`captureDom: Stable selector "${sel}" not found for page "${pageName}"`);
        }
      } else {
        // generic wait for body
        try {
          await page.waitForSelector('body', { timeout: 5000 });
        } catch {}
      }

      // small safe pause to let dynamic content settle
      try {
        await page.waitForTimeout(300);
      } catch {}

      const html = await page.content();
      domList.push({ page_name: pageName, html });
    } catch (e) {
      console.warn(`captureDom: Failed for ${pageName}: ${e.message}`);
      try {
        const html = await page.content();
        domList.push({ page_name: pageName, html });
      } catch (e2) {
        console.warn('captureDom: Also failed to get page.content()', e2.message);
      }
    }
  }

  // Start the scripted flow based on the feature file
  try {
    // Navigate to login page
    try {
      await page.goto('https://www.saucedemo.com', { waitUntil: 'domcontentloaded' });
    } catch (e) {
      console.warn('Initial navigation failed:', e.message);
    }

    // Before any interaction, wait for #login-button then capture login page DOM
    try {
      await page.waitForSelector('#login-button', { timeout: 10000 });
    } catch (e) {
      console.warn('Login button not found in time:', e.message);
    }
    await captureDom('login');

    // After capturing initial DOM, attempt to accept cookies and dismiss overlays (non-blocking)
    try {
      await tryAcceptCookies();
    } catch {}
    try {
      await tryDismissOverlays();
    } catch {}

    // Background: enter username and password and click login
    try {
      await typeSafe('#user-name', 'standard_user');
    } catch (e) {
      console.warn('Could not type username:', e.message);
    }
    try {
      await typeSafe('#password', 'secret_sauce');
    } catch (e) {
      console.warn('Could not type password:', e.message);
    }
    try {
      await clickSafe('#login-button');
    } catch (e) {
      console.warn('Could not click login button:', e.message);
    }

    // After login, wait for inventory stable element and capture
    try {
      await page.waitForLoadState('networkidle', { timeout: 7000 });
    } catch {}
    try {
      await page.waitForSelector(stableSelector.inventory.split(',')[0], { timeout: 8000 });
    } catch {}
    await captureDom('inventory');

    // Scenario: Add a product to the cart and view cart
    try {
      // Click add to cart for Sauce Labs Backpack
      await clickSafe('#add-to-cart-sauce-labs-backpack');
    } catch (e) {
      console.warn('Error clicking add to cart:', e.message);
    }

    // Click cart link (shopping cart)
    try {
      await clickSafe('.shopping_cart_link');
    } catch (e) {
      console.warn('Error clicking cart link:', e.message);
    }

    // Wait for cart page stable element then capture
    try {
      await page.waitForLoadState('networkidle', { timeout: 7000 });
    } catch {}
    try {
      await page.waitForSelector(stableSelector.cart, { timeout: 8000 });
    } catch {}
    await captureDom('cart');

    // Scenario: Enter checkout information
    try {
      await clickSafe('#checkout');
    } catch (e) {
      console.warn('Could not click checkout:', e.message);
    }

    // Wait for checkout info page stable element then capture
    try {
      await page.waitForLoadState('networkidle', { timeout: 7000 });
    } catch {}
    try {
      await page.waitForSelector(stableSelector.checkout_info, { timeout: 8000 });
    } catch {}
    await captureDom('checkout_info');

    // Fill checkout form
    try {
      await typeSafe('#firstName', 'test');
    } catch (e) {
      console.warn('Could not type firstName:', e.message);
    }
    try {
      await typeSafe('#lastName', 'test');
    } catch (e) {
      console.warn('Could not type lastName:', e.message);
    }
    try {
      await typeSafe('#postalCode', '8796');
    } catch (e) {
      console.warn('Could not type postalCode:', e.message);
    }

    try {
      await clickSafe('#continue');
    } catch (e) {
      console.warn('Could not click continue:', e.message);
    }

    // Wait for checkout overview stable element then capture
    try {
      await page.waitForLoadState('networkidle', { timeout: 7000 });
    } catch {}
    try {
      await page.waitForSelector(stableSelector.checkout_overview, { timeout: 8000 });
    } catch {}
    await captureDom('checkout_overview');

    // Scenario: Complete checkout and return to products
    try {
      await clickSafe('#finish');
    } catch (e) {
      console.warn('Could not click finish:', e.message);
    }

    // Wait for checkout complete stable element then capture
    try {
      await page.waitForLoadState('networkidle', { timeout: 7000 });
    } catch {}
    try {
      await page.waitForSelector(stableSelector.checkout_complete, { timeout: 8000 });
    } catch {}
    await captureDom('checkout_complete');

    // Click back to products
    try {
      await clickSafe('#back-to-products');
    } catch (e) {
      console.warn('Could not click back-to-products:', e.message);
    }

    // Wait for inventory page after finish then capture
    try {
      await page.waitForLoadState('networkidle', { timeout: 7000 });
    } catch {}
    try {
      await page.waitForSelector(stableSelector.inventory_after_finish, { timeout: 8000 });
    } catch {}
    await captureDom('inventory_after_finish');

    // Scenario: Logout from the application
    try {
      await clickSafe('#react-burger-menu-btn');
    } catch (e) {
      console.warn('Could not click burger menu button:', e.message);
    }

    // Try to wait for the logout link then click
    try {
      await page.waitForSelector('#logout_sidebar_link', { timeout: 5000 });
      await clickSafe('#logout_sidebar_link');
    } catch (e) {
      // fallback: try clicking visible logout links
      try {
        await clickSafe('a#logout_sidebar_link');
      } catch (e2) {
        console.warn('Could not click logout link:', e2.message);
      }
    }

    // Wait for login page after logout then capture
    try {
      await page.waitForLoadState('networkidle', { timeout: 7000 });
    } catch {}
    try {
      await page.waitForSelector(stableSelector.login_after_logout, { timeout: 8000 });
    } catch {}
    await captureDom('login_after_logout');
  } catch (e) {
    console.warn('Unexpected error in main flow:', e.message);
  }

  // Save DOM list to JSON file
  try {
    fs.writeFileSync(domFilePath, JSON.stringify(domList, null, 2), 'utf-8');
  } catch (e) {
    console.warn('Failed to write DOM file:', e.message);
  }

  // Copy the running script to output path
  try {
    // __filename should point to this script file when executed
    if (typeof __filename !== 'undefined') {
      try {
        fs.copyFileSync(__filename, scriptFilePath);
      } catch (e) {
        console.warn('Could not copy script file:', e.message);
      }
    } else {
      console.warn('__filename is undefined; cannot copy script file.');
    }
  } catch (e) {
    console.warn('Error copying script file:', e.message);
  }

  // Close browser
  try {
    await browser.close();
  } catch (e) {
    console.warn('Error closing browser:', e.message);
  }

  // Final required output
  console.log(`Execution completed. DOM file saved to: ${domFilePath}`);
})();