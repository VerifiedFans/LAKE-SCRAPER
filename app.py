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
import base64

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

def get_stealth_chrome_options():
    """Browse AI inspired Chrome options with maximum stealth"""
    chrome_options = Options()
    
    # Essential for deployment
    chrome_options.add_argument('--headless')
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    
    # Browse AI inspired stealth settings
    chrome_options.add_argument('--window-size=1920,1080')
    chrome_options.add_argument('--start-maximized')
    
    # Advanced anti-detection (Browse AI style)
    chrome_options.add_argument('--disable-blink-features=AutomationControlled')
    chrome_options.add_argument('--disable-extensions')
    chrome_options.add_argument('--no-first-run')
    chrome_options.add_argument('--disable-plugins')
    chrome_options.add_argument('--disable-default-apps')
    chrome_options.add_argument('--disable-background-timer-throttling')
    chrome_options.add_argument('--disable-backgrounding-occluded-windows')
    chrome_options.add_argument('--disable-renderer-backgrounding')
    chrome_options.add_argument('--disable-field-trial-config')
    chrome_options.add_argument('--disable-back-forward-cache')
    chrome_options.add_argument('--disable-background-networking')
    chrome_options.add_argument('--disable-sync')
    chrome_options.add_argument('--disable-features=TranslateUI,BlinkGenPropertyTrees')
    chrome_options.add_argument('--disable-ipc-flooding-protection')
    
    # Network and performance tweaks
    chrome_options.add_argument('--aggressive-cache-discard')
    chrome_options.add_argument('--memory-pressure-off')
    chrome_options.add_argument('--max_old_space_size=4096')
    
    # User agent rotation (Browse AI style)
    user_agents = [
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
        'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36'
    ]
    selected_ua = random.choice(user_agents)
    chrome_options.add_argument(f'--user-agent={selected_ua}')
    
    # Remove automation indicators
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation", "enable-logging"])
    chrome_options.add_experimental_option('useAutomationExtension', False)
    
    # Browse AI style preferences
    prefs = {
        "profile.default_content_setting_values": {
            "notifications": 2,
            "geolocation": 2,
            "media_stream": 2,
        },
        "profile.managed_default_content_settings": {
            "images": 1
        },
        "profile.default_content_settings": {
            "popups": 0
        },
        "credentials_enable_service": False,
        "profile.password_manager_enabled": False
    }
    chrome_options.add_experimental_option("prefs", prefs)
    
    return chrome_options

def inject_stealth_scripts(driver):
    """Inject Browse AI inspired stealth scripts"""
    
    # Hide webdriver property
    driver.execute_script("""
        Object.defineProperty(navigator, 'webdriver', {
            get: () => undefined,
        });
    """)
    
    # Override plugins
    driver.execute_script("""
        Object.defineProperty(navigator, 'plugins', {
            get: () => [1, 2, 3, 4, 5],
        });
    """)
    
    # Override languages
    driver.execute_script("""
        Object.defineProperty(navigator, 'languages', {
            get: () => ['en-US', 'en'],
        });
    """)
    
    # Override permissions
    driver.execute_script("""
        const originalQuery = window.navigator.permissions.query;
        window.navigator.permissions.query = (parameters) => (
            parameters.name === 'notifications' ?
                Promise.resolve({ state: Notification.permission }) :
                originalQuery(parameters)
        );
    """)
    
    # Override chrome runtime
    driver.execute_script("""
        window.chrome = {
            runtime: {},
        };
    """)
    
    # Mock canvas fingerprinting
    driver.execute_script("""
        const getImageData = HTMLCanvasElement.prototype.getContext('2d').constructor.prototype.getImageData;
        HTMLCanvasElement.prototype.getContext('2d').constructor.prototype.getImageData = function(sx, sy, sw, sh) {
            const imageData = getImageData.apply(this, arguments);
            for (let i = 0; i < imageData.data.length; i += 4) {
                imageData.data[i] += Math.floor(Math.random() * 10) - 5;
                imageData.data[i + 1] += Math.floor(Math.random() * 10) - 5;
                imageData.data[i + 2] += Math.floor(Math.random() * 10) - 5;
            }
            return imageData;
        };
    """)

