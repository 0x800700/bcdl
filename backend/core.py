import os
import re
import time
import json
import logging
from playwright.sync_api import sync_playwright

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class BandcampScraper:
    def __init__(self, download_dir="/app/downloads"):
        self.download_dir = download_dir
        if not os.path.exists(self.download_dir):
            os.makedirs(self.download_dir)

    def sanitize_filename(self, name):
        return re.sub(r'[\\/*?:"<>|]', "", name)

    def scan_artist(self, artist_url, on_album_found=None):
        """Scans an artist page for albums and checks their status."""
        albums = []
        with sync_playwright() as p:
            # Launch browser (headless defaults to True for Docker)
            browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-setuid-sandbox"])
            page = browser.new_page()
            try:
                logger.info(f"Navigating to {artist_url}")
                page.goto(artist_url)
                
                # Ensure we are on the music page if possible, or just scan what's there
                if not artist_url.endswith("/music"):
                    music_link = page.locator("a[href='/music']")
                    if music_link.is_visible():
                        logger.info("Clicking 'Music' link to see all albums")
                        try:
                            music_link.click(force=True)
                        except Exception as e:
                            logger.warning(f"Click failed ({e}), trying direct navigation")
                            # Try to construct the URL
                            if "/music" not in page.url:
                                new_url = page.url.rstrip("/") + "/music"
                                page.goto(new_url)
                        
                        try:
                            page.wait_for_load_state("networkidle", timeout=10000)
                        except:
                            pass

                # Check if it's a track/album page or an artist page (music grid)
                found_links = []
                if page.locator("ol#music-grid").is_visible():
                    # First, ensure we have all items by scrolling to bottom once to trigger any infinite scroll
                    logger.info("Initial scroll to trigger infinite scroll...")
                    last_height = page.evaluate("document.body.scrollHeight")
                    while True:
                        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                        page.wait_for_timeout(1000)
                        new_height = page.evaluate("document.body.scrollHeight")
                        if new_height == last_height:
                            break
                        last_height = new_height

                    # Now iterate through items, scrolling each into view to trigger image load
                    logger.info("Processing grid items...")
                    grid_items = page.locator("ol#music-grid li.music-grid-item").all()
                    
                    for item in grid_items:
                        try:
                            item.scroll_into_view_if_needed()
                            # Small wait for image to load
                            page.wait_for_timeout(100)
                            
                            link = item.locator("a").first
                            href = link.get_attribute("href")
                            
                            # Extract title
                            title_el = item.locator(".title")
                            title = title_el.inner_text().strip() if title_el.is_visible() else "Unknown Title"
                            
                            # Try to get cover image
                            img = item.locator("img").first
                            cover_url = None
                            if img.is_visible():
                                # Force check for data-original first as it's more reliable for lazy loaded
                                cover_url = img.get_attribute("data-original")
                                if not cover_url:
                                    cover_url = img.get_attribute("src")
                            
                            if href:
                                # Handle relative URLs
                                if not href.startswith("http"):
                                    parsed_url =  page.url
                                    base_url = parsed_url.split("/music")[0]
                                    if base_url.endswith("/"):
                                        base_url = base_url[:-1]
                                    
                                    if not href.startswith("/"):
                                        href = "/" + href
                                        
                                    href = base_url + href
                                
                                found_links.append({
                                    "title": title,
                                    "url": href,
                                    "cover_url": cover_url
                                })
                        except Exception as e:
                            logger.warning(f"Error processing item: {e}")
                
                # Now visit each album to check status
                for album in found_links:
                    try:
                        logger.info(f"Checking price for: {album['title']}")
                        page.goto(album['url'])
                        
                        price_status = "paid" # Default to paid
                        
                        # Check for "Free Download" or "name your price"
                        buy_button = page.locator("h4.ft.compound-button button.download-link")
                        
                        if page.locator("h4.ft.compound-button").filter(has_text=re.compile(r"name your price", re.IGNORECASE)).is_visible():
                            price_status = "nyp"
                        elif page.locator("h4.ft.compound-button").filter(has_text=re.compile(r"Free Download", re.IGNORECASE)).is_visible():
                            price_status = "free"
                        elif not buy_button.is_visible():
                             price_status = "unavailable"
                        else:
                             btn_text = buy_button.first.inner_text()
                             if "name your price" in btn_text.lower():
                                 price_status = "nyp"
                             elif "free" in btn_text.lower():
                                 price_status = "free"
                        
                        album['price_status'] = price_status
                        albums.append(album)
                        
                        # Notify callback if provided
                        if on_album_found:
                            on_album_found(album)
                        
                    except Exception as e:
                        logger.error(f"Error checking album {album['title']}: {e}")
                        album['price_status'] = "unknown"
                        albums.append(album)
                        if on_album_found:
                            on_album_found(album)

            except Exception as e:
                logger.error(f"Error scanning: {e}")
            finally:
                browser.close()
        return albums

    def download_album(self, url, target_format="FLAC", progress_callback=None):
        """Downloads a single album."""
        result_status = "failed"
        
        def report(msg):
            logger.info(msg)
            if progress_callback:
                progress_callback(msg)

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-setuid-sandbox"])
            context = browser.new_context(accept_downloads=True)
            page = context.new_page()
            
            try:
                report(f"Processing: {url}")
                page.goto(url)
                
                # Cookie banner
                try:
                    cookie_btn = page.locator("button").filter(has_text="Accept all").first
                    if cookie_btn.is_visible(timeout=3000):
                        cookie_btn.click()
                except:
                    pass

                title = page.locator("h2.trackTitle").first.inner_text().strip()
                report(f"Title: {title}")

                # 1. Direct link check
                try:
                    tralbum_data = page.locator("script[data-tralbum]").get_attribute("data-tralbum")
                    if tralbum_data:
                        data = json.loads(tralbum_data)
                        if data.get("freeDownloadPage"):
                            report("Using direct download link")
                            page.goto(data.get("freeDownloadPage"))
                            return self._handle_download_page(page, title, target_format, report)
                except Exception as e:
                    logger.warning(f"Direct link check failed: {e}")

                # 2. Buy/Free button interaction
                buy_button = page.locator("h4.ft.compound-button button.download-link").filter(has_text=re.compile(r"Buy|Free|Download", re.IGNORECASE)).first
                
                if not buy_button.is_visible():
                    report("No download button found")
                    return "skipped_paid"

                buy_button.click(force=True)

                # Price input
                price_input = page.locator("input#userPrice")
                try:
                    price_input.wait_for(state="visible", timeout=5000)
                except:
                    pass

                if price_input.is_visible():
                    report("Setting price to 0")
                    price_input.fill("0")
                    time.sleep(1)
                    
                    download_link = page.locator("a.download-panel-free-download-link")
                    if download_link.is_visible():
                        download_link.click(force=True)
                        
                        # Check for email requirement
                        try:
                            page.wait_for_load_state("networkidle", timeout=5000)
                        except:
                            pass

                        if "download" in page.url:
                            pass # Good
                        elif page.locator("input#fan_email_address").is_visible():
                            report("Email required, skipping")
                            return "skipped_email"
                    else:
                        if page.locator("input#fan_email_address").is_visible():
                            report("Email required, skipping")
                            return "skipped_email"
                        else:
                            return "failed"
                else:
                    report("No price input found")

                # Handle download page
                return self._handle_download_page(page, title, target_format, report)

            except Exception as e:
                report(f"Error: {e}")
                return "failed"
            finally:
                browser.close()

    def _handle_download_page(self, page, title, target_format, report):
        try:
            report("Waiting for download page...")
            format_dropdown = page.locator("#format-type, .format-type, .formats").first
            format_dropdown.wait_for(state="visible", timeout=10000)
            
            tag_name = format_dropdown.evaluate("el => el.tagName")
            if tag_name == "SELECT":
                format_dropdown.select_option(value=target_format.lower())
            else:
                format_dropdown.click()
                page.locator("li").filter(has_text=target_format).click()
            
            report(f"Selected format: {target_format}")
            
            download_btn = page.locator(".download-item-container a").filter(has_text="Download").first
            report("Preparing download...")
            download_btn.wait_for(state="visible", timeout=60000)
            
            download_url = download_btn.get_attribute("href")
            
            report("Starting download...")
            with page.expect_download(timeout=60000) as download_info:
                try:
                    page.goto(download_url)
                except:
                    pass
            
            download = download_info.value
            suggested_filename = download.suggested_filename
            save_path = os.path.join(self.download_dir, suggested_filename)
            download.save_as(save_path)
            report(f"Downloaded: {suggested_filename}")
            return "downloaded"

        except Exception as e:
            report(f"Download failed: {e}")
            return "failed"
