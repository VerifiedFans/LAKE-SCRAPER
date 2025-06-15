from flask import Flask, render_template, request, jsonify, send_file
import os
import csv
import time
import json
import re
import subprocess
import requests
import zipfile
import stat
from datetime import datetime, timedelta
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
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
    'current_url': '',
    'chromedriver_status': 'Not initialized'
}

concert_data = []

def get_chrome_version():
    """Get the installed Chrome version"""
    try:
        result = subprocess.run(['/usr/bin/google-chrome', '--version'], 
                              capture_output=True, text=True)
        version_str = result.stdout.strip()
        # Extract version number (e.g., "Google Chrome 137.0.7151.103" -> "137")
        version_match = re.search(r'(\d+)\.', version_str)
        if version_match:
            return version_match.group(1)
        return None
    except Exception as e:
        logger.error(f"Error getting Chrome version: {e}")
        return None

def download_correct_chromedriver():
    """Download and install the correct ChromeDriver version"""
    try:
        # Get Chrome version
        chrome_version = get_chrome_version()
        if not chrome_version:
            raise Exception("Could not determine Chrome version")
        
        logger.info(f"Chrome version detected: {chrome_version}")
        scraping_status['chromedriver_status'] = f"Chrome version: {chrome_version}"
        
        # Download URL for ChromeDriver
        chromedriver_url = f"https://chromedriver.storage.googleapis.com/LATEST_RELEASE_{chrome_version}"
        
        # Get the exact version
        response = requests.get(chromedriver_url, timeout=10)
        if response.status_code != 200:
            # Try Chrome for Testing API for newer versions
            api_url = "https://googlechromelabs.github.io/chrome-for-testing/last-known-good-versions-with-downloads.json"
            api_response = requests.get(api_url, timeout=10)
            if api_response.status_code == 200:
                data = api_response.json()
                stable_version = data['channels']['Stable']['version']
                major_version = stable_version.split('.')[0]
                if major_version == chrome_version:
                    exact_version = stable_version
                    download_url = f"https://storage.googleapis.com/chrome-for-testing-public/{exact_version}/linux64/chromedriver-linux64.zip"
                else:
                    raise Exception(f"No matching ChromeDriver for Chrome {chrome_version}")
            else:
                raise Exception(f"Could not get ChromeDriver version for Chrome {chrome_version}")
        else:
            exact_version = response.text.strip()
            download_url = f"https://chromedriver.storage.googleapis.com/{exact_version}/chromedriver_linux64.zip"
        
        logger.info(f"Downloading ChromeDriver version: {exact_version}")
        scraping_status['chromedriver_status'] = f"Downloading ChromeDriver {exact_version}"
        
        # Download ChromeDriver
        driver_response = requests.get(download_url, timeout=30)
        if driver_response.status_code != 200:
            raise Exception(f"Failed to download ChromeDriver: {driver_response.status_code}")
        
        # Create temp directory for extraction
        temp_dir = tempfile.mkdtemp()
        zip_path = os.path.join(temp_dir, 'chromedriver.zip')
        
        # Save zip file
        with open(zip_path, 'wb') as f:
            f.write(driver_response.content)
        
        # Extract zip
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(temp_dir)
        
        # Find the chromedriver binary
        chromedriver_path = None
        for root, dirs, files in os.walk(temp_dir):
            for file in files:
                if file == 'chromedriver' or file == 'chromedriver.exe':
                    chromedriver_path = os.path.join(root, file)
                    break
            if chromedriver_path:
                break
        
        if not chromedriver_path:
            raise Exception("ChromeDriver binary not found in downloaded zip")
        
        # Make it executable
        os.chmod(chromedriver_path, stat.S_IRWXU | stat.S_IRGRP | stat.S_IXGRP | stat.S_IROTH | stat.S_IXOTH)
        
        logger.info(f"ChromeDriver installed at: {chromedriver_path}")
        scraping_status['chromedriver_status'] = f"Installed at {chromedriver_path}"
        
        return chromedriver_path
        
    except Exception as e:
        error_msg = f"Failed to download ChromeDriver: {e}"
        logger.error(error_msg)
        scraping_status['chromedriver_status'] = f"Error: {error_msg}"
        return None

