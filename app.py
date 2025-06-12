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
    """Scrape concerts for a single artist - Updated version"""
    driver = None
    concerts = []
    
    try:
        driver = webdriver.Chrome(options=get_chrome_options())
        driver.get(artist_url)
        
        # Wait for page to load
        WebDriverWait(driver, 15).wait(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )
        
        # Extract artist name from URL or page
        artist_name = artist_url.split('/')[-1].replace('-', ' ').title()
        try:
            # Try multiple selectors for artist name
            artist_selectors = [
                "h1", ".artist-name", "[data-testid='artist-name']", 
                ".ArtistHeader_name", ".artist-header h1", ".page-title"
            ]
            for selector in artist_selectors:
                try:
                    artist_element = driver.find_element(By.CSS_SELECTOR, selector)
                    if artist_element.text.strip():
                        artist_name = artist_element.text.strip()
                        break
                except:
                    continue
        except:
            pass
        
        logger.info(f"Processing artist: {artist_name}")
        
        # Try to find and click "Past" tab/button
        past_clicked = False
        past_selectors = [
            "//button[contains(text(), 'Past')]",
            "//a[contains(text(), 'Past')]", 
            "//div[contains(text(), 'Past')]",
            "//span[contains(text(), 'Past')]",
            "//*[contains(@class, 'past')]",
            "//*[contains(@data-testid, 'past')]",
            "//button[contains(@aria-label, 'Past')]"
        ]
        
        for selector in past_selectors:
            try:
                past_button = WebDriverWait(driver, 5).wait(
                    EC.element_to_be_clickable((By.XPATH, selector))
                )
                driver.execute_script("arguments[0].click();", past_button)
                past_clicked = True
                logger.info(f"Clicked 'Past' button for {artist_name}")
                time.sleep(3)
                break
            except:
                continue
        
        if not past_clicked:
            logger.warning(f"Could not find 'Past' button for {artist_name}, trying to scrape current page")
        
        # Scrape concerts with pagination
        for page in range(max_pages):
            try:
                # Wait for content to load
                time.sleep(2)
                
                # Try multiple selectors for concert/event elements
                concert_selectors = [
                    "[data-testid='event-card']",
                    ".event-item", 
                    ".concert-item", 
                    ".show-item",
                    ".event-card",
                    ".EventCard",
                    ".event",
                    ".show",
                    "[class*='event']",
                    "[class*='Event']",
                    "[class*='show']",
                    "[class*='Show']"
                ]
                
                concert_elements = []
                for selector in concert_selectors:
                    try:
                        elements = driver.find_elements(By.CSS_SELECTOR, selector)
                        if elements:
                            concert_elements = elements
                            logger.info(f"Found {len(elements)} elements with selector: {selector}")
                            break
                    except:
                        continue
                
                if not concert_elements:
                    logger.warning(f"No concert elements found on page {page + 1} for {artist_name}")
                    break
                
                # Extract concert information from each element
                for i, element in enumerate(concert_elements):
                    try:
                        # Extract venue name with multiple selectors
                        venue_name = ""
                        venue_selectors = [
                            ".venue-name", "[data-testid='venue-name']", 
                            ".event-venue", ".venue", ".location-name",
                            "h3", "h4", "h2", ".title", ".name",
                            "[class*='venue']", "[class*='Venue']"
                        ]
                        
                        for selector in venue_selectors:
                            try:
                                venue_elem = element.find_element(By.CSS_SELECTOR, selector)
                                text = venue_elem.text.strip()
                                if text and len(text) > 2:  # Make sure it's not just empty or very short
                                    venue_name = text
                                    break
                            except:
                                continue
                        
                        # Extract date with multiple selectors
                        date_str = ""
                        date_selectors = [
                            ".event-date", "[data-testid='event-date']",
                            ".date", ".show-date", "time", ".datetime",
                            "[class*='date']", "[class*='Date']", "[class*='time']"
                        ]
                        
                        for selector in date_selectors:
                            try:
                                date_elem = element.find_element(By.CSS_SELECTOR, selector)
                                text = date_elem.text.strip()
                                if text:
                                    date_str = text
                                    break
                            except:
                                continue
                        
                        # Extract venue address/location
                        venue_address = ""
                        address_selectors = [
                            ".venue-location", "[data-testid='venue-location']",
                            ".event-location", ".location", ".city", ".address",
                            ".venue-city", "[class*='location']", "[class*='Location']",
                            "[class*='city']", "[class*='City']"
                        ]
                        
                        for selector in address_selectors:
                            try:
                                addr_elem = element.find_element(By.CSS_SELECTOR, selector)
                                text = addr_elem.text.strip()
                                if text:
                                    venue_address = text
                                    break
                            except:
                                continue
                        
                        # If we couldn't find venue name, try to use any text from the element
                        if not venue_name:
                            try:
                                all_text = element.text.strip()
                                lines = [line.strip() for line in all_text.split('\n') if line.strip()]
                                if lines:
                                    venue_name = lines[0]  # Use first non-empty line
                            except:
                                pass
                        
                        # Only add if we have at least a venue name
                        if venue_name:
                            concert = {
                                'artist_name': artist_name,
                                'venue_name': venue_name,
                                'venue_address': venue_address or 'Not specified',
                                'concert_date': date_str or 'Date not found'
                            }
                            concerts.append(concert)
                            logger.info(f"Found concert: {venue_name} - {date_str}")
                        else:
                            logger.warning(f"Skipped element {i+1} - no venue name found")
                    
                    except Exception as e:
                        logger.warning(f"Error extracting concert data from element {i+1}: {e}")
                        continue
                
                # Try to click "More Dates", "Load More", or "Show More" button
                pagination_clicked = False
                pagination_selectors = [
                    "//button[contains(text(), 'More Dates')]",
                    "//button[contains(text(), 'Load More')]", 
                    "//button[contains(text(), 'Show More')]",
                    "//button[contains(text(), 'View More')]",
                    "//a[contains(text(), 'More')]",
                    "//*[contains(@class, 'load-more')]",
                    "//*[contains(@class, 'show-more')]",
                    "//*[contains(@data-testid, 'load-more')]"
                ]
                
                for selector in pagination_selectors:
                    try:
                        more_button = driver.find_element(By.XPATH, selector)
                        if more_button.is_displayed() and more_button.is_enabled():
                            driver.execute_script("arguments[0].click();", more_button)
                            pagination_clicked = True
                            logger.info(f"Clicked pagination button for {artist_name}")
                            time.sleep(3)
                            break
                    except:
                        continue
                
                if not pagination_clicked:
                    logger.info(f"No more pagination available for {artist_name}")
                    break
                    
            except Exception as e:
                logger.warning(f"Error on page {page + 1} for {artist_name}: {e}")
                break
        
        logger.info(f"Successfully found {len(concerts)} concerts for {artist_name}")
        return concerts
        
    except Exception as e:
        logger.error(f"Error scraping {artist_url}: {e}")
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
    
    # Validate URLs
    valid_urls = []
    for url in artist_urls:
        url = url.strip()
        if 'bandsintown.com' in url and '/a/' in url:
            valid_urls.append(url)
        else:
            logger.warning(f"Invalid URL format: {url}")
    
    if not valid_urls:
        return jsonify({'error': 'No valid Bandsintown URLs provided. Please use format: https://www.bandsintown.com/a/artist-name'}), 400
    
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
