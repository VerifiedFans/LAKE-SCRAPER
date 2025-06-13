from flask import Flask, render_template, request, jsonify, send_file
import os
import csv
import time
import json
import re
from datetime import datetime, timedelta
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.keys import Keys
from selenium.common.exceptions import TimeoutException, NoSuchElementException
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor
import logging
import random

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'your-secret-key-here')

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Global variables for scraping status
scraping_status = {
    'is_running': False,
    'artists_processed': 0,
    'concerts_found': 0,
    'unique_venues': set(),
    'current_artist': '',
    'errors': [],
    'debug_info': [],
    'raw_html': '',
    'page_title': '',
    'current_url': ''
}

concert_data = []

def get_chrome_options():
    """Configure Chrome to be as human-like as possible"""
    chrome_options = Options()
    
    # Essential for deployment
    chrome_options.add_argument('--headless')
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    
    # Human-like window size (common laptop resolution)
    chrome_options.add_argument('--window-size=1366,768')
    
    # Anti-detection measures
    chrome_options.add_argument('--disable-blink-features=AutomationControlled')
    chrome_options.add_argument('--disable-extensions')
    chrome_options.add_argument('--disable-plugins')
    chrome_options.add_argument('--disable-default-apps')
    chrome_options.add_argument('--disable-background-timer-throttling')
    chrome_options.add_argument('--disable-backgrounding-occluded-windows')
    chrome_options.add_argument('--disable-renderer-backgrounding')
    chrome_options.add_argument('--disable-features=TranslateUI')
    chrome_options.add_argument('--disable-ipc-flooding-protection')
    
    # More realistic user agent (latest Chrome)
    chrome_options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
    
    # Disable automation indicators
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation", "enable-logging"])
    chrome_options.add_experimental_option('useAutomationExtension', False)
    
    # Add some preferences to look more human
    prefs = {
        "profile.default_content_setting_values": {
            "notifications": 2,  # Block notifications
            "geolocation": 2     # Block location sharing
        },
        "profile.managed_default_content_settings": {
            "images": 1  # Allow images
        }
    }
    chrome_options.add_experimental_option("prefs", prefs)
    
    return chrome_options

def human_like_delay(min_seconds=1, max_seconds=3):
    """Random delay to mimic human thinking/reading time"""
    delay = random.uniform(min_seconds, max_seconds)
    time.sleep(delay)
    return delay

def human_like_scroll(driver, debug_info):
    """Mimic human scrolling behavior"""
    try:
        # Random scroll pattern
        scroll_actions = [
            lambda: driver.execute_script("window.scrollBy(0, 300);"),  # Scroll down
            lambda: driver.execute_script("window.scrollBy(0, -100);"), # Scroll back up a bit  
            lambda: driver.execute_script("window.scrollBy(0, 500);"),  # Scroll down more
            lambda: driver.execute_script("window.scrollTo(0, 0);"),    # Back to top
        ]
        
        # Pick 2-3 random scroll actions
        actions_to_perform = random.sample(scroll_actions, random.randint(2, 3))
        
        for action in actions_to_perform:
            action()
            human_like_delay(0.5, 1.5)  # Pause between scrolls
            
        debug_info.append("🖱️ Performed human-like scrolling")
        
    except Exception as e:
        debug_info.append(f"❌ Error during scrolling: {e}")

def human_like_mouse_movement(driver, element, debug_info):
    """Move mouse to element in a human-like way"""
    try:
        actions = ActionChains(driver)
        
        # Move to a random nearby position first
        viewport_width = driver.execute_script("return window.innerWidth;")
        viewport_height = driver.execute_script("return window.innerHeight;")
        
        random_x = random.randint(100, min(500, viewport_width - 100))
        random_y = random.randint(100, min(300, viewport_height - 100))
        
        # Move to random position first
        actions.move_by_offset(random_x, random_y)
        actions.pause(random.uniform(0.1, 0.3))
        
        # Then move to the actual element
        actions.move_to_element(element)
        actions.pause(random.uniform(0.2, 0.5))
        
        actions.perform()
        debug_info.append("🖱️ Performed human-like mouse movement")
        
    except Exception as e:
        debug_info.append(f"❌ Error during mouse movement: {e}")