def get_chrome_options():
    """Chrome options for stealth mode"""
    chrome_options = Options()
    
    # Essential for deployment
    chrome_options.add_argument('--headless')
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument('--window-size=1366,768')
    
    # Anti-detection
    chrome_options.add_argument('--disable-blink-features=AutomationControlled')
    chrome_options.add_argument('--disable-extensions')
    chrome_options.add_argument('--disable-plugins')
    chrome_options.add_argument('--disable-default-apps')
    chrome_options.add_argument('--disable-background-timer-throttling')
    chrome_options.add_argument('--disable-backgrounding-occluded-windows')
    chrome_options.add_argument('--disable-renderer-backgrounding')
    
    # Real user agent
    chrome_version = get_chrome_version() or "137"
    user_agent = f'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{chrome_version}.0.0.0 Safari/537.36'
    chrome_options.add_argument(f'--user-agent={user_agent}')
    
    # Remove automation indicators
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option('useAutomationExtension', False)
    
    return chrome_options

def human_delay(min_sec=1, max_sec=3):
    """Human-like delay"""
    delay = random.uniform(min_sec, max_sec)
    time.sleep(delay)
    return delay

def extract_concerts_simple(driver, artist_name, debug_info):
    """Simple but effective concert extraction"""
    concerts = []
    
    try:
        # Get all text from the page
        body_text = driver.find_element(By.TAG_NAME, "body").text
        debug_info.append(f"📝 Page text length: {len(body_text)} characters")
        
        if len(body_text) < 100:
            debug_info.append("❌ Very little text found on page")
            return concerts
        
        # Sample of the text
        debug_info.append(f"📝 Text sample: {body_text[:500]}...")
        
        # Split into lines
        lines = [line.strip() for line in body_text.split('\n') if line.strip()]
        debug_info.append(f"📄 Total lines: {len(lines)}")
        
        # Look for gospel/country venue keywords
        venue_keywords = [
            'Baptist', 'Church', 'Center', 'Hall', 'Theater', 'Theatre', 'Arena', 'Stadium',
            'Civic', 'Memorial', 'Community', 'Gospel', 'Quartet', 'Auditorium',
            'Convention', 'Coliseum', 'Amphitheater', 'Pavilion', 'Tabernacle',
            'Academy', 'School', 'College', 'University', 'Fairgrounds'
        ]
        
        # Month abbreviations for dates
        months = ['JAN', 'FEB', 'MAR', 'APR', 'MAY', 'JUN', 'JUL', 'AUG', 'SEP', 'OCT', 'NOV', 'DEC']
        
        # Find lines with venue keywords
        venue_lines = []
        for i, line in enumerate(lines):
            if any(keyword.lower() in line.lower() for keyword in venue_keywords):
                venue_lines.append({'line': line, 'index': i})
        
        debug_info.append(f"🎯 Found {len(venue_lines)} lines with venue keywords")
        
        # Process each venue line
        processed_venues = set()
        
        for venue_data in venue_lines[:30]:  # Process up to 30 potential venues
            try:
                venue_line = venue_data['line']
                line_index = venue_data['index']
                
                # Skip obvious non-venue lines
                skip_terms = ['Set Reminder', 'Tickets', 'Follow', 'More Dates', 'Show More', 'Free Entry', 'View More']
                if any(term in venue_line for term in skip_terms):
                    continue
                
                # Clean the venue name
                venue_name = re.sub(r'\s+', ' ', venue_line).strip()
                
                # Look for date in nearby lines
                date_str = ""
                search_range = 4  # Look 4 lines before and after
                start_idx = max(0, line_index - search_range)
                end_idx = min(len(lines), line_index + search_range + 1)
                
                for nearby_line in lines[start_idx:end_idx]:
                    if any(month in nearby_line.upper() for month in months):
                        date_str = nearby_line.strip()
                        break
                
                # Look for location (City, ST format)
                location_str = ""
                for nearby_line in lines[start_idx:end_idx]:
                    location_match = re.search(r'([A-Za-z\s]+,\s*[A-Z]{2})\b', nearby_line)
                    if location_match:
                        location_str = location_match.group(1).strip()
                        break
                
                # Add if valid and not duplicate
                if (venue_name and 
                    len(venue_name) > 8 and 
                    len(venue_name) < 200 and
                    venue_name not in processed_venues):
                    
                    concert = {
                        'artist_name': artist_name,
                        'venue_name': venue_name,
                        'venue_address': location_str or 'Not specified',
                        'concert_date': date_str or 'Date not found'
                    }
                    
                    concerts.append(concert)
                    processed_venues.add(venue_name)
                    debug_info.append(f"   ✅ Added: {venue_name}")
                    if date_str:
                        debug_info.append(f"      📅 Date: {date_str}")
                    if location_str:
                        debug_info.append(f"      📍 Location: {location_str}")
                
            except Exception as e:
                debug_info.append(f"   ❌ Error processing venue line: {e}")
                continue
        
        debug_info.append(f"🎯 Total concerts found: {len(concerts)}")
        return concerts
        
    except Exception as e:
        debug_info.append(f"❌ Error in concert extraction: {e}")
        return concerts

