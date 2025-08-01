# enhanced_scraper.py - Enhanced scraper that captures hidden/collapsed content
import requests
from bs4 import BeautifulSoup
import json
from urllib.parse import urljoin
import time
import re

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

def extract_all_content_including_hidden(body_content):
    """Extract all content including hidden/collapsed sections"""
    if not body_content:
        return ""
    
    # Get all text including hidden content
    all_text = body_content.get_text(separator=' ', strip=True)
    
    # Also look for specific collapsed content patterns
    collapsed_content = []
    
    # Look for common collapse/accordion patterns
    collapse_selectors = [
        '.collapse', '.accordion', '.collapsible', 
        '[data-toggle="collapse"]', '[aria-expanded]',
        '.tab-content', '.tab-pane', '.hidden', '.show-more'
    ]
    
    for selector in collapse_selectors:
        elements = body_content.select(selector)
        for element in elements:
            collapsed_text = element.get_text(separator=' ', strip=True)
            if collapsed_text and len(collapsed_text) > 20:
                collapsed_content.append(collapsed_text)
    
    # Combine all content
    combined_content = all_text
    if collapsed_content:
        combined_content += " " + " ".join(collapsed_content)
    
    return combined_content

def extract_detailed_curriculum(body_content):
    """Extract detailed curriculum information including hidden sections"""
    if not body_content:
        return []
    
    curriculum_data = []
    
    # Get all text content including hidden sections
    full_text = extract_all_content_including_hidden(body_content)
    
    # Look for curriculum patterns
    curriculum_patterns = [
        r'semester\s+\d+[:\-]?\s*([^.]+(?:\.[^.]+){0,10})',
        r'year\s+\d+[:\-]?\s*([^.]+(?:\.[^.]+){0,10})',
        r'module\s+\d+[:\-]?\s*([^.]+(?:\.[^.]+){0,5})',
        r'course\s+structure[:\-]?\s*([^.]+(?:\.[^.]+){0,15})'
    ]
    
    for pattern in curriculum_patterns:
        matches = re.findall(pattern, full_text, re.IGNORECASE | re.DOTALL)
        for match in matches:
            if len(match.strip()) > 20:  # Only substantial content
                curriculum_data.append(match.strip())
    
    # Look for subject lists
    subject_lines = []
    lines = full_text.split('\n')
    for line in lines:
        line_clean = line.strip()
        # Look for lines that might be subjects
        if (len(line_clean) > 10 and len(line_clean) < 100 and 
            not line_clean.startswith('http') and
            any(subject_word in line_clean.lower() for subject_word in 
                ['design', 'research', 'psychology', 'engineering', 'management', 'analysis', 'development'])):
            subject_lines.append(line_clean)
    
    if subject_lines:
        curriculum_data.extend(subject_lines[:10])  # Limit to 10 most relevant
    
    return curriculum_data

def extract_course_info_from_page(course_url, original_text, source_url):
    """Extract comprehensive course info including hidden content"""
    print(f"Getting detailed course info from: {course_url}")
    
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        response = requests.get(course_url, headers=headers, timeout=15)
        response.raise_for_status()
    except Exception as e:
        print(f"Error fetching course page {course_url}: {e}")
        return create_fallback_course_info(original_text, course_url, source_url)

    soup = BeautifulSoup(response.text, "html.parser")
    
    # Get title
    title_elem = soup.find('title') or soup.find('h1')
    course_title = title_elem.get_text(strip=True) if title_elem else original_text
    
    # Clean up title
    course_title = clean_course_title(course_title)
    
    # Remove navigation from body
    soup = remove_navigation_elements(soup)
    body_content = get_body_content(soup)
    
    # Extract subjects from body content (including hidden)
    subjects = extract_subjects_from_body_enhanced(body_content)
    
    # Extract detailed curriculum including hidden sections
    curriculum = extract_detailed_curriculum(body_content)
    
    # Extract comprehensive course description
    description = extract_course_description(body_content)
    
    # Determine degree category
    degree_category = determine_degree_category(source_url, course_title, body_content)
    
    return {
        'course': course_title,
        'degree': degree_category,
        'subjects': subjects,
        'curriculum': curriculum,
        'description': description,
        'source_url': course_url
    }

