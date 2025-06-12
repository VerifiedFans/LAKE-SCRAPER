# LAKE-SCRAPER
YOU CAN RUN BUT YOU CAN'T HIDE
# 🎵 Bandsintown Concert Data Scraper

A web application that scrapes concert data from Bandsintown artist pages and exports the results to CSV format. Built with Flask, Selenium, and designed for easy deployment on Railway.app.

## Features

- **Bulk Artist Processing**: Add multiple Bandsintown artist URLs via file upload or manual entry
- **Automated Data Extraction**: Scrapes past concert data including venue names, addresses, and dates
- **Real-time Progress Tracking**: Live status updates during scraping process
- **CSV Export**: Download complete dataset in CSV format
- **Responsive UI**: Modern, mobile-friendly interface
- **Error Handling**: Comprehensive error tracking and reporting

## Data Collected

For each concert, the scraper collects:
- Artist Name
- Venue Name
- Venue Address/Location
- Concert Date

## How It Works

1. **Navigate to Past Events**: Automatically clicks the "Past" tab on artist pages
2. **Paginate Through Results**: Clicks "More Dates" button up to 3 times to load historical data
3. **Extract Concert Data**: Parses venue information, dates, and locations
4. **Compile Results**: Aggregates all data into a downloadable CSV file

## Quick Start

### Local Development

1. Clone the repository:
```bash
git clone <your-repo-url>
cd bandsintown-scraper
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Run the application:
```bash
python app.py
```

4. Open your browser to `http://localhost:5000`

### Railway.app Deployment

1. Connect your GitHub repository to Railway.app
2. The app will automatically deploy using the included configuration files
3. Set any required environment variables in Railway dashboard
4. Your scraper will be live at your Railway-provided URL

## Configuration Files

- `app.py` - Main Flask application
- `requirements.txt` - Python dependencies
- `railway.json` - Railway deployment configuration
- `nixpacks.toml` - Build configuration for Railway
- `Dockerfile` - Container configuration (alternative to nixpacks)
- `Procfile` - Process definition
- `templates/index.html` - Frontend interface

## Usage

1. **Add Artist URLs**: 
   - Upload a text file with URLs (one per line), or
   - Manually enter URLs in the text area
   - Example URL: `https://www.bandsintown.com/a/taylor-swift`

2. **Start Scraping**:
   - Click "Start Scraping" to begin the process
   - Monitor real-time progress and statistics
   - View current artist being processed

3. **Download Results**:
   - Once complete, click "Download CSV" to get your data
   - CSV includes all concerts found across all artists

## Technical Details

### Dependencies
- **Flask**: Web framework
- **Selenium**: Web scraping automation
- **Chrome/ChromeDriver**: Headless browser for scraping
- **Gunicorn**: WSGI server for production

### Architecture
- **Frontend**: Responsive HTML/CSS/JavaScript interface
- **Backend**: Flask API with background processing
- **Scraping**: Selenium-based automation with Chrome headless
- **Data Export**: CSV generation with temporary file handling

### Browser Configuration
The scraper uses Chrome in headless mode with optimized settings:
- No sandbox mode for containerized environments
- Disabled GPU acceleration for server deployment
- Custom user agent for better compatibility
- Optimized window size and memory usage

## Error Handling

The application includes comprehensive error handling:
- Individual artist failures don't stop the entire process
- Network timeout handling
- Missing element graceful degradation
- Detailed error reporting in the UI

## Rate Limiting & Ethics

- Built-in delays between page interactions
- Respectful scraping practices
- Only accesses publicly available data
- Follows robots.txt guidelines

## Environment Variables

Optional environment variables:
- `SECRET_KEY`: Flask session secret (auto-generated if not set)
- `PORT`: Application port (defaults to 5000)

## Troubleshooting

### Common Issues

1. **Chrome/ChromeDriver Issues**: 
   - Ensure Chrome is properly installed in deployment environment
   - Check ChromeDriver version compatibility

2. **Memory Issues**: 
   - Reduce concurrent processing if running out of memory
   - Consider processing smaller batches of artists

3. **Network Timeouts**: 
   - Bandsintown may have rate limiting
   - Try reducing the number of concurrent requests

### Logs
Check application logs for detailed error information:
```bash
# Railway logs
railway logs

# Local development
python app.py  # Check console output
```

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test thoroughly
5. Submit a pull request

## License

This project is for educational and research purposes. Please respect Bandsintown's terms of service and rate limits when using this scraper.

## Support

For issues and questions:
1. Check the troubleshooting section
2. Review Railway.app deployment logs
3. Create an issue in the GitHub repository

---

**Note**: This scraper is designed to work with Bandsintown's current website structure. Website changes may require updates to the scraping logic.
