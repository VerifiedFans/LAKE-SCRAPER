from flask import Flask, render_template, request, jsonify, send_file
import os
import csv
import time
import json
import re
from datetime import datetime, timedelta
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
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

def get_undetected_chrome():
    """Get undetected Chrome driver with automatic ChromeDriver management"""
    
    # Undetected Chrome options
    options = uc.ChromeOptions()
    
    # Essential for deployment
    options.add_argument('--headless')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    
    # Human-like settings
    options.add_argument('--window-size=1366,768')
    options.add_argument('--disable-blink-features=AutomationControlled')
    options.add_argument('--disable-extensions')
    options.add_argument('--disable-plugins')
    options.add_argument('--disable-default-apps')
    options.add_argument('--disable-background-timer-throttling')
    options.add_argument('--disable-backgrounding-occluded-windows')
    options.add_argument('--disable-renderer-backgrounding')
    options.add_argument('--disable-features=TranslateUI')
    options.add_argument('--disable-ipc-flooding-protection')
    
    # Create undetected Chrome driver (handles ChromeDriver version automatically)
    driver = uc.Chrome(options=options, version_main=None)
    
    return driver

def human_like_delay(min_seconds=1, max_seconds=3):
    """Random delay to mimic human behavior"""
    delay = random.uniform(min_seconds, max_seconds)
    time.sleep(delay)
    return delay

def extract_concerts_from_page(driver, artist_name, debug_info):
    """Extract concerts using multiple strategies"""
    concerts = []
    
    try:
        # Get page text
        body_text = driver.find_element(By.TAG_NAME, "body").text
        debug_info.append(f"📝 Page text length: {len(body_text)} characters")
        
        if not body_text:
            debug_info.append("❌ No page text found")
            return concerts
        
        # Sample of text for debugging
        debug_info.append(f"📝 Text sample: {body_text[:300]}...")
        
        # Look for venue patterns
        lines = [line.strip() for line in body_text.split('\n') if line.strip()]
        
        venue_keywords = [
            'Baptist', 'Church', 'Center', 'Hall', 'Theater', 'Arena', 'Stadium',
            'Civic', 'Memorial', 'Community', 'Gospel', 'Quartet', 'Auditorium',
            'Convention', 'Coliseum', 'Amphitheater', 'Pavilion'
        ]
        
        months = ['JAN', 'FEB', 'MAR', 'APR', 'MAY', 'JUN', 'JUL', 'AUG', 'SEP', 'OCT', 'NOV', 'DEC']
        
        potential_venues = []
        
        for i, line in enumerate(lines):
            # Check for venue keywords
            if any(keyword in line for keyword in venue_keywords):
                # Get context around this line
                context_start = max(0, i-2)
                context_end = min(len(lines), i+3)
                context = lines[context_start:context_end]
                
                potential_venues.append({
                    'venue_line': line,
                    'context': context,
                    'line_index': i
                })
        
        debug_info.append(f"🎯 Found {len(potential_venues)} potential venue lines")
        
        # Process potential venues
        processed_venues = set()
        
        for venue_data in potential_venues[:20]:  # Limit to first 20
            try:
                venue_name = venue_data['venue_line'].strip()
                venue_address = ""
                date_str = ""
                
                # Look for date in context
                for context_line in venue_data['context']:
                    if any(month in context_line.upper() for month in months):
                        date_str = context_line.strip()
                        break
                
                # Look for location in context
                for context_line in venue_data['context']:
                    location_match = re.search(r'([A-Za-z\s]+,\s*[A-Z]{2})\b', context_line)
                    if location_match:
                        venue_address = location_match.group(1).strip()
                        break
                
                # Clean venue name
                venue_name = re.sub(r'\s+', ' ', venue_name).strip()
                
                # Filter out non-venue lines
                skip_keywords = ['Set Reminder', 'Tickets', 'Free Entry', 'Follow', 'More Dates', 'Show More']
                if any(skip in venue_name for skip in skip_keywords):
                    continue
                
                # Add if valid and not duplicate
                if venue_name and len(venue_name) > 5 and venue_name not in processed_venues:
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
                debug_info.append(f"   ❌ Error processing venue: {e}")
                continue
        
        debug_info.append(f"🎯 Total concerts extracted: {len(concerts)}")
        return concerts
        
    except Exception as e:
        debug_info.append(f"❌ Error in concert extraction: {e}")
        return concerts

