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
from selenium.common.exceptions import TimeoutException, NoSuchElementException
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor
import logging

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
    'raw_html': ''
}

concert_data = []

def get_chrome_options():
    """Configure Chrome options for headless operation"""
    chrome_options = Options()
    chrome_options.add_argument('--headless')
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument('--disable-gpu')
    chrome_options.add_argument('--window-size=1920,1080')
    chrome_options.add_argument('--disable-web-security')
    chrome_options.add_argument('--disable-features=VizDisplayCompositor')
    chrome_options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
    return chrome_options

def scrape_artist_concerts(artist_url, max_pages=3):
    """HTML Inspector version - captures raw HTML and tries multiple approaches"""
    driver = None
    concerts = []
    debug_info = []
    
    try:
        driver = webdriver.Chrome(options=get_chrome_options())
        debug_info.append("✅ Chrome driver started")
        
        driver.get(artist_url)
        debug_info.append(f"✅ Navigated to: {artist_url}")
        
        # Wait for page to load
        WebDriverWait(driver, 15).wait(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )
        debug_info.append("✅ Page loaded")
        
        # Extract artist name
        url_parts = artist_url.split('/')[-1].split('-')
        if len(url_parts) > 1:
            artist_name = ' '.join(url_parts[1:]).title()
        else:
            artist_name = artist_url.split('/')[-1].replace('-', ' ').title()
        
        debug_info.append(f"🎤 Artist: {artist_name}")
        
        # Wait for dynamic content to load
        time.sleep(5)
        
        # Capture raw HTML for debugging
        try:
            page_source = driver.page_source
            scraping_status['raw_html'] = page_source[:10000]  # First 10k characters
            debug_info.append(f"📄 Captured {len(page_source)} characters of HTML")
        except Exception as e:
            debug_info.append(f"❌ Could not capture HTML: {e}")
        
        # Look for "Past" in the HTML and click it
        past_clicked = False
        try:
            # Try to find "Past" tab with various methods
            time.sleep(2)
            
            # Method 1: Look for clickable "Past" text
            past_elements = driver.find_elements(By.XPATH, "//*[normalize-space(text())='Past']")
            debug_info.append(f"🔍 Found {len(past_elements)} elements with 'Past' text")
            
            for i, elem in enumerate(past_elements):
                try:
                    # Get element info
                    tag = elem.tag_name
                    classes = elem.get_attribute("class")
                    clickable = elem.is_enabled() and elem.is_displayed()
                    debug_info.append(f"   Past element {i+1}: <{tag}> class='{classes}' clickable={clickable}")
                    
                    if clickable:
                        # Scroll to element and click
                        driver.execute_script("arguments[0].scrollIntoView(true);", elem)
                        time.sleep(1)
                        driver.execute_script("arguments[0].click();", elem)
                        past_clicked = True
                        debug_info.append(f"   ✅ Successfully clicked Past element {i+1}")
                        time.sleep(5)  # Wait for content to load
                        break
                        
                except Exception as e:
                    debug_info.append(f"   ❌ Error clicking Past element {i+1}: {e}")
                    continue
            
            # Method 2: If no direct "Past" found, look for tab-like elements
            if not past_clicked:
                tab_elements = driver.find_elements(By.XPATH, 
                    "//*[contains(@class, 'tab') or contains(@role, 'tab')]//*[contains(text(), 'Past')]"
                )
                debug_info.append(f"🔍 Found {len(tab_elements)} tab-like elements with 'Past'")
                
                for elem in tab_elements:
                    try:
                        if elem.is_displayed() and elem.is_enabled():
                            driver.execute_script("arguments[0].click();", elem)
                            past_clicked = True
                            debug_info.append("   ✅ Clicked Past tab element")
                            time.sleep(5)
                            break
                    except:
                        continue
                        
        except Exception as e:
            debug_info.append(f"❌ Error finding/clicking Past: {e}")
        
        if past_clicked:
            debug_info.append("✅ Successfully clicked Past tab")
        else:
            debug_info.append("⚠️ Could not click Past tab - will try to scrape current page")
        
        # Now try to extract concerts using multiple strategies
        time.sleep(3)
        
        # Strategy 1: Look for structured concert data using regex on page text
        try:
            page_text = driver.find_element(By.TAG_NAME, "body").text
            debug_info.append(f"📝 Page text length: {len(page_text)} characters")
            
            # Look for patterns like "JUN 12 ... Baptist Church ... City, ST"
            concert_patterns = []
            
            # Split text into lines and look for concert-like patterns
            lines = page_text.split('\n')
            for i, line in enumerate(lines):
                line = line.strip()
                if line and any(month in line.upper() for month in ['JAN', 'FEB', 'MAR', 'APR', 'MAY', 'JUN', 'JUL', 'AUG', 'SEP', 'OCT', 'NOV', 'DEC']):
                    # This line contains a date, look at surrounding lines for venue info
                    context_lines = lines[max(0, i-2):min(len(lines), i+3)]
                    context_text = '\n'.join(context_lines)
                    
                    if any(venue_word in context_text for venue_word in ['Church', 'Baptist', 'Center', 'Hall', 'Theater', 'Arena']):
                        concert_patterns.append(context_text)
                        debug_info.append(f"   📋 Found concert pattern: {context_text[:100]}...")
            
            debug_info.append(f"🎯 Strategy 1: Found {len(concert_patterns)} concert patterns in text")
            
        except Exception as e:
            debug_info.append(f"❌ Strategy 1 failed: {e}")
        
        # Strategy 2: Look for specific HTML patterns
        try:
            # Look for elements containing both date and venue information
            concert_elements = driver.find_elements(By.XPATH,
                "//*[contains(text(), 'JUN') or contains(text(), 'JUL') or contains(text(), 'AUG') or contains(text(), 'MAY') or contains(text(), 'APR')]/ancestor::*[contains(., 'Church') or contains(., 'Baptist') or contains(., 'Center') or contains(., 'Hall')]"
            )
            
            debug_info.append(f"🎯 Strategy 2: Found {len(concert_elements)} elements with date+venue")
            
            for i, elem in enumerate(concert_elements[:10]):
                try:
                    elem_text = elem.text.strip()
                    if elem_text:
                        debug_info.append(f"   Concert element {i+1}: {elem_text[:150]}...")
                        
                        # Try to parse this element for concert data
                        lines = [line.strip() for line in elem_text.split('\n') if line.strip()]
                        
                        venue_name = ""
                        venue_address = ""
                        date_str = ""
                        
                        # Extract venue
                        for line in lines:
                            if any(word in line for word in ['Church', 'Baptist', 'Center', 'Hall', 'Theater', 'Arena', 'Stadium']):
                                venue_name = line
                                break
                        
                        # Extract location (City, ST pattern)
                        for line in lines:
                            if re.match(r'.*,\s*[A-Z]{2}.*', line):
                                venue_address = line
                                break
                        
                        # Extract date
                        for line in lines:
                            if any(month in line.upper() for month in ['JAN', 'FEB', 'MAR', 'APR', 'MAY', 'JUN', 'JUL', 'AUG', 'SEP', 'OCT', 'NOV', 'DEC']):
                                date_str = line
                                break
                        
                        if venue_name:
                            concert = {
                                'artist_name': artist_name,
                                'venue_name': venue_name,
                                'venue_address': venue_address or 'Not specified',
                                'concert_date': date_str or 'Date not found'
                            }
                            
                            # Check for duplicates
                            is_duplicate = any(
                                c['venue_name'] == concert['venue_name'] and 
                                c['concert_date'] == concert['concert_date']
                                for c in concerts
                            )
                            
                            if not is_duplicate:
                                concerts.append(concert)
                                debug_info.append(f"   ✅ Added concert: {venue_name} | {date_str} | {venue_address}")
                        
                except Exception as e:
                    debug_info.append(f"   ❌ Error processing concert element {i+1}: {e}")
                    continue
                    
        except Exception as e:
            debug_info.append(f"❌ Strategy 2 failed: {e}")
        
        # Strategy 3: Brute force - look at ALL elements and find concert-like content
        try:
            all_elements = driver.find_elements(By.XPATH, "//*[text()]")
            concert_like_elements = []
            
            for elem in all_elements:
                try:
                    text = elem.text.strip()
                    if text and len(text) > 20:  # Substantial text
                        # Check if it contains concert-like patterns
                        has_date = any(month in text.upper() for month in ['JAN', 'FEB', 'MAR', 'APR', 'MAY', 'JUN', 'JUL', 'AUG', 'SEP', 'OCT', 'NOV', 'DEC'])
                        has_venue = any(word in text for word in ['Church', 'Baptist', 'Center', 'Hall', 'Theater', 'Arena', 'Stadium'])
                        has_location = bool(re.search(r'[A-Za-z]+,\s*[A-Z]{2}', text))
                        
                        if has_date and (has_venue or has_location):
                            concert_like_elements.append(text)
                except:
                    continue
            
            debug_info.append(f"🎯 Strategy 3: Found {len(concert_like_elements)} concert-like elements")
            
            # Process the most promising elements
            for i, text in enumerate(concert_like_elements[:5]):
                debug_info.append(f"   Concert-like text {i+1}: {text[:200]}...")
                
        except Exception as e:
            debug_info.append(f"❌ Strategy 3 failed: {e}")
        
        # Store debug info
        scraping_status['debug_info'] = debug_info
        
        debug_info.append(f"🎯 FINAL RESULT: Found {len(concerts)} concerts for {artist_name}")
        logger.info(f"Scraping completed for {artist_name}: {len(concerts)} concerts found")
        
        return concerts
        
    except Exception as e:
        error_msg = f"❌ Major error scraping {artist_url}: {e}"
        debug_info.append(error_msg)
        scraping_status['debug_info'] = debug_info
        logger.error(error_msg)
        return concerts
        
    finally:
        if driver:
            driver.quit()

def scrape_multiple_artists(artist_urls):
    """Scrape concerts for multiple artists"""
    global scraping_status, concert_data
    
    scraping_status['is_running'] = True
    scraping_status['artists_processed'] = 0
    scraping_status['concerts_found'] = 0
    scraping_status['unique_venues'] = set()
    scraping_status['errors'] = []
    scraping_status['debug_info'] = []
    scraping_status['raw_html'] = ''
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
        'debug_info': scraping_status.get('debug_info', [])
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
        'concert_count': len(concert_data)
    })

@app.route('/raw_html')
def get_raw_html():
    """New endpoint to see the raw HTML that was captured"""
    return jsonify({
        'raw_html': scraping_status.get('raw_html', ''),
        'html_length': len(scraping_status.get('raw_html', ''))
    })

@app.route('/health')
def health_check():
    return jsonify({'status': 'healthy', 'timestamp': datetime.now().isoformat()})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
