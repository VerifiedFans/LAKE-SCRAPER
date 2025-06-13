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
    'errors': []
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
    """Scrape concerts - Updated for current Bandsintown structure"""
    driver = None
    concerts = []
    
    try:
        driver = webdriver.Chrome(options=get_chrome_options())
        driver.get(artist_url)
        
        # Wait for page to load
        WebDriverWait(driver, 15).wait(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )
        
        # Extract artist name from URL
        url_parts = artist_url.split('/')[-1].split('-')
        if len(url_parts) > 1:
            artist_name = ' '.join(url_parts[1:]).title()  # Skip the digits, use the name part
        else:
            artist_name = artist_url.split('/')[-1].replace('-', ' ').title()
        
        logger.info(f"Processing artist: {artist_name}")
        
        # Click "Past" tab - it's a clickable text element
        past_clicked = False
        try:
            # Wait for and click the "Past" tab (based on your screenshot)
            past_tab = WebDriverWait(driver, 10).wait(
                EC.element_to_be_clickable((By.XPATH, "//div[text()='Past'] | //span[text()='Past'] | //a[text()='Past']"))
            )
            driver.execute_script("arguments[0].click();", past_tab)
            past_clicked = True
            logger.info(f"✅ Clicked 'Past' tab for {artist_name}")
            time.sleep(3)
        except Exception as e:
            logger.warning(f"Could not find 'Past' tab: {e}")
            # Try alternative selectors
            try:
                past_tab = driver.find_element(By.XPATH, "//*[contains(text(), 'Past')]")
                driver.execute_script("arguments[0].click();", past_tab)
                past_clicked = True
                logger.info(f"✅ Clicked 'Past' tab (alternative method)")
                time.sleep(3)
            except:
                logger.warning(f"Could not click Past tab, will try to scrape current page")
        
        # Scrape concerts with pagination
        for page in range(max_pages):
            try:
                # Wait for concerts to load
                time.sleep(2)
                
                # Find concert containers based on the structure from your screenshot
                # Each concert appears to be in a row/container with date, venue, location
                concert_containers = driver.find_elements(By.XPATH, 
                    "//div[contains(@class, 'concert') or contains(@class, 'event') or contains(@class, 'show')] | "
                    "//div[.//*[contains(text(), '2025') or contains(text(), '2024')]] | "
                    "//div[contains(., 'JUN') or contains(., 'MAY') or contains(., 'APR') or contains(., 'MAR')]"
                )
                
                # If no specific containers found, try to find any div that contains concert-like content
                if not concert_containers:
                    # Look for divs that contain both a venue name and location pattern
                    concert_containers = driver.find_elements(By.XPATH, 
                        "//div[contains(., 'Center') or contains(., 'Church') or contains(., 'Hall') or contains(., 'Theater') or contains(., 'Venue')]"
                    )
                
                logger.info(f"Found {len(concert_containers)} potential concert containers on page {page + 1}")
                
                if not concert_containers:
                    logger.warning(f"No concert containers found on page {page + 1}")
                    break
                
                # Extract concert information
                page_concerts = []
                for i, container in enumerate(concert_containers):
                    try:
                        container_text = container.text.strip()
                        if not container_text:
                            continue
                        
                        # Split text into lines
                        lines = [line.strip() for line in container_text.split('\n') if line.strip()]
                        
                        # Skip if not enough information
                        if len(lines) < 2:
                            continue
                        
                        # Extract information based on the pattern from your screenshot
                        venue_name = ""
                        venue_address = ""
                        date_str = ""
                        
                        # Look for venue name - typically the longest line or one with "Center", "Church", etc.
                        for line in lines:
                            if any(keyword in line for keyword in ['Center', 'Church', 'Hall', 'Theater', 'Venue', 'Club', 'Arena', 'Stadium', 'Baptist', 'Civic', 'Landscape', 'Design']):
                                venue_name = line
                                break
                        
                        # Look for location (city, state pattern like "Corinth, MS")
                        for line in lines:
                            if ', ' in line and len(line.split(', ')) == 2:
                                parts = line.split(', ')
                                if len(parts[1]) == 2:  # State abbreviation
                                    venue_address = line
                                    break
                        
                        # Look for date (month abbreviation + number)
                        for line in lines:
                            if any(month in line.upper() for month in ['JAN', 'FEB', 'MAR', 'APR', 'MAY', 'JUN', 'JUL', 'AUG', 'SEP', 'OCT', 'NOV', 'DEC']):
                                date_str = line
                                break
                        
                        # If we didn't find venue name with keywords, use the first substantial line
                        if not venue_name and lines:
                            for line in lines:
                                if len(line) > 5 and 'I Was There' not in line and not any(month in line.upper() for month in ['JAN', 'FEB', 'MAR', 'APR', 'MAY', 'JUN']):
                                    venue_name = line
                                    break
                        
                        # Only add if we have at least a venue name
                        if venue_name:
                            concert = {
                                'artist_name': artist_name,
                                'venue_name': venue_name,
                                'venue_address': venue_address or 'Not specified',
                                'concert_date': date_str or 'Date not found'
                            }
                            page_concerts.append(concert)
                            logger.info(f"✅ Found concert: {venue_name} - {date_str} - {venue_address}")
                        
                    except Exception as e:
                        logger.warning(f"Error processing concert container {i+1}: {e}")
                        continue
                
                concerts.extend(page_concerts)
                logger.info(f"Page {page + 1}: Found {len(page_concerts)} concerts")
                
                # Try to find and click "More Dates" button
                more_dates_clicked = False
                try:
                    # Scroll to bottom of page first to ensure "More Dates" button is visible
                    driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                    time.sleep(1)
                    
                    # Try to find "More Dates" button
                    more_button = driver.find_element(By.XPATH, 
                        "//button[contains(text(), 'More Dates')] | "
                        "//a[contains(text(), 'More Dates')] | "
                        "//div[contains(text(), 'More Dates')] | "
                        "//span[contains(text(), 'More Dates')]"
                    )
                    
                    if more_button.is_displayed() and more_button.is_enabled():
                        driver.execute_script("arguments[0].click();", more_button)
                        more_dates_clicked = True
                        logger.info(f"✅ Clicked 'More Dates' button")
                        time.sleep(3)  # Wait for new content to load
                    
                except Exception as e:
                    logger.info(f"No 'More Dates' button found or couldn't click: {e}")
                
                if not more_dates_clicked:
                    logger.info(f"No more pages available for {artist_name}")
                    break
                    
            except Exception as e:
                logger.warning(f"Error on page {page + 1} for {artist_name}: {e}")
                break
        
        logger.info(f"🎯 Successfully found {len(concerts)} concerts for {artist_name}")
        return concerts
        
    except Exception as e:
        logger.error(f"❌ Error scraping {artist_url}: {e}")
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
    
    # Validate URLs - must have the format with digits
    valid_urls = []
    invalid_urls = []
    
    for url in artist_urls:
        url = url.strip()
        if 'bandsintown.com' in url and '/a/' in url:
            # Check if URL has the required format with digits
            path_part = url.split('/a/')[-1]
            if '-' in path_part and path_part.split('-')[0].isdigit():
                valid_urls.append(url)
            else:
                invalid_urls.append(url)
        else:
            invalid_urls.append(url)
    
    if invalid_urls:
        error_msg = f"Invalid URLs (need 6-digit format like '/a/147132-artist-name'): {', '.join(invalid_urls[:3])}"
        if len(invalid_urls) > 3:
            error_msg += f" and {len(invalid_urls) - 3} more"
        return jsonify({'error': error_msg}), 400
    
    if not valid_urls:
        return jsonify({'error': 'No valid Bandsintown URLs provided. Use format: https://www.bandsintown.com/a/123456-artist-name'}), 400
    
    # Start scraping in background thread
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
        'errors': scraping_status['errors']
    })

@app.route('/stop_scraping', methods=['POST'])
def stop_scraping():
    global scraping_status
    scraping_status['is_running'] = False
    return jsonify({'message': 'Scraping stopped'})

@app.route('/download_csv')
def download_csv():
    if not concert_data:
        return jsonify({'error': 'No data available'}), 400
    
    # Create temporary CSV file
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

@app.route('/health')
def health_check():
    """Health check endpoint for deployment platforms"""
    return jsonify({'status': 'healthy', 'timestamp': datetime.now().isoformat()})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