def extract_subjects_from_body_enhanced(body_content):
    """Enhanced subject extraction including hidden content"""
    if not body_content:
        return []
    
    subjects = []
    
    # Get all text including hidden sections
    full_text = extract_all_content_including_hidden(body_content).lower()
    
    # Enhanced subject keywords
    subject_keywords = [
        'accounting', 'finance', 'economics', 'business management',
        'marketing', 'taxation', 'banking', 'statistics',
        'graphic design', 'animation', 'ui/ux design', 'web design',
        'multimedia', 'photography', 'video editing', 'interaction design',
        'user experience', 'human-centered design', 'design thinking',
        'prototyping', 'usability', 'cognitive psychology',
        'physical education', 'sports science', 'exercise physiology',
        'sports psychology', 'anatomy', 'physiology', 'research methods',
        'ethnographic methods', 'complexity science', 'human factors',
        'ergonomics', 'modeling', 'simulation', 'accessibility',
        'sustainability', 'cross-cultural', 'emerging technologies',
        'social innovation'
    ]
    
    for keyword in subject_keywords:
        if keyword in full_text:
            subjects.append(keyword.title())
    
    return list(set(subjects))  # Remove duplicates

def extract_course_description(body_content):
    """Extract comprehensive course description"""
    if not body_content:
        return ""
    
    # Get first few paragraphs as description
    paragraphs = body_content.find_all('p')
    description_parts = []
    
    for p in paragraphs[:5]:  # First 5 paragraphs
        text = p.get_text(strip=True)
        if len(text) > 50:  # Only substantial paragraphs
            description_parts.append(text)
    
    return " ".join(description_parts)[:500]  # Limit to 500 chars

def create_fallback_course_info(original_text, course_url, source_url):
    """Create minimal course info when page can't be accessed"""
    return {
        'course': clean_course_title(original_text),
        'degree': determine_degree_category(source_url, original_text, None),
        'subjects': [],
        'curriculum': [],
        'description': "",
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
    """Main scraping function with enhanced content extraction"""
    print("🚀 Starting enhanced scraping with hidden content support...")
    
    all_courses = []
    
    for source_url in urls:
        print(f"\n--- Processing {source_url} ---")
        
        # Step 1: Get course links from body content only
        course_links = extract_course_links_from_body(source_url)
        print(f"Found {len(course_links)} course links")
        
        # Step 2: Extract comprehensive info from each course page
        for link_info in course_links[:15]:  # Increased limit for better coverage
            course_info = extract_course_info_from_page(
                link_info['url'], 
                link_info['text'], 
                source_url
            )
            
            if course_info and len(course_info['course'].split()) >= 3:
                all_courses.append(course_info)
                print(f"✅ Added: {course_info['course']}")
                print(f"   Subjects: {course_info['subjects'][:3]}...")  # Show first 3 subjects
                print(f"   Curriculum items: {len(course_info['curriculum'])}")
            
            time.sleep(0.7)  # Be respectful
    
    # Remove duplicates
    seen_courses = set()
    unique_courses = []
    
    for course in all_courses:
        course_key = course['course'].lower().strip()
        if course_key not in seen_courses:
            seen_courses.add(course_key)
            unique_courses.append(course)
    
    print(f"\n✅ ENHANCED SCRAPING COMPLETE")
    print(f"📊 Total unique courses: {len(unique_courses)}")
    
    # Save results
    with open("courses_enhanced.json", "w", encoding='utf-8') as f:
        json.dump(unique_courses, f, indent=2, ensure_ascii=False)
    
    print("💾 Saved to courses_enhanced.json")
    
    # Show sample with enhanced data
    print("\n📋 Sample courses with enhanced data:")
    for i, course in enumerate(unique_courses[:3]):
        print(f"{i+1}. {course['course']}")
        print(f"   Subjects: {course['subjects'][:5]}")
        print(f"   Curriculum: {len(course['curriculum'])} items")
        print(f"   Description: {course['description'][:100]}...")
        print(f"   URL: {course['source_url']}")
        print()

if __name__ == "__main__":
    main()