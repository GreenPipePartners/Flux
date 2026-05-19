#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urljoin

from selenium import webdriver
from selenium.common.exceptions import ElementClickInterceptedException, TimeoutException
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait


DEFAULT_GATEWAY_URL = "http://localhost:8088"


@dataclass(frozen=True)
class IgnitionActivationConfig:
    gateway_url: str
    username: str
    password: str
    headless: bool
    timeout_seconds: int
    keep_open: bool
    debug_dir: Path | None


def main() -> int:
    config = parse_args()
    driver = build_driver(config)
    try:
        try:
            activate_ignition(driver, config)
        except Exception:
            write_debug_artifacts(driver, config)
            raise
        if config.keep_open:
            input("Browser left open. Press Enter to close it.")
        return 0
    finally:
        if not config.keep_open:
            driver.quit()


def parse_args() -> IgnitionActivationConfig:
    parser = argparse.ArgumentParser(description="Log into an Ignition Gateway and click Activate Ignition.")
    parser.add_argument("--gateway-url", default=os.getenv("IGNITION_GATEWAY_URL", DEFAULT_GATEWAY_URL))
    parser.add_argument("--username", default=os.getenv("IGNITION_USERNAME") or os.getenv("IGNITION_USER", "admin"))
    parser.add_argument("--password", default=os.getenv("IGNITION_PASSWORD", "password"))
    parser.add_argument("--headed", action="store_true", help="Show the browser window instead of running headless.")
    parser.add_argument("--timeout", type=int, default=int(os.getenv("IGNITION_SELENIUM_TIMEOUT", "30")))
    parser.add_argument("--keep-open", action="store_true", help="Leave the browser open after clicking the button.")
    parser.add_argument("--debug-dir", default=os.getenv("IGNITION_SELENIUM_DEBUG_DIR", "/tmp/ignition-selenium"))
    args = parser.parse_args()

    if not args.username:
        parser.error("Provide --username or IGNITION_USERNAME.")
    if not args.password:
        parser.error("Provide --password or IGNITION_PASSWORD.")

    return IgnitionActivationConfig(
        gateway_url=args.gateway_url.rstrip("/"),
        username=args.username,
        password=args.password,
        headless=not args.headed,
        timeout_seconds=args.timeout,
        keep_open=args.keep_open,
        debug_dir=Path(args.debug_dir) if args.debug_dir else None,
    )


def build_driver(config: IgnitionActivationConfig) -> WebDriver:
    options = ChromeOptions()
    if config.headless:
        options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920,1080")
    driver = webdriver.Chrome(options=options)
    driver.set_window_size(1920, 1080)
    return driver


def activate_ignition(driver: WebDriver, config: IgnitionActivationConfig) -> None:
    wait = WebDriverWait(driver, config.timeout_seconds)
    driver.get(urljoin(config.gateway_url + "/", "web/home"))

    if login_link_present(driver, timeout_seconds=5) or login_form_present(driver, timeout_seconds=2):
        login(driver, config, wait)

    if click_reset_if_present(driver, timeout_seconds=3):
        print("Clicked Reset Trial.")
        return

    activate_button = first_clickable(
        driver,
        wait,
        [
            (By.CSS_SELECTOR, "button[data-label='Activate Ignition']"),
            (By.XPATH, "//button[normalize-space()='Activate Ignition']"),
            (By.XPATH, "//a[normalize-space()='Activate Ignition']"),
            (By.XPATH, "//*[self::button or self::a][contains(normalize-space(), 'Activate Ignition')]"),
            (By.XPATH, "//*[contains(normalize-space(), 'Activate Ignition') and not(self::script)]"),
        ],
    )
    click_element(driver, activate_button)
    if click_reset_if_present(driver, timeout_seconds=config.timeout_seconds):
        print("Clicked Reset Trial.")
        return

    print("Clicked Activate Ignition.")


def login_link_present(driver: WebDriver, *, timeout_seconds: int) -> bool:
    try:
        WebDriverWait(driver, timeout_seconds).until(
            EC.element_to_be_clickable((By.XPATH, "//*[self::button or self::a][normalize-space()='Log In']"))
        )
    except TimeoutException:
        return False
    return True


def click_reset_if_present(driver: WebDriver, *, timeout_seconds: int) -> bool:
    locators = [
        (By.CSS_SELECTOR, "button[data-label='Reset Trial']"),
        (By.XPATH, "//*[self::button or self::a][normalize-space()='Reset Trial']"),
        (By.CSS_SELECTOR, "button[data-label*='Reset' i]"),
        (By.XPATH, "//*[self::button or self::a][contains(normalize-space(), 'Reset Trial')]"),
        (By.XPATH, "//*[self::button or self::a][contains(normalize-space(), 'Reset Ignition')]"),
        (By.XPATH, "//*[self::button or self::a][contains(normalize-space(), 'Reset')]"),
    ]
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        for locator in locators:
            matches = driver.find_elements(*locator)
            for element in matches:
                if element.is_displayed() and element.is_enabled():
                    click_element(driver, element)
                    click_confirmation_if_present(driver)
                    return True
        time.sleep(0.25)
    return False