def smart_wait(driver, condition, timeout=20, debug_info=None):
    """Smart waiting with multiple fallback strategies"""
    try:
        WebDriverWait(driver, timeout).until(condition)
        return True
    except TimeoutException:
        if debug_info:
            debug_info.append(f"⏰ Timeout after {timeout}s, trying alternative approach")
        
        # Fallback: wait for any content
        try:
            WebDriverWait(driver, 5).until(
                lambda d: len(d.page_source) > 1000
            )
            return True
        except:
            return False

def extract_concerts_advanced(driver, artist_name, debug_info):
    """Advanced concert extraction using multiple strategies"""
    concerts = []
    
    try:
        # Strategy 1: DOM traversal for structured data
        debug_info.append("🔍 Strategy 1: DOM structure analysis")
        
        # Look for structured concert containers
        concert_selectors = [
            "//div[contains(@class, 'event')]",
            "//div[contains(@class, 'concert')]", 
            "//div[contains(@class, 'show')]",
            "//article",
            "//li[contains(., 'Church') or contains(., 'Center') or contains(., 'Baptist')]"
        ]
        
        found_elements = []
        for selector in concert_selectors:
            try:
                elements = driver.find_elements(By.XPATH, selector)
                found_elements.extend(elements)
                debug_info.append(f"   Found {len(elements)} elements with selector: {selector}")
            except:
                continue
        
        # Process structured elements
        for elem in found_elements[:50]:
            try:
                elem_text = elem.text.strip()
                if elem_text and len(elem_text) > 20:
                    concert = parse_concert_text(elem_text, artist_name)
                    if concert:
                        concerts.append(concert)
                        debug_info.append(f"   ✅ Structured: {concert['venue_name']}")
            except:
                continue
        
        # Strategy 2: Text pattern matching
        debug_info.append("🔍 Strategy 2: Text pattern matching")
        
        body_text = driver.find_element(By.TAG_NAME, "body").text
        concerts.extend(extract_concerts_from_text(body_text, artist_name, debug_info))
        
        # Strategy 3: HTML source parsing
        debug_info.append("🔍 Strategy 3: HTML source parsing")
        
        page_source = driver.page_source
        html_concerts = extract_concerts_from_html(page_source, artist_name, debug_info)
        concerts.extend(html_concerts)
        
        # Remove duplicates
        unique_concerts = []
        seen_venues = set()
        
        for concert in concerts:
            venue_key = f"{concert['venue_name']}-{concert['concert_date']}"
            if venue_key not in seen_venues:
                unique_concerts.append(concert)
                seen_venues.add(venue_key)
        
        debug_info.append(f"🎯 Total unique concerts found: {len(unique_concerts)}")
        return unique_concerts
        
    except Exception as e:
        debug_info.append(f"❌ Error in advanced extraction: {e}")
        return concerts

def parse_concert_text(text, artist_name):
    """Parse individual text blocks for concert information"""
    try:
        lines = [line.strip() for line in text.split('\n') if line.strip()]
        
        venue_name = ""
        venue_address = ""
        date_str = ""
        
        # Venue keywords for gospel/country music
        venue_keywords = [
            'Baptist', 'Church', 'Center', 'Hall', 'Theater', 'Arena', 'Stadium', 
            'Civic', 'Memorial', 'Community', 'Gospel', 'Quartet', 'Auditorium',
            'Convention', 'Coliseum', 'Amphitheater', 'Pavilion'
        ]
        
        # Find venue
        for line in lines:
            if any(keyword in line for keyword in venue_keywords):
                # Clean the line
                cleaned = re.sub(r'\s+', ' ', line).strip()
                if len(cleaned) > 5 and not any(skip in cleaned for skip in ['Set Reminder', 'Tickets', 'Follow']):
                    venue_name = cleaned
                    break
        
        # Find date
        months = ['JAN', 'FEB', 'MAR', 'APR', 'MAY', 'JUN', 'JUL', 'AUG', 'SEP', 'OCT', 'NOV', 'DEC']
        for line in lines:
            if any(month in line.upper() for month in months):
                date_str = line.strip()
                break
        
        # Find location
        for line in lines:
            location_match = re.search(r'([A-Za-z\s]+,\s*[A-Z]{2})\b', line)
            if location_match:
                venue_address = location_match.group(1).strip()
                break
        
        if venue_name:
            return {
                'artist_name': artist_name,
                'venue_name': venue_name,
                'venue_address': venue_address or 'Not specified',
                'concert_date': date_str or 'Date not found'
            }
            
    except Exception as e:
        return None
    
    return None