def scrape_artist_concerts(artist_url, max_pages=3):
    """Scrape concerts using undetected Chrome"""
    driver = None
    concerts = []
    debug_info = []
    
    try:
        # Initialize undetected Chrome
        debug_info.append("🚀 Initializing undetected Chrome driver...")
        driver = get_undetected_chrome()
        debug_info.append("✅ Undetected Chrome driver initialized successfully")
        
        # Navigate to page
        debug_info.append(f"🌐 Navigating to: {artist_url}")
        driver.get(artist_url)
        
        # Human-like waiting
        delay = human_like_delay(3, 6)
        debug_info.append(f"⏳ Human-like delay: {delay:.1f}s")
        
        # Wait for page to load
        try:
            WebDriverWait(driver, 20).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
            debug_info.append("✅ Page loaded successfully")
        except TimeoutException:
            debug_info.append("❌ Timeout waiting for page load")
            return concerts
        
        # Get page information
        page_title = driver.title
        current_url = driver.current_url
        scraping_status['page_title'] = page_title
        scraping_status['current_url'] = current_url
        
        debug_info.append(f"📄 Page title: '{page_title}'")
        debug_info.append(f"📄 Current URL: {current_url}")
        
        # Check for bot detection
        page_source = driver.page_source
        scraping_status['raw_html'] = page_source[:15000]
        
        bot_indicators = ['access denied', 'blocked', 'captcha', 'forbidden', 'bot detected']
        detected = [indicator for indicator in bot_indicators if indicator in page_source.lower()]
        
        if detected:
            debug_info.append(f"🚫 Possible bot detection: {detected}")
        else:
            debug_info.append("✅ No bot detection indicators found")
        
        # Extract artist name
        url_parts = artist_url.split('/')[-1].split('-')
        artist_name = ' '.join(url_parts[1:]).title() if len(url_parts) > 1 else 'Unknown Artist'
        debug_info.append(f"🎤 Artist: {artist_name}")
        
        # Look for Past tab
        debug_info.append("🔍 Looking for Past tab...")
        
        past_clicked = False
        try:
            # Try multiple selectors for Past tab
            past_selectors = [
                "//a[normalize-space(text())='Past']",
                "//div[normalize-space(text())='Past']",
                "//span[normalize-space(text())='Past']",
                "//button[normalize-space(text())='Past']",
                "//*[contains(text(), 'Past')]"
            ]
            
            for selector in past_selectors:
                try:
                    elements = driver.find_elements(By.XPATH, selector)
                    for element in elements:
                        if element.is_displayed() and element.is_enabled():
                            # Scroll to element
                            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
                            human_like_delay(0.5, 1)
                            
                            # Click
                            element.click()
                            past_clicked = True
                            debug_info.append("✅ Successfully clicked Past tab")
                            human_like_delay(3, 6)  # Wait for content to load
                            break
                    if past_clicked:
                        break
                except:
                    continue
            
            if not past_clicked:
                debug_info.append("⚠️ Could not find/click Past tab, proceeding with current page")
                
        except Exception as e:
            debug_info.append(f"❌ Error with Past tab: {e}")
        
        # Extract concerts
        debug_info.append("🎵 Extracting concerts...")
        concerts = extract_concerts_from_page(driver, artist_name, debug_info)
        
        # Store debug info
        scraping_status['debug_info'] = debug_info
        
        debug_info.append(f"🎯 FINAL RESULT: Found {len(concerts)} concerts for {artist_name}")
        logger.info(f"Undetected Chrome scraping completed for {artist_name}: {len(concerts)} concerts")
        
        return concerts
        
    except Exception as e:
        error_msg = f"❌ Critical error in undetected Chrome scraping {artist_url}: {e}"
        debug_info.append(error_msg)
        scraping_status['debug_info'] = debug_info
        logger.error(error_msg)
        return concerts
        
    finally:
        if driver:
            try:
                human_like_delay(1, 2)
                driver.quit()
            except:
                pass

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
                delay = random.uniform(5, 15)
                logger.info(f"Delay: {delay:.1f} seconds before next artist")
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