def click_confirmation_if_present(driver: WebDriver) -> None:
    for locator in [
        (By.XPATH, "//*[self::button or self::a][normalize-space()='Reset']"),
        (By.XPATH, "//*[self::button or self::a][normalize-space()='Confirm']"),
        (By.XPATH, "//*[self::button or self::a][normalize-space()='OK']"),
        (By.XPATH, "//*[self::button or self::a][normalize-space()='Yes']"),
    ]:
        if click_if_present(driver, locator, timeout_seconds=2):
            return


def write_debug_artifacts(driver: WebDriver, config: IgnitionActivationConfig) -> None:
    if config.debug_dir is None:
        return
    config.debug_dir.mkdir(parents=True, exist_ok=True)
    (config.debug_dir / "current_url.txt").write_text(driver.current_url, encoding="utf-8")
    (config.debug_dir / "title.txt").write_text(driver.title, encoding="utf-8")
    (config.debug_dir / "page.html").write_text(driver.page_source, encoding="utf-8")
    try:
        body = driver.find_element(By.TAG_NAME, "body").text
    except Exception:
        body = ""
    (config.debug_dir / "body.txt").write_text(body, encoding="utf-8")
    driver.save_screenshot(str(config.debug_dir / "screenshot.png"))
    print("Wrote Selenium debug artifacts to %s" % config.debug_dir, file=sys.stderr)


def login_form_present(driver: WebDriver, *, timeout_seconds: int) -> bool:
    try:
        WebDriverWait(driver, timeout_seconds).until(any_present(login_field_locators()))
    except TimeoutException:
        return False
    return True


def login(driver: WebDriver, config: IgnitionActivationConfig, wait: WebDriverWait) -> None:
    click_if_present(driver, (By.XPATH, "//*[self::button or self::a][normalize-space()='Log In']"), timeout_seconds=2)
    username = first_visible(driver, wait, login_field_locators())
    username.clear()
    username.send_keys(config.username, Keys.ENTER)

    click_if_present(
        driver,
        (By.XPATH, "//*[self::button or self::input][normalize-space()='CONTINUE' or @value='CONTINUE']"),
        timeout_seconds=2,
    )

    password = first_visible(driver, wait, password_field_locators())
    password.clear()
    password.send_keys(config.password, Keys.ENTER)
    wait.until_not(any_present([(By.CSS_SELECTOR, "input[type='password']")]))


def login_field_locators() -> list[tuple[str, str]]:
    return [
        (By.CSS_SELECTOR, "input[name='username']"),
        (By.CSS_SELECTOR, "input[name='user']"),
        (By.CSS_SELECTOR, "input[id*='username' i]"),
        (By.CSS_SELECTOR, "input[id*='user' i]"),
        (By.CSS_SELECTOR, "input[type='text']"),
        (By.CSS_SELECTOR, "input[type='email']"),
    ]


def password_field_locators() -> list[tuple[str, str]]:
    return [
        (By.CSS_SELECTOR, "input[name='password']"),
        (By.CSS_SELECTOR, "input[type='password']"),
        (By.CSS_SELECTOR, "input[id*='password' i]"),
    ]


def click_if_present(driver: WebDriver, locator: tuple[str, str], *, timeout_seconds: int) -> bool:
    try:
        WebDriverWait(driver, timeout_seconds).until(EC.element_to_be_clickable(locator)).click()
    except TimeoutException:
        return False
    return True


def click_element(driver: WebDriver, element: WebElement) -> None:
    driver.execute_script("arguments[0].scrollIntoView({block: 'center', inline: 'center'});", element)
    try:
        element.click()
    except ElementClickInterceptedException:
        driver.execute_script("arguments[0].click();", element)


def first_visible(driver: WebDriver, wait: WebDriverWait, locators: list[tuple[str, str]]) -> WebElement:
    return first_match(driver, wait, locators, EC.visibility_of_element_located)


def first_clickable(driver: WebDriver, wait: WebDriverWait, locators: list[tuple[str, str]]) -> WebElement:
    return first_match(driver, wait, locators, EC.element_to_be_clickable)


def first_match(driver: WebDriver, wait: WebDriverWait, locators: list[tuple[str, str]], condition_factory) -> WebElement:
    last_error: TimeoutException | None = None
    for locator in locators:
        try:
            return wait.until(condition_factory(locator))
        except TimeoutException as exc:
            last_error = exc
    raise TimeoutException("No matching element found for locators: %s" % locators) from last_error


def any_present(locators: list[tuple[str, str]]):
    def predicate(driver: WebDriver):
        for locator in locators:
            matches = driver.find_elements(*locator)
            if matches:
                return matches[0]
        return False

    return predicate


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("Interrupted.", file=sys.stderr)
        raise SystemExit(130)