def extract_concerts_from_text(body_text, artist_name, debug_info):
    """Extract concerts from plain text using pattern matching"""
    concerts = []
    
    try:
        lines = [line.strip() for line in body_text.split('\n') if line.strip()]
        
        # Look for concert patterns
        venue_keywords = ['Baptist', 'Church', 'Center', 'Hall', 'Theater', 'Gospel', 'Quartet']
        months = ['JAN', 'FEB', 'MAR', 'APR', 'MAY', 'JUN', 'JUL', 'AUG', 'SEP', 'OCT', 'NOV', 'DEC']
        
        potential_concerts = []
        
        for i, line in enumerate(lines):
            # Check if line contains venue keywords
            if any(keyword in line for keyword in venue_keywords):
                # Get context around this line
                context_start = max(0, i-3)
                context_end = min(len(lines), i+4)
                context = lines[context_start:context_end]
                
                potential_concerts.append({
                    'venue_line': line,
                    'context': context,
                    'index': i
                })
        
        debug_info.append(f"   Found {len(potential_concerts)} potential venue lines")
        
        for concert_data in potential_concerts[:15]:  # Limit to prevent overload
            concert = parse_concert_text('\n'.join(concert_data['context']), artist_name)
            if concert:
                concerts.append(concert)
                debug_info.append(f"   ✅ Text: {concert['venue_name']}")
        
    except Exception as e:
        debug_info.append(f"   ❌ Text extraction error: {e}")
    
    return concerts

def extract_concerts_from_html(html_source, artist_name, debug_info):
    """Extract concerts from HTML source using regex"""
    concerts = []
    
    try:
        # Look for patterns in HTML that might contain concert data
        # Common patterns: venue names followed by locations
        
        venue_pattern = r'([\w\s]+(Baptist|Church|Center|Hall|Theater|Gospel|Quartet)[\w\s]*)[,\s]*([\w\s]+,\s*[A-Z]{2})'
        matches = re.findall(venue_pattern, html_source, re.IGNORECASE)
        
        debug_info.append(f"   Found {len(matches)} HTML venue patterns")
        
        for match in matches[:10]:  # Limit to prevent overload
            venue_name = match[0].strip()
            venue_address = match[2].strip() if len(match) > 2 else 'Not specified'
            
            if len(venue_name) > 5:
                concerts.append({
                    'artist_name': artist_name,
                    'venue_name': venue_name,
                    'venue_address': venue_address,
                    'concert_date': 'Date not found'
                })
                debug_info.append(f"   ✅ HTML: {venue_name}")
        
    except Exception as e:
        debug_info.append(f"   ❌ HTML extraction error: {e}")
    
    return concerts

def scrape_artist_concerts(artist_url, max_pages=3):
    """Browse AI inspired scraper with advanced evasion"""
    driver = None
    concerts = []
    debug_info = []
    
    try:
        # Initialize stealth driver
        chrome_options = get_stealth_chrome_options()
        driver = webdriver.Chrome(options=chrome_options)
        
        # Inject stealth scripts
        inject_stealth_scripts(driver)
        
        debug_info.append("✅ Initialized Browse AI inspired stealth driver")
        
        # Navigate with random delay
        debug_info.append(f"🌐 Navigating to: {artist_url}")
        driver.get(artist_url)
        
        # Smart waiting for page load
        if not smart_wait(driver, EC.presence_of_element_located((By.TAG_NAME, "body")), 20, debug_info):
            debug_info.append("❌ Failed to load page body")
            return concerts
        
        # Random human-like delay
        delay = random.uniform(3, 7)
        time.sleep(delay)
        debug_info.append(f"⏳ Human-like delay: {delay:.1f}s")
        
        # Get page info
        page_title = driver.title
        current_url = driver.current_url
        scraping_status['page_title'] = page_title
        scraping_status['current_url'] = current_url
        
        debug_info.append(f"📄 Page title: '{page_title}'")
        debug_info.append(f"📄 Current URL: {current_url}")
        
        # Check for bot detection
        page_source = driver.page_source
        scraping_status['raw_html'] = page_source[:15000]
        
        bot_indicators = ['access denied', 'blocked', 'captcha', 'forbidden', 'bot detected', 'cloudflare']
        detected = [indicator for indicator in bot_indicators if indicator in page_source.lower()]
        
        if detected:
            debug_info.append(f"🚫 Bot detection indicators: {detected}")
        else:
            debug_info.append("✅ No bot detection indicators found")
        
        # Extract artist name
        url_parts = artist_url.split('/')[-1].split('-')
        artist_name = ' '.join(url_parts[1:]).title() if len(url_parts) > 1 else 'Unknown Artist'
        debug_info.append(f"🎤 Artist: {artist_name}")
        
        # Browse AI style interaction - multiple click attempts for Past tab
        debug_info.append("🔍 Looking for Past tab (Browse AI style)")
        
        past_clicked = False
        past_strategies = [
            # Strategy 1: Direct text match
            lambda: driver.find_elements(By.XPATH, "//*[normalize-space(text())='Past']"),
            # Strategy 2: Contains text
            lambda: driver.find_elements(By.XPATH, "//*[contains(text(), 'Past')]"),
            # Strategy 3: Case insensitive
            lambda: driver.find_elements(By.XPATH, "//*[contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'past')]"),
            # Strategy 4: Within nav elements
            lambda: driver.find_elements(By.XPATH, "//nav//*[contains(text(), 'Past')] | //ul//*[contains(text(), 'Past')]"),
        ]
        
        for i, strategy in enumerate(past_strategies):
            try:
                elements = strategy()
                debug_info.append(f"   Strategy {i+1}: Found {len(elements)} Past elements")
                
                for elem in elements:
                    if elem.is_displayed() and elem.is_enabled():
                        try:
                            # Scroll to element
                            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", elem)
                            time.sleep(random.uniform(0.5, 1.5))
                            
                            # Try click
                            elem.click()
                            past_clicked = True
                            debug_info.append(f"   ✅ Clicked Past tab with strategy {i+1}")
                            time.sleep(random.uniform(4, 8))
                            break
                            
                        except Exception as e:
                            debug_info.append(f"   ❌ Click failed: {e}")
                            continue
                
                if past_clicked:
                    break
                    
            except Exception as e:
                debug_info.append(f"   ❌ Strategy {i+1} failed: {e}")
                continue
        
        if not past_clicked:
            debug_info.append("⚠️ Could not click Past tab, proceeding with current page")
        
        # Advanced concert extraction
        concerts = extract_concerts_advanced(driver, artist_name, debug_info)
        
        # Try pagination if concerts found
        if concerts and max_pages > 1:
            debug_info.append("🔍 Looking for pagination...")
            
            for page_num in range(1, max_pages):
                try:
                    # Look for "Show More" or pagination buttons
                    more_selectors = [
                        "//*[contains(text(), 'Show More')]",
                        "//*[contains(text(), 'More Dates')]", 
                        "//*[contains(text(), 'Load More')]",
                        "//button[contains(@class, 'load-more')] | //a[contains(@class, 'load-more')]"
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
                        driver.execute_script("arguments[0].scrollIntoView();", more_button)
                        time.sleep(random.uniform(1, 3))
                        more_button.click()
                        debug_info.append(f"✅ Clicked pagination button {page_num}")
                        time.sleep(random.uniform(3, 6))
                        
                        # Extract more concerts
                        additional_concerts = extract_concerts_advanced(driver, artist_name, debug_info)
                        concerts.extend(additional_concerts)
                    else:
                        debug_info.append(f"❌ No pagination button found on page {page_num}")
                        break
                        
                except Exception as e:
                    debug_info.append(f"❌ Pagination error: {e}")
                    break
        
        # Store debug info
        scraping_status['debug_info'] = debug_info
        
        debug_info.append(f"🎯 FINAL RESULT: Found {len(concerts)} concerts for {artist_name}")
        logger.info(f"Browse AI style scraping completed for {artist_name}: {len(concerts)} concerts")
        
        return concerts
        
    except Exception as e:
        error_msg = f"❌ Critical error in Browse AI scraping {artist_url}: {e}"
        debug_info.append(error_msg)
        scraping_status['debug_info'] = debug_info
        logger.error(error_msg)
        return concerts
        
    finally:
        if driver:
            try:
                time.sleep(random.uniform(1, 3))
                driver.quit()
            except:
                pass

def scrape_multiple_artists(artist_urls):
    """Scrape multiple artists with Browse AI inspired delays"""
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
            
            # Browse AI style delays between requests
            if i < len(artist_urls) - 1:
                delay = random.uniform(10, 30)  # 10-30 seconds between artists
                logger.info(f"Browse AI style delay: {delay:.1f} seconds before next artist")
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
