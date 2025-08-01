# scraper.py - Simple approach: Body content only
import requests
from bs4 import BeautifulSoup
import json
from urllib.parse import urljoin
import time

# Load URLs from scrape_urls.json
with open("scrape_urls.json") as f:
    url_config = json.load(f)
urls = url_config["urls"]

def remove_navigation_elements(soup):
    """Remove header, footer, and navigation elements"""
    elements_to_remove = [
        'header', 'footer', 'nav', 'aside',
        '[class*="nav"]', '[class*="menu"]', '[class*="header"]', '[class*="footer"]',
        '[id*="nav"]', '[id*="menu"]', '[id*="header"]', '[id*="footer"]',
        'script', 'style', 'noscript'
    ]
    
    for selector in elements_to_remove:
        for element in soup.select(selector):
            element.decompose()
    
    return soup

def get_body_content(soup):
    """Get only the main body content"""
    # Try to find main content area
    main_content_selectors = [
        'main', 'article', '[role="main"]', '.main-content', 
        '.content', '.page-content', 'body'
    ]
    
    for selector in main_content_selectors:
        content = soup.select_one(selector)
        if content:
            return content
    
    # Fallback to body
    return soup.find('body') or soup

def extract_course_links_from_body(url):
    """Extract course links from body content only"""
    print(f"Scraping body content from: {url}")
    
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
    except Exception as e:
        print(f"Error fetching {url}: {e}")
        return []

    soup = BeautifulSoup(response.text, "html.parser")
    
    # Remove navigation elements
    soup = remove_navigation_elements(soup)
    
    # Get only body content
    body_content = get_body_content(soup)
    
    course_links = []
    processed_links = set()
    
    # Find all links in body content
    links = body_content.find_all('a', href=True)
    
    for link in links:
        href = link.get('href')
        text = link.get_text(strip=True)
        
        if not href or not text or href in processed_links:
            continue
            
        # Skip certain types of links
        if any(skip in href.lower() for skip in ['#', 'javascript:', 'mailto:', 'tel:']):
            continue
            
        # Look for course-related links
        if is_likely_course_link(href, text):
            full_url = urljoin(url, href)
            course_links.append({
                'url': full_url,
                'text': text,
                'source_url': url
            })
            processed_links.add(href)
            print(f"Found course link: {text}")
    
    return course_links

def is_likely_course_link(href, text):
    """Check if link is likely a course page"""
    href_lower = href.lower()
    text_lower = text.lower()
    
    # URL patterns that suggest course pages
    course_url_patterns = [
        'program', 'course', 'degree', 'diploma', 'bachelor', 'master',
        'bcom', 'mcom', 'bsc', 'msc', 'btech', 'mtech'
    ]
    
    # Text patterns that suggest course names
    course_text_patterns = [
        'bachelor', 'master', 'diploma', 'certificate', 'program',
        'degree', 'course', 'specialization'
    ]
    
    # Check URL
    has_course_url = any(pattern in href_lower for pattern in course_url_patterns)
    
    # Check text (must be substantial)
    has_course_text = (
        any(pattern in text_lower for pattern in course_text_patterns) and
        len(text.split()) >= 2 and
        len(text) >= 10
    )
    
    return has_course_url or has_course_text

def extract_course_info_from_page(course_url, original_text, source_url):
    """Extract course info from individual course page (Title + Body only)"""
    print(f"Getting course info from: {course_url}")
    
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        response = requests.get(course_url, headers=headers, timeout=10)
        response.raise_for_status()
    except Exception as e:
        print(f"Error fetching course page {course_url}: {e}")
        return create_fallback_course_info(original_text, course_url, source_url)

    soup = BeautifulSoup(response.text, "html.parser")
    
    # Get title
    title_elem = soup.find('title') or soup.find('h1')
    course_title = title_elem.get_text(strip=True) if title_elem else original_text
    
    # Clean up title (remove site name, etc.)
    course_title = clean_course_title(course_title)
    
    # Remove navigation from body
    soup = remove_navigation_elements(soup)
    body_content = get_body_content(soup)
    
    # Extract subjects from body content
    subjects = extract_subjects_from_body(body_content)
    
    # Determine degree category
    degree_category = determine_degree_category(source_url, course_title, body_content)
    
    return {
        'course': course_title,
        'degree': degree_category,
        'subjects': subjects,
        'source_url': course_url
    }

