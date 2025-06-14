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
    'current_url': ''
}

concert_data = []

def get_chrome_options():
    """Simple Chrome options that work"""
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
    
    # Realistic user agent
    chrome_options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36')
    
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
            'Baptist', 'Church', 'Center', 'Hall', 'Theater', 'Arena', 'Stadium',
            'Civic', 'Memorial', 'Community', 'Gospel', 'Quartet', 'Auditorium',
            'Convention', 'Coliseum', 'Amphitheater', 'Pavilion', 'Tabernacle'
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
        
        for venue_data in venue_lines[:25]:  # Limit to prevent overload
            try:
                venue_line = venue_data['line']
                line_index = venue_data['index']
                
                # Skip obvious non-venue lines
                skip_terms = ['Set Reminder', 'Tickets', 'Follow', 'More Dates', 'Show More', 'Free Entry']
                if any(term in venue_line for term in skip_terms):
                    continue
                
                # Clean the venue name
                venue_name = re.sub(r'\s+', ' ', venue_line).strip()
                
                # Look for date in nearby lines
                date_str = ""
                search_range = 3  # Look 3 lines before and after
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
    """Scrape concerts with retry logic"""
    driver = None
    concerts = []
    debug_info = []
    
    for attempt in range(max_retries):
        try:
            debug_info.append(f"🚀 Attempt {attempt + 1}/{max_retries}")
            
            # Initialize Chrome driver
            chrome_options = get_chrome_options()
            
            try:
                # Try with system ChromeDriver
                driver = webdriver.Chrome(options=chrome_options)
                debug_info.append("✅ Chrome driver initialized successfully")
            except Exception as e:
                debug_info.append(f"❌ Chrome driver error: {e}")
                if attempt == max_retries - 1:
                    raise e
                continue
            
            # Hide webdriver property
            driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            
            # Navigate to page
            debug_info.append(f"🌐 Navigating to: {artist_url}")
            driver.get(artist_url)
            
            # Wait for page load
            delay = human_delay(3, 6)
            debug_info.append(f"⏳ Waiting {delay:.1f}s for page load")
            
            # Check if page loaded
            try:
                WebDriverWait(driver, 15).until(
                    EC.presence_of_element_located((By.TAG_NAME, "body"))
                )
                debug_info.append("✅ Page body loaded")
            except TimeoutException:
                debug_info.append("❌ Timeout waiting for page load")
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
            url_parts = artist_url.split('/')[-1].split('-')
            artist_name = ' '.join(url_parts[1:]).title() if len(url_parts) > 1 else 'Unknown Artist'
            debug_info.append(f"🎤 Artist: {artist_name}")
            
            # Try to click Past tab
            debug_info.append("🔍 Looking for Past tab...")
            try:
                # Simple approach - look for Past text
                past_elements = driver.find_elements(By.XPATH, "//*[contains(text(), 'Past')]")
                
                clicked_past = False
                for element in past_elements[:3]:  # Try first 3 matches
                    try:
                        if element.is_displayed() and element.is_enabled():
                            driver.execute_script("arguments[0].scrollIntoView();", element)
                            human_delay(0.5, 1)
                            element.click()
                            clicked_past = True
                            debug_info.append("✅ Clicked Past tab")
                            human_delay(3, 5)  # Wait for content
                            break
                    except:
                        continue
                
                if not clicked_past:
                    debug_info.append("⚠️ Could not click Past tab, using current page")
            
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
                delay = random.uniform(8, 20)
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