def scrape_artist_concerts(artist_url, max_retries=2):
    """Scrape concerts with automatic ChromeDriver management"""
    driver = None
    concerts = []
    debug_info = []
    
    # Extract artist name early
    url_parts = artist_url.split('/')[-1].split('-')
    artist_name = ' '.join(url_parts[1:]).title() if len(url_parts) > 1 else 'Unknown Artist'
    debug_info.append(f"🎤 Artist: {artist_name}")
    
    # Download correct ChromeDriver
    chromedriver_path = download_correct_chromedriver()
    if not chromedriver_path:
        debug_info.append("❌ Failed to download correct ChromeDriver")
        return concerts
    
    for attempt in range(max_retries):
        try:
            debug_info.append(f"🚀 Attempt {attempt + 1}/{max_retries}")
            
            # Initialize Chrome driver with correct ChromeDriver
            chrome_options = get_chrome_options()
            service = Service(chromedriver_path)
            
            try:
                driver = webdriver.Chrome(service=service, options=chrome_options)
                debug_info.append("✅ Chrome driver initialized with correct version")
            except Exception as e:
                debug_info.append(f"❌ Chrome driver error: {e}")
                if attempt == max_retries - 1:
                    raise e
                continue
            
            # Hide webdriver property
            driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            
            # Navigate to page
            debug_info.append(f"🌐 Navigating to: {artist_url}")
            logger.info(f"🌐 Navigating to: {artist_url}")
            driver.get(artist_url)
            logger.info(f"✅ GET request completed for: {artist_url}")
            
            # Wait for page load
            delay = human_delay(3, 6)
            debug_info.append(f"⏳ Waiting {delay:.1f}s for page load")
            logger.info(f"⏳ Waiting {delay:.1f}s for page load")
            
            # Check if page loaded
            try:
                WebDriverWait(driver, 15).until(
                    EC.presence_of_element_located((By.TAG_NAME, "body"))
                )
                debug_info.append("✅ Page body loaded")
                logger.info("✅ Page body loaded successfully")
                
                # CHECKPOINT: Confirm we can interact with the page
                logger.info("🔍 CHECKPOINT: Testing page interaction...")
                current_url = driver.current_url
                logger.info(f"🔍 Current URL: {current_url}")
                
            except TimeoutException:
                debug_info.append("❌ Timeout waiting for page load")
                logger.error("❌ Timeout waiting for page load")
                if attempt == max_retries - 1:
                    return concerts
                continue
            except Exception as e:
                debug_info.append(f"❌ Unexpected error during page load: {str(e)}")
                logger.error(f"❌ Unexpected error during page load: {str(e)}")
                if attempt == max_retries - 1:
                    return concerts
                continue
            
            # Get page info
            page_title = driver.title
            current_url = driver.current_url
            scraping_status['page_title'] = page_title
            scraping_status['current_url'] = current_url
            
            debug_info.append(f"📄 Page title: '{page_title}'")
            debug_info.append(f"📄 Current URL: {current_url}")
            
            # Capture HTML sample
            page_source = driver.page_source
            scraping_status['raw_html'] = page_source[:15000]
            debug_info.append(f"📄 HTML captured: {len(page_source)} characters")
            
            # Check for bot detection
            bot_indicators = ['access denied', 'blocked', 'captcha', 'forbidden', 'bot detected']
            detected = [indicator for indicator in bot_indicators if indicator in page_source.lower()]
            
            if detected:
                debug_info.append(f"🚫 Bot detection indicators: {detected}")
                if attempt == max_retries - 1:
                    return concerts
                human_delay(5, 10)  # Wait longer before retry
                continue
            else:
                debug_info.append("✅ No bot detection found")
            
            # Extract artist name
            debug_info.append(f"🎤 Processing: {artist_name}")
            
            # Try to click Past tab
            debug_info.append("🔍 Looking for Past tab in Concerts section...")
            try:
                # Look for the Concerts and tour dates section first
                concert_section_found = False
                try:
                    concert_section = driver.find_element(By.XPATH, "//*[contains(text(), 'Concerts and tour dates')]")
                    debug_info.append("✅ Found 'Concerts and tour dates' section")
                    concert_section_found = True
                except:
                    debug_info.append("⚠️ Could not find 'Concerts and tour dates' section")
                
                # Look for Past tab near Upcoming tab
                past_selectors = [
                    # Look for Past near Upcoming
                    "//div[contains(text(), 'Upcoming')]/following-sibling::*[contains(text(), 'Past')]",
                    "//div[contains(text(), 'Upcoming')]/..//*[contains(text(), 'Past')]",
                    # Direct Past tab searches
                    "//div[normalize-space(text())='Past']",
                    "//span[normalize-space(text())='Past']", 
                    "//a[normalize-space(text())='Past']",
                    "//button[normalize-space(text())='Past']",
                    # Case insensitive
                    "//*[contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'past')]"
                ]
                
                clicked_past = False
                for i, selector in enumerate(past_selectors):
                    try:
                        elements = driver.find_elements(By.XPATH, selector)
                        debug_info.append(f"   Selector {i+1}: Found {len(elements)} Past elements")
                        
                        for element in elements:
                            try:
                                if element.is_displayed() and element.is_enabled():
                                    # Scroll to element
                                    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
                                    human_delay(0.5, 1)
                                    
                                    # Try different click methods
                                    try:
                                        element.click()
                                        clicked_past = True
                                        debug_info.append(f"   ✅ Clicked Past tab with selector {i+1}")
                                        break
                                    except:
                                        # Try JavaScript click
                                        driver.execute_script("arguments[0].click();", element)
                                        clicked_past = True
                                        debug_info.append(f"   ✅ Clicked Past tab with JS (selector {i+1})")
                                        break
                            except Exception as e:
                                debug_info.append(f"   ❌ Element not clickable: {e}")
                                continue
                        
                        if clicked_past:
                            break
                            
                    except Exception as e:
                        debug_info.append(f"   ❌ Selector {i+1} error: {e}")
                        continue
                
                if clicked_past:
                    debug_info.append("✅ Successfully clicked Past tab, waiting for content...")
                    human_delay(4, 7)  # Wait for Past concerts to load
                else:
                    debug_info.append("⚠️ Could not click Past tab, using current page (Upcoming)")
            
            except Exception as e:
                debug_info.append(f"❌ Past tab error: {e}")
            
            # Extract concerts
            debug_info.append("🎵 Extracting concerts...")
            concerts = extract_concerts_simple(driver, artist_name, debug_info)
            
            # Success - break retry loop
            break
            
        except Exception as e:
            error_msg = f"❌ Attempt {attempt + 1} failed: {e}"
            debug_info.append(error_msg)
            
            if attempt == max_retries - 1:
                logger.error(f"All attempts failed for {artist_url}: {e}")
            else:
                debug_info.append(f"🔄 Retrying in 5 seconds...")
                time.sleep(5)
            
        finally:
            if driver:
                try:
                    driver.quit()
                except:
                    pass
                driver = None
    
    # Store debug info
    scraping_status['debug_info'] = debug_info
    
    debug_info.append(f"🎯 FINAL RESULT: Found {len(concerts)} concerts for {artist_name}")
    logger.info(f"Scraping completed for {artist_name}: {len(concerts)} concerts")
    
    return concerts

def scrape_multiple_artists(artist_urls):
    """Scrape multiple artists"""
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
            
            # Delay between artists
            if i < len(artist_urls) - 1:
                delay = random.uniform(10, 25)
                logger.info(f"Waiting {delay:.1f} seconds before next artist")
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
        error_msg = f"Invalid URLs: {', '.join(invalid_urls[:3])}"
        if len(invalid_urls) > 3:
            error_msg += f" and {len(invalid_urls) - 3} more"
        return jsonify({'error': error_msg}), 400
    
    if not valid_urls:
        return jsonify({'error': 'No valid Bandsintown URLs provided'}), 400
    
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
        'current_url': scraping_status.get('current_url', ''),
        'chromedriver_status': scraping_status.get('chromedriver_status', 'Unknown')
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
        'current_url': scraping_status.get('current_url', ''),
        'chromedriver_status': scraping_status.get('chromedriver_status', 'Unknown')
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