def create_fallback_course_info(original_text, course_url, source_url):
    """Create course info when individual page can't be accessed"""
    return {
        'course': clean_course_title(original_text),
        'degree': determine_degree_category(source_url, original_text, None),
        'subjects': [],
        'source_url': course_url
    }

def clean_course_title(title):
    """Clean course title"""
    # Remove common suffixes
    suffixes_to_remove = [
        "| JAIN (Deemed-to-be University)",
        "- JAIN University",
        "| JAIN University",
        "- Home",
        "| Home"
    ]
    
    for suffix in suffixes_to_remove:
        if suffix in title:
            title = title.replace(suffix, "").strip()
    
    # Remove extra whitespace
    title = ' '.join(title.split())
    
    return title

def extract_subjects_from_body(body_content):
    """Extract subjects from body content"""
    if not body_content:
        return []
    
    subjects = []
    body_text = body_content.get_text().lower()
    
    # Common subject keywords
    subject_keywords = [
        'accounting', 'finance', 'economics', 'business management',
        'marketing', 'taxation', 'banking', 'statistics',
        'graphic design', 'animation', 'ui/ux design', 'web design',
        'multimedia', 'photography', 'video editing',
        'physical education', 'sports science', 'exercise physiology',
        'sports psychology', 'anatomy', 'physiology'
    ]
    
    for keyword in subject_keywords:
        if keyword in body_text:
            subjects.append(keyword.title())
    
    return list(set(subjects))  # Remove duplicates

def determine_degree_category(source_url, course_title, body_content):
    """Determine degree category based on source URL and content"""
    source_url_lower = source_url.lower()
    course_title_lower = course_title.lower()
    
    # Check source URL first
    if "commerce" in source_url_lower or "business" in source_url_lower:
        return "Commerce & Management Programs"
    elif "design" in source_url_lower:
        return "Design & Creative Programs"
    elif "sports" in source_url_lower or "physical" in source_url_lower:
        return "Sports & Physical Education Programs"
    
    # Check course title
    if any(word in course_title_lower for word in ['commerce', 'business', 'finance', 'accounting']):
        return "Commerce & Management Programs"
    elif any(word in course_title_lower for word in ['design', 'graphic', 'animation', 'ui', 'ux']):
        return "Design & Creative Programs"
    elif any(word in course_title_lower for word in ['sports', 'physical', 'education']):
        return "Sports & Physical Education Programs"
    
    return "General Programs"

def main():
    """Main scraping function"""
    print("🚀 Starting simple body-content scraping...")
    
    all_courses = []
    
    for source_url in urls:
        print(f"\n--- Processing {source_url} ---")
        
        # Step 1: Get course links from body content only
        course_links = extract_course_links_from_body(source_url)
        print(f"Found {len(course_links)} course links")
        
        # Step 2: Extract info from each course page (title + body)
        for link_info in course_links[:10]:  # Limit to prevent overload
            course_info = extract_course_info_from_page(
                link_info['url'], 
                link_info['text'], 
                source_url
            )
            
            if course_info and len(course_info['course'].split()) >= 3:
                all_courses.append(course_info)
                print(f"✅ Added: {course_info['course']}")
            
            time.sleep(0.5)  # Be respectful
    
    # Remove duplicates
    seen_courses = set()
    unique_courses = []
    
    for course in all_courses:
        course_key = course['course'].lower().strip()
        if course_key not in seen_courses:
            seen_courses.add(course_key)
            unique_courses.append(course)
    
    print(f"\n✅ SCRAPING COMPLETE")
    print(f"📊 Total unique courses: {len(unique_courses)}")
    
    # Save results
    with open("courses.json", "w", encoding='utf-8') as f:
        json.dump(unique_courses, f, indent=2, ensure_ascii=False)
    
    print("💾 Saved to courses.json")
    
    # Show sample
    print("\n📋 Sample courses found:")
    for i, course in enumerate(unique_courses[:5]):
        print(f"{i+1}. {course['course']}")
        print(f"   URL: {course['source_url']}")
        print()

if __name__ == "__main__":
    main()