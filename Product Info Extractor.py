from flask import Flask, request, jsonify
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import re
import json

app = Flask(__name__)

def extract_product_info(url):
    """
    Extract product information from a URL
    Returns a dict with image, title, price, description
    """
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, 'html.parser')
        html_text = response.text
        
        product_info = {
            'image': None,
            'title': None,
            'price': None,
            'description': None,
            'url': url
        }
        
        # === EXTRACT IMAGE ===
        og_image = soup.find('meta', property='og:image')
        if og_image and og_image.get('content'):
            product_info['image'] = og_image['content']
        else:
            twitter_image = soup.find('meta', attrs={'name': 'twitter:image'})
            if twitter_image and twitter_image.get('content'):
                product_info['image'] = twitter_image['content']
            else:
                images = soup.find_all('img')
                if images:
                    large_images = [
                        img for img in images 
                        if img.get('src') and not any(x in img.get('src', '') for x in ['icon', 'logo', 'sprite'])
                    ]
                    if large_images:
                        img_src = large_images[0].get('src')
                        product_info['image'] = urljoin(url, img_src)
        
        # === EXTRACT TITLE ===
        og_title = soup.find('meta', property='og:title')
        if og_title and og_title.get('content'):
            product_info['title'] = og_title['content']
        else:
            title_tag = soup.find('title')
            if title_tag:
                product_info['title'] = title_tag.get_text().strip()
            else:
                h1_tag = soup.find('h1')
                if h1_tag:
                    product_info['title'] = h1_tag.get_text().strip()
        
        # === EXTRACT PRICE ===
        
        # Method 1: JSON-LD structured data
        json_ld_scripts = soup.find_all('script', type='application/ld+json')
        for script in json_ld_scripts:
            try:
                data = json.loads(script.string)
                if isinstance(data, list):
                    data = data[0]
                
                if 'offers' in data:
                    offers = data['offers']
                    if isinstance(offers, dict) and 'price' in offers:
                        product_info['price'] = f"${offers['price']}"
                        break
                    elif isinstance(offers, list) and len(offers) > 0 and 'price' in offers[0]:
                        product_info['price'] = f"${offers[0]['price']}"
                        break
            except:
                continue
        
        # Method 2: Meta tags
        if not product_info['price']:
            price_meta = soup.find('meta', property='product:price:amount')
            if price_meta and price_meta.get('content'):
                product_info['price'] = f"${price_meta['content']}"
        
        # Method 3: Raw HTML search
        if not product_info['price']:
            price_patterns = [
                r'"price":\s*\{\s*"current":\s*(\d+\.?\d*)',
                r'"currentPrice":\s*(\d+\.?\d*)',
                r'"price":\s*(\d+\.?\d*)',
                r'price":\s*"?\$?(\d+\.?\d*)"?',
            ]
            
            for pattern in price_patterns:
                match = re.search(pattern, html_text)
                if match:
                    product_info['price'] = f"${match.group(1)}"
                    break
        
        # Method 4: HTML selectors
        if not product_info['price']:
            price_selectors = [
                soup.find('span', itemprop='price'),
                soup.find('meta', itemprop='price'),
                soup.find('span', {'data-test': re.compile(r'price', re.I)}),
                soup.find(class_=re.compile(r'price', re.I)),
                soup.find('span', class_=re.compile(r'price', re.I)),
            ]
            
            for price_elem in price_selectors:
                if price_elem:
                    price_text = price_elem.get('content') if price_elem.name == 'meta' else price_elem.get_text()
                    if price_text:
                        price_match = re.search(r'[\$€£]?\s*(\d+[,.]?\d*\.?\d*)', price_text)
                        if price_match:
                            product_info['price'] = price_match.group(0).strip()
                            break
        
        # === EXTRACT DESCRIPTION ===
        og_desc = soup.find('meta', property='og:description')
        if og_desc and og_desc.get('content'):
            product_info['description'] = og_desc['content']
        else:
            meta_desc = soup.find('meta', attrs={'name': 'description'})
            if meta_desc and meta_desc.get('content'):
                product_info['description'] = meta_desc['content']
            else:
                schema_desc = soup.find(itemprop='description')
                if schema_desc:
                    product_info['description'] = schema_desc.get_text().strip()[:500]
        
        return product_info
        
    except Exception as e:
        return None

# RapidAPI Endpoint
@app.route('/extract', methods=['GET'])
def api_extract_product():
    """
    Extract product information from URL
    
    Query Parameters:
        url (required): Product URL to extract information from
    
    Returns:
        JSON object with product details
    """
    # Get URL from query parameter
    url = request.args.get('url')
    
    if not url:
        return jsonify({
            'success': False,
            'error': 'Missing required parameter: url',
            'message': 'Please provide a product URL'
        }), 400
    
    # Extract product info
    product_info = extract_product_info(url)
    
    if product_info and (product_info['image'] or product_info['title']):
        return jsonify({
            'success': True,
            'data': {
                'title': product_info['title'],
                'price': product_info['price'],
                'image': product_info['image'],
                'description': product_info['description'],
                'url': product_info['url']
            }
        }), 200
    else:
        return jsonify({
            'success': False,
            'error': 'Could not extract product information',
            'message': 'The site may be blocking scrapers or the URL is invalid',
            'data': {
                'title': None,
                'price': None,
                'image': None,
                'description': None,
                'url': url
            }
        }), 404

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'service': 'Product Information Extractor API',
        'version': '1.0.0'
    }), 200

@app.route('/', methods=['GET'])
def home():
    """API documentation"""
    return jsonify({
        'name': 'Product Information Extractor API',
        'version': '1.0.0',
        'description': 'Extract product details (title, price, image, description) from e-commerce URLs',
        'endpoints': {
            'GET /extract': {
                'description': 'Extract product information from a URL',
                'parameters': {
                    'url': {
                        'type': 'string',
                        'required': True,
                        'description': 'Product URL to extract information from',
                        'example': 'https://www.target.com/p/product-name/-/A-12345678'
                    }
                },
                'response': {
                    'success': 'boolean',
                    'data': {
                        'title': 'string',
                        'price': 'string',
                        'image': 'string (URL)',
                        'description': 'string',
                        'url': 'string'
                    }
                }
            },
            'GET /health': {
                'description': 'Check API health status'
            }
        },
        'example_usage': {
            'request': 'GET /extract?url=https://www.target.com/p/product/-/A-12345678',
            'response': {
                'success': True,
                'data': {
                    'title': 'Product Name',
                    'price': '$19.99',
                    'image': 'https://example.com/image.jpg',
                    'description': 'Product description...',
                    'url': 'https://www.target.com/p/product/-/A-12345678'
                }
            }
        }
    }), 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000)