def scrape_artist_concerts(artist_url, max_pages=3):
    """Human-like scraper that mimics real user behavior"""
    driver = None
    concerts = []
    debug_info = []
    
    try:
        # Initialize driver with human-like options
        chrome_options = get_chrome_options()
        driver = webdriver.Chrome(options=chrome_options)
        
        # Hide webdriver properties
        driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        driver.execute_script("Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]})")
        driver.execute_script("Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']})")
        
        debug_info.append("✅ Initialized human-like Chrome driver")
        
        # Navigate to the page
        debug_info.append(f"🌐 Navigating to: {artist_url}")
        driver.get(artist_url)
        
        # Mimic human page load waiting - look around first
        human_like_delay(2, 4)
        debug_info.append("⏳ Simulated human page load waiting")
        
        # Check if page loaded
        try:
            WebDriverWait(driver, 20).wait(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
            debug_info.append("✅ Page body loaded")
        except TimeoutException:
            debug_info.append("❌ Timeout waiting for page body")
            return concerts
        
        # Get page information
        page_title = driver.title
        current_url = driver.current_url
        scraping_status['page_title'] = page_title
        scraping_status['current_url'] = current_url
        
        debug_info.append(f"📄 Page title: '{page_title}'")
        debug_info.append(f"📄 Current URL: {current_url}")
        
        # Check for bot detection
        page_source = driver.page_source.lower()
        bot_indicators = ['access denied', 'blocked', 'captcha', 'forbidden', 'bot detected']
        detected_indicators = [indicator for indicator in bot_indicators if indicator in page_source]
        
        if detected_indicators:
            debug_info.append(f"🚫 Possible bot detection: {detected_indicators}")
        else:
            debug_info.append("✅ No obvious bot detection indicators")
        
        # Capture HTML sample
        scraping_status['raw_html'] = driver.page_source[:15000]
        debug_info.append(f"📄 Captured {len(driver.page_source)} characters of HTML")
        
        # Extract artist name
        url_parts = artist_url.split('/')[-1].split('-')
        if len(url_parts) > 1:
            artist_name = ' '.join(url_parts[1:]).title()
        else:
            artist_name = artist_url.split('/')[-1].replace('-', ' ').title()
        
        debug_info.append(f"🎤 Artist: {artist_name}")
        
        # Human-like browsing behavior - scroll around and look at the page
        human_like_scroll(driver, debug_info)
        
        # Wait like a human would while reading
        human_like_delay(1, 3)
        
        # Look for the "Past" tab in a human-like way
        debug_info.append("🔍 Looking for 'Past' tab...")
        
        past_clicked = False
        try:
            # First, scroll to make sure we can see the navigation area
            driver.execute_script("window.scrollTo(0, 200);")
            human_like_delay(0.5, 1)
            
            # Look for Past tab with multiple strategies
            past_selectors = [
                "//a[normalize-space(text())='Past']",
                "//div[normalize-space(text())='Past']", 
                "//span[normalize-space(text())='Past']",
                "//button[normalize-space(text())='Past']",
                "//*[contains(text(), 'Past') and not(contains(text(), 'Concerts'))]"
            ]
            
            past_element = None
            for selector in past_selectors:
                try:
                    elements = driver.find_elements(By.XPATH, selector)
                    for elem in elements:
                        if elem.is_displayed() and elem.is_enabled():
                            past_element = elem
                            debug_info.append(f"✅ Found Past element: {selector}")
                            break
                    if past_element:
                        break
                except:
                    continue
            
            if past_element:
                # Human-like interaction with the Past tab
                debug_info.append("🖱️ Preparing to click Past tab...")
                
                # Scroll element into view
                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", past_element)
                human_like_delay(0.5, 1)
                
                # Move mouse to element in human-like way
                human_like_mouse_movement(driver, past_element, debug_info)
                
                # Click with human-like pause
                human_like_delay(0.2, 0.5)
                
                try:
                    # Try regular click first
                    past_element.click()
                    past_clicked = True
                    debug_info.append("✅ Clicked Past tab with regular click")
                except:
                    try:
                        # Try JavaScript click if regular click fails
                        driver.execute_script("arguments[0].click();", past_element)
                        past_clicked = True
                        debug_info.append("✅ Clicked Past tab with JavaScript click")
                    except Exception as e:
                        debug_info.append(f"❌ Failed to click Past tab: {e}")
                
                if past_clicked:
                    # Human-like waiting for content to load
                    debug_info.append("⏳ Waiting for Past concerts to load...")
                    human_like_delay(3, 6)
                    
                    # Scroll to see new content
                    driver.execute_script("window.scrollBy(0, 300);")
                    human_like_delay(1, 2)
            
            else:
                debug_info.append("❌ Could not find any Past tab element")
                
        except Exception as e:
            debug_info.append(f"❌ Error finding/clicking Past tab: {e}")
        
        # Now extract concert data
        debug_info.append("🎵 Extracting concert data...")
        
        # Wait for any dynamic content to load
        human_like_delay(2, 4)
        
        # Get all text content from the page
        try:
            body_text = driver.find_element(By.TAG_NAME, "body").text
            debug_info.append(f"📝 Body text length: {len(body_text)} characters")
            
            if body_text:
                # Sample of content for debugging
                debug_info.append(f"📝 Text sample: {body_text[:300]}...")
                
                # Look for concert patterns in the text
                lines = [line.strip() for line in body_text.split('\n') if line.strip()]
                concert_candidates = []
                
                # Find lines that look like concerts
                for i, line in enumerate(lines):
                    # Look for venue indicators
                    venue_keywords = ['Baptist', 'Church', 'Center', 'Hall', 'Theater', 'Arena', 'Stadium', 'Civic', 'Memorial', 'Community', 'Gospel', 'Quartet']
                    has_venue = any(keyword in line for keyword in venue_keywords)
                    
                    # Look for date indicators
                    months = ['JAN', 'FEB', 'MAR', 'APR', 'MAY', 'JUN', 'JUL', 'AUG', 'SEP', 'OCT', 'NOV', 'DEC']
                    has_date = any(month in line.upper() for month in months)
                    
                    # Look for location indicators (City, ST)
                    has_location = bool(re.search(r'[A-Za-z\s]+,\s*[A-Z]{2}\b', line))
                    
                    if has_venue or has_date or has_location:
                        # Get context around this line
                        context_start = max(0, i-2)
                        context_end = min(len(lines), i+3)
                        context = lines[context_start:context_end]
                        concert_candidates.append({
                            'main_line': line,
                            'context': context,
                            'line_index': i
                        })
                
                debug_info.append(f"🎯 Found {len(concert_candidates)} potential concert lines")
                
                # Process concert candidates
                processed_venues = set()  # Avoid duplicates
                
                for candidate in concert_candidates[:20]:  # Limit to first 20
                    try:
                        context_text = '\n'.join(candidate['context'])
                        debug_info.append(f"📋 Processing: {candidate['main_line'][:100]}...")
                        
                        # Extract venue name
                        venue_name = ""
                        for line in candidate['context']:
                            if any(keyword in line for keyword in venue_keywords):
                                venue_name = line.strip()
                                break
                        
                        # Extract date
                        date_str = ""
                        for line in candidate['context']:
                            if any(month in line.upper() for month in months):
                                date_str = line.strip()
                                break
                        
                        # Extract location
                        venue_address = ""
                        for line in candidate['context']:
                            location_match = re.search(r'([A-Za-z\s]+,\s*[A-Z]{2})\b', line)
                            if location_match:
                                venue_address = location_match.group(1).strip()
                                break
                        
                        # Use main line as venue if no specific venue found
                        if not venue_name:
                            venue_name = candidate['main_line']
                        
                        # Clean up venue name
                        venue_name = re.sub(r'\s+', ' ', venue_name).strip()
                        
                        # Only add if we have a substantial venue name and haven't seen it before
                        if venue_name and len(venue_name) > 3 and venue_name not in processed_venues:
                            # Filter out non-venue lines
                            skip_keywords = ['Set Reminder', 'Tickets', 'Free Entry', 'Follow', 'More Dates', 'Show More']
                            if not any(skip in venue_name for skip in skip_keywords):
                                concert = {
                                    'artist_name': artist_name,
                                    'venue_name': venue_name,
                                    'venue_address': venue_address or 'Not specified',
                                    'concert_date': date_str or 'Date not found'
                                }
                                
                                concerts.append(concert)
                                processed_venues.add(venue_name)
                                debug_info.append(f"   ✅ Added: {venue_name} | {date_str} | {venue_address}")
                        
                    except Exception as e:
                        debug_info.append(f"   ❌ Error processing candidate: {e}")
                        continue
                
        except Exception as e:
            debug_info.append(f"❌ Error extracting text content: {e}")
        
        # Look for "Show More Dates" button and click it (human-like)
        for page_num in range(1, max_pages):
            debug_info.append(f"🔍 Looking for 'Show More Dates' button (page {page_num + 1})...")
            
            try:
                # Scroll to bottom to find the button
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                human_like_delay(1, 2)
                
                # Look for more dates button
                more_selectors = [
                    "//button[contains(text(), 'Show More Dates')]",
                    "//a[contains(text(), 'Show More Dates')]",
                    "//div[contains(text(), 'Show More Dates')]",
                    "//*[contains(text(), 'More Dates')]",
                    "//*[contains(text(), 'Load More')]"
                ]
                
                more_button = None
                for selector in more_selectors:
                    try:
                        elements = driver.find_elements(By.XPATH, selector)
                        for elem in elements:
                            if elem.is_displayed() and elem.is_enabled():
                                more_button = elem
                                break
                        if more_button:
                            break
                    except:
                        continue
                
                if more_button:
                    debug_info.append("✅ Found 'Show More Dates' button")
                    
                    # Human-like interaction
                    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", more_button)
                    human_like_delay(0.5, 1)
                    
                    # Move mouse and click
                    human_like_mouse_movement(driver, more_button, debug_info)
                    human_like_delay(0.3, 0.7)
                    
                    try:
                        more_button.click()
                        debug_info.append("✅ Clicked 'Show More Dates' button")
                        
                        # Wait for new content like a human would
                        human_like_delay(3, 6)
                        
                        # TODO: Extract additional concerts from new content
                        # (Same logic as above could be repeated here)
                        
                    except Exception as e:
                        debug_info.append(f"❌ Failed to click More Dates button: {e}")
                        break
                else:
                    debug_info.append("❌ No 'Show More Dates' button found")
                    break
                    
            except Exception as e:
                debug_info.append(f"❌ Error looking for More Dates button: {e}")
                break
        
        # Store debug info
        scraping_status['debug_info'] = debug_info
        
        debug_info.append(f"🎯 FINAL RESULT: Found {len(concerts)} concerts for {artist_name}")
        logger.info(f"Human-like scraping completed for {artist_name}: {len(concerts)} concerts")
        
        return concerts
        
    except Exception as e:
        error_msg = f"❌ Critical error in human-like scraping {artist_url}: {e}"
        debug_info.append(error_msg)
        scraping_status['debug_info'] = debug_info
        logger.error(error_msg)
        return concerts
        
    finally:
        if driver:
            try:
                # Human-like exit - don't just quit immediately
                human_like_delay(1, 2)
                driver.quit()
            except:
                pass

def scrape_multiple_artists(artist_urls):
    """Scrape concerts for multiple artists with human-like delays between them"""
    global scraping_status, concert_data
    
    scraping_status['is_running'] = True
    scraping_status['artists_processed'] = 0
    scraping_status['concerts_found'] = 0
    scraping_status['unique_venues'] = set()
    scraping_status['errors'] = []
    scraping_status['debug_info'] = []
    scraping_status['raw_html'] = ''
    scraping_status['page_title'] = ''
    scraping_status['current_url'] = ''
    concert_data = []
    
    try:
        for i, url in enumerate(artist_urls):
            if not scraping_status['is_running']:
                break
                
            scraping_status['current_artist'] = url.split('/')[-1].replace('-', ' ').title()
            logger.info(f"Processing artist {i+1}/{len(artist_urls)}: {scraping_status['current_artist']}")
            
            try:
                concerts = scrape_artist_concerts(url.strip())
                concert_data.extend(concerts)
                
                scraping_status['concerts_found'] += len(concerts)
                for concert in concerts:
                    scraping_status['unique_venues'].add(concert['venue_name'])
                    
            except Exception as e:
                error_msg = f"Error processing {url}: {str(e)}"
                scraping_status['errors'].append(error_msg)
                logger.error(error_msg)
            
            scraping_status['artists_processed'] += 1
            
            # Human-like delay between artists (like switching tabs)
            if i < len(artist_urls) - 1:  # Not the last artist
                delay = random.uniform(5, 15)  # 5-15 seconds between artists
                logger.info(f"Human-like delay: {delay:.1f} seconds before next artist")
                time.sleep(delay)
            
    except Exception as e:
        logger.error(f"Error in scraping process: {e}")
        scraping_status['errors'].append(f"General error: {str(e)}")
    
    finally:
        scraping_status['is_running'] = False
        scraping_status['current_artist'] = ''

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/start_scraping', methods=['POST'])
def start_scraping():
    global scraping_status
    
    if scraping_status['is_running']:
        return jsonify({'error': 'Scraping already in progress'}), 400
    
    data = request.json
    artist_urls = data.get('urls', [])
    
    if not artist_urls:
        return jsonify({'error': 'No URLs provided'}), 400
    
    # Validate URLs
    valid_urls = []
    invalid_urls = []
    
    for url in artist_urls:
        url = url.strip()
        if 'bandsintown.com' in url and '/a/' in url:
            path_part = url.split('/a/')[-1]
            if '-' in path_part and path_part.split('-')[0].isdigit():
                valid_urls.append(url)
            else:
                invalid_urls.append(url)
        else:
            invalid_urls.append(url)
    
    if invalid_urls:
        error_msg = f"Invalid URLs (need format like '/a/147132-artist-name'): {', '.join(invalid_urls[:3])}"
        if len(invalid_urls) > 3:
            error_msg += f" and {len(invalid_urls) - 3} more"
        return jsonify({'error': error_msg}), 400
    
    if not valid_urls:
        return jsonify({'error': 'No valid Bandsintown URLs provided. Use format: https://www.bandsintown.com/a/123456-artist-name'}), 400
    
    # Start scraping
    thread = threading.Thread(target=scrape_multiple_artists, args=(valid_urls,))
    thread.daemon = True
    thread.start()
    
    return jsonify({'message': 'Scraping started', 'total_artists': len(valid_urls)})

@app.route('/scraping_status')
def get_scraping_status():
    return jsonify({
        'is_running': scraping_status['is_running'],
        'artists_processed': scraping_status['artists_processed'],
        'concerts_found': scraping_status['concerts_found'],
        'unique_venues': len(scraping_status['unique_venues']),
        'current_artist': scraping_status['current_artist'],
        'errors': scraping_status['errors'],
        'debug_info': scraping_status.get('debug_info', []),
        'page_title': scraping_status.get('page_title', ''),
        'current_url': scraping_status.get('current_url', '')
    })

@app.route('/stop_scraping', methods=['POST'])
def stop_scraping():
    global scraping_status
    scraping_status['is_running'] = False
    return jsonify({'message': 'Scraping stopped'})

@app.route('/download_csv')
def download_csv():
    if not concert_data:
        return jsonify({'error': 'No concert data available to download'}), 400
    
    temp_file = tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.csv', newline='')
    
    try:
        writer = csv.DictWriter(temp_file, fieldnames=['artist_name', 'venue_name', 'venue_address', 'concert_date'])
        writer.writeheader()
        writer.writerows(concert_data)
        temp_file.close()
        
        return send_file(temp_file.name, 
                        as_attachment=True, 
                        download_name=f'bandsintown_concerts_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv',
                        mimetype='text/csv')
    
    except Exception as e:
        logger.error(f"Error creating CSV: {e}")
        return jsonify({'error': 'Failed to create CSV file'}), 500

@app.route('/debug_info')
def get_debug_info():
    return jsonify({
        'debug_info': scraping_status.get('debug_info', []),
        'concert_data': concert_data,
        'concert_count': len(concert_data),
        'page_title': scraping_status.get('page_title', ''),
        'current_url': scraping_status.get('current_url', '')
    })

@app.route('/raw_html')
def get_raw_html():
    return jsonify({
        'raw_html': scraping_status.get('raw_html', ''),
        'html_length': len(scraping_status.get('raw_html', '')),
        'page_title': scraping_status.get('page_title', ''),
        'current_url': scraping_status.get('current_url', '')
    })

@app.route('/health')
def health_check():
    return jsonify({'status': 'healthy', 'timestamp': datetime.now().isoformat()})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
