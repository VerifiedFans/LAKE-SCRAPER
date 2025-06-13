from flask import Flask, render_template, request, jsonify, send_file
import os
import csv
import time
import json
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
    'debug_info': []
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
    """Scrape concerts - Targeted for exact Bandsintown structure from screenshot"""
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
        
        # Extract artist name from URL
        url_parts = artist_url.split('/')[-1].split('-')
        if len(url_parts) > 1:
            artist_name = ' '.join(url_parts[1:]).title()
        else:
            artist_name = artist_url.split('/')[-1].replace('-', ' ').title()
        
        debug_info.append(f"🎤 Artist: {artist_name}")
        
        # Click "Past" tab - Look for the tab structure from screenshot
        past_clicked = False
        try:
            # Wait a bit for the page to fully load
            time.sleep(3)
            
            # Try to find the "Past" tab - multiple approaches
            past_selectors = [
                "//div[text()='Past']",
                "//span[text()='Past']", 
                "//a[text()='Past']",
                "//button[text()='Past']",
                "//*[normalize-space(text())='Past']",
                "//div[contains(@class, 'tab') and contains(text(), 'Past')]",
                "//a[contains(@class, 'tab') and contains(text(), 'Past')]"
            ]
            
            for i, selector in enumerate(past_selectors):
                try:
                    past_element = driver.find_element(By.XPATH, selector)
                    if past_element.is_displayed():
                        # Scroll to element first
                        driver.execute_script("arguments[0].scrollIntoView(true);", past_element)
                        time.sleep(1)
                        
                        # Try clicking
                        driver.execute_script("arguments[0].click();", past_element)
                        past_clicked = True
                        debug_info.append(f"✅ Clicked 'Past' tab using selector {i+1}")
                        time.sleep(4)  # Wait for content to load
                        break
                        
                except Exception as e:
                    debug_info.append(f"   Past selector {i+1} failed: {e}")
                    continue
            
            if not past_clicked:
                debug_info.append("⚠️ Could not click 'Past' tab, will try to find concerts on current page")
                
        except Exception as e:
            debug_info.append(f"❌ Error clicking Past tab: {e}")
        
        # Now scrape concerts with pagination
        for page in range(max_pages):
            debug_info.append(f"🔍 Scraping page {page + 1}")
            
            try:
                # Wait for content to load
                time.sleep(2)
                
                # Based on the screenshot, concerts appear to be in a structured list
                # Each concert has: date (JUN 12), venue name, location, and buttons
                
                # Try to find concert containers - look for elements with dates
                date_elements = driver.find_elements(By.XPATH, 
                    "//div[contains(text(), 'JUN') or contains(text(), 'JUL') or contains(text(), 'AUG') or contains(text(), 'SEP') or contains(text(), 'OCT') or contains(text(), 'NOV') or contains(text(), 'DEC') or contains(text(), 'JAN') or contains(text(), 'FEB') or contains(text(), 'MAR') or contains(text(), 'APR') or contains(text(), 'MAY')]"
                )
                
                debug_info.append(f"   Found {len(date_elements)} date elements")
                
                # Alternative: Look for elements containing venue-like names
                venue_elements = driver.find_elements(By.XPATH,
                    "//div[contains(text(), 'Church') or contains(text(), 'Baptist') or contains(text(), 'Center') or contains(text(), 'Hall') or contains(text(), 'Theater') or contains(text(), 'Arena') or contains(text(), 'Stadium')]"
                )
                
                debug_info.append(f"   Found {len(venue_elements)} venue-like elements")
                
                # Look for concert rows/containers - elements that contain both date and venue info
                # Based on screenshot, each concert seems to be in a row with date, name, location
                concert_rows = driver.find_elements(By.XPATH,
                    "//div[contains(., 'Baptist') or contains(., 'Church') or contains(., 'Center') or contains(., 'Hall')][contains(., 'JUN') or contains(., 'JUL') or contains(., 'AUG') or contains(., 'SEP') or contains(., 'OCT') or contains(., 'NOV') or contains(., 'DEC') or contains(., 'JAN') or contains(., 'FEB') or contains(., 'MAR') or contains(., 'APR') or contains(., 'MAY')]"
                )
                
                debug_info.append(f"   Found {len(concert_rows)} potential concert rows")
                
                # If no specific rows found, try to find parent containers
                if not concert_rows:
                    # Look for any div that contains concert-like text patterns
                    all_divs = driver.find_elements(By.TAG_NAME, "div")
                    potential_concerts = []
                    
                    for div in all_divs:
                        try:
                            div_text = div.text.strip()
                            if div_text and len(div_text) > 10:
                                # Check if it contains concert-like patterns
                                has_venue = any(word in div_text for word in ['Baptist', 'Church', 'Center', 'Hall', 'Theater', 'Arena', 'Stadium'])
                                has_location = len([part for part in div_text.split(', ') if len(part) == 2]) > 0  # State abbreviations
                                has_date = any(month in div_text.upper() for month in ['JAN', 'FEB', 'MAR', 'APR', 'MAY', 'JUN', 'JUL', 'AUG', 'SEP', 'OCT', 'NOV', 'DEC'])
                                
                                if (has_venue or has_location) and has_date:
                                    potential_concerts.append(div)
                        except:
                            continue
                    
                    concert_rows = potential_concerts
                    debug_info.append(f"   Found {len(concert_rows)} potential concert containers from all divs")
                
                # Extract data from found concert rows
                page_concerts = []
                for i, row in enumerate(concert_rows[:50]):  # Limit to first 50 to avoid duplicates
                    try:
                        row_text = row.text.strip()
                        if not row_text or len(row_text) < 10:
                            continue
                        
                        debug_info.append(f"   Processing row {i+1}: {row_text[:100]}...")
                        
                        # Split into lines
                        lines = [line.strip() for line in row_text.split('\n') if line.strip()]
                        
                        # Extract concert data
                        venue_name = ""
                        venue_address = ""
                        date_str = ""
                        
                        # Find venue name (look for lines with venue keywords)
                        for line in lines:
                            if any(keyword in line for keyword in ['Baptist', 'Church', 'Center', 'Hall', 'Theater', 'Arena', 'Stadium', 'Civic', 'Memorial', 'Community']):
                                venue_name = line
                                break
                        
                        # Find location (look for City, ST pattern)
                        for line in lines:
                            if ', ' in line:
                                parts = line.split(', ')
                                if len(parts) >= 2 and len(parts[-1]) == 2:  # Last part is state abbreviation
                                    venue_address = line
                                    break
                        
                        # Find date (look for month abbreviations)
                        for line in lines:
                            if any(month in line.upper() for month in ['JAN', 'FEB', 'MAR', 'APR', 'MAY', 'JUN', 'JUL', 'AUG', 'SEP', 'OCT', 'NOV', 'DEC']):
                                date_str = line
                                break
                        
                        # If no specific venue found, use first substantial line
                        if not venue_name and lines:
                            for line in lines:
                                if len(line) > 5 and 'Set Reminder' not in line and 'Tickets' not in line and 'Free Entry' not in line:
                                    venue_name = line
                                    break
                        
                        # Only add if we have meaningful data
                        if venue_name and len(venue_name) > 3:
                            concert = {
                                'artist_name': artist_name,
                                'venue_name': venue_name,
                                'venue_address': venue_address or 'Not specified',
                                'concert_date': date_str or 'Date not found'
                            }
                            
                            # Avoid duplicates
                            is_duplicate = any(
                                existing['venue_name'] == concert['venue_name'] and 
                                existing['concert_date'] == concert['concert_date']
                                for existing in concerts + page_concerts
                            )
                            
                            if not is_duplicate:
                                page_concerts.append(concert)
                                debug_info.append(f"   ✅ Added: {venue_name} | {date_str} | {venue_address}")
                            else:
                                debug_info.append(f"   ⚠️ Skipped duplicate: {venue_name}")
                        
                    except Exception as e:
                        debug_info.append(f"   ❌ Error processing row {i+1}: {e}")
                        continue
                
                concerts.extend(page_concerts)
                debug_info.append(f"📊 Page {page + 1}: Added {len(page_concerts)} concerts (Total: {len(concerts)})")
                
                # Look for "Show More Dates" button
                more_clicked = False
                try:
                    # Scroll to bottom first
                    driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                    time.sleep(2)
                    
                    # Look for "Show More Dates" button based on screenshot
                    more_selectors = [
                        "//div[contains(text(), 'Show More Dates')]",
                        "//button[contains(text(), 'Show More Dates')]",
                        "//a[contains(text(), 'Show More Dates')]",
                        "//span[contains(text(), 'Show More Dates')]",
                        "//*[contains(text(), 'More Dates')]",
                        "//*[contains(text(), 'Show More')]"
                    ]
                    
                    for selector in more_selectors:
                        try:
                            more_button = driver.find_element(By.XPATH, selector)
                            if more_button.is_displayed() and more_button.is_enabled():
                                driver.execute_script("arguments[0].scrollIntoView(true);", more_button)
                                time.sleep(1)
                                driver.execute_script("arguments[0].click();", more_button)
                                more_clicked = True
                                debug_info.append(f"   ✅ Clicked 'Show More Dates' button")
                                time.sleep(4)  # Wait for new content
                                break
                        except Exception as e:
                            debug_info.append(f"   More button selector failed: {e}")
                            continue
                            
                except Exception as e:
                    debug_info.append(f"   ❌ Error looking for More button: {e}")
                
                if not more_clicked:
                    debug_info.append(f"   ⚠️ No 'Show More Dates' button found, stopping pagination")
                    break
                
            except Exception as e:
                debug_info.append(f"❌ Error on page {page + 1}: {e}")
                break
        
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

@app.route('/health')
def health_check():
    return jsonify({'status': 'healthy', 'timestamp': datetime.now().isoformat()})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
