import requests
from bs4 import BeautifulSoup
import json
import time
import re
from urllib.parse import urljoin, urlparse

class RealtimeCourseScraper:
    def __init__(self):
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        
    def scrape_course_details(self, course_url):
        """
        Scrape detailed information from a specific course page
        Returns comprehensive course details including curriculum, subjects, etc.
        """
        print(f"🔍 Real-time scraping: {course_url}")
        
        try:
            response = requests.get(course_url, headers=self.headers, timeout=15)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Remove navigation and non-content elements
            self._remove_navigation_elements(soup)
            
            # Extract comprehensive course information
            course_details = {
                'url': course_url,
                'title': self._extract_course_title(soup),
                'description': self._extract_detailed_description(soup),
                'curriculum': self._extract_curriculum_details(soup),
                'subjects': self._extract_subjects_comprehensive(soup),
                'duration': self._extract_duration(soup),
                'eligibility': self._extract_eligibility(soup),
                'career_prospects': self._extract_career_prospects(soup),
                'specializations': self._extract_specializations(soup),
                'highlights': self._extract_course_highlights(soup),
                'fees_info': self._extract_fees_information(soup),
                'admission_process': self._extract_admission_process(soup),
                'full_content': self._extract_all_visible_content(soup)
            }
            
            print(f"✅ Successfully scraped {len(course_details['curriculum'])} curriculum items")
            print(f"✅ Found {len(course_details['subjects'])} subjects")
            
            return course_details
            
        except Exception as e:
            print(f"❌ Error scraping {course_url}: {e}")
            return None
    
    def _remove_navigation_elements(self, soup):
        """Remove navigation, header, footer elements"""
        elements_to_remove = [
            'header', 'footer', 'nav', 'aside',
            '[class*="nav"]', '[class*="menu"]', '[class*="header"]', '[class*="footer"]',
            '[id*="nav"]', '[id*="menu"]', '[id*="header"]', '[id*="footer"]',
            'script', 'style', 'noscript', '.breadcrumb'
        ]
        
        for selector in elements_to_remove:
            for element in soup.select(selector):
                element.decompose()
    
    def _extract_course_title(self, soup):
        """Extract clean course title"""
        title_selectors = ['h1', 'title', '.course-title', '.page-title']
        
        for selector in title_selectors:
            title_elem = soup.select_one(selector)
            if title_elem:
                title = title_elem.get_text(strip=True)
                # Clean title
                title = re.sub(r'\s*\|\s*JAIN.*', '', title)
                title = re.sub(r'\s*-\s*JAIN.*', '', title)
                return title.strip()
        
        return "Course Title Not Found"
    
    def _extract_detailed_description(self, soup):
        """Extract comprehensive course description"""
        description_parts = []
        
        # Look for description in various places
        description_selectors = [
            '.course-description',
            '.programme-description', 
            '.program-overview',
            '.course-overview',
            'p:contains("programme")',
            'p:contains("course")',
            'div:contains("designed")'
        ]
        
        for selector in description_selectors:
            elements = soup.select(selector)
            for elem in elements:
                text = elem.get_text(strip=True)
                if len(text) > 100:  # Only substantial descriptions
                    description_parts.append(text)
        
        # Also get first few substantial paragraphs
        paragraphs = soup.find_all('p')
        for p in paragraphs[:10]:
            text = p.get_text(strip=True)
            if len(text) > 80 and not any(skip in text.lower() for skip in ['cookie', 'javascript', 'error']):
                description_parts.append(text)
        
        # Combine and deduplicate
        unique_descriptions = []
        seen_text = set()
        
        for desc in description_parts:
            # Use first 100 chars as key to avoid exact duplicates
            key = desc[:100].lower()
            if key not in seen_text:
                seen_text.add(key)
                unique_descriptions.append(desc)
        
        return ' '.join(unique_descriptions[:3])  # Top 3 unique descriptions
    
    def _extract_curriculum_details(self, soup):
        """Extract detailed curriculum including semester-wise breakdown"""
        curriculum_items = []
        
        # Get all text content
        full_text = soup.get_text()
        
        # Pattern 1: Semester-wise curriculum
        semester_patterns = [
            r'semester\s+(\d+)[:\-]?\s*([^.]+(?:\.[^.]+){0,20})',
            r'sem\s+(\d+)[:\-]?\s*([^.]+(?:\.[^.]+){0,15})',
            r'year\s+(\d+)[:\-]?\s*([^.]+(?:\.[^.]+){0,15})'
        ]
        
        for pattern in semester_patterns:
            matches = re.findall(pattern, full_text, re.IGNORECASE | re.DOTALL)
            for sem_num, content in matches:
                if len(content.strip()) > 30:
                    curriculum_items.append(f"Semester {sem_num}: {content.strip()}")
        
        # Pattern 2: Subject lists
        subject_list_patterns = [
            r'courses?\s+offered[:\-]?\s*([^.]+(?:\.[^.]+){0,10})',
            r'subjects?[:\-]?\s*([^.]+(?:\.[^.]+){0,10})',
            r'curriculum[:\-]?\s*([^.]+(?:\.[^.]+){0,15})'
        ]
        
        for pattern in subject_list_patterns:
            matches = re.findall(pattern, full_text, re.IGNORECASE | re.DOTALL)
            for match in matches:
                if len(match.strip()) > 30:
                    curriculum_items.append(match.strip())
        
        # Pattern 3: Look for structured curriculum in tables or lists
        tables = soup.find_all('table')
        for table in tables:
            table_text = table.get_text(separator=' | ', strip=True)
            if len(table_text) > 50 and any(word in table_text.lower() for word in ['semester', 'course', 'subject']):
                curriculum_items.append(f"Curriculum Table: {table_text[:500]}")
        
        lists = soup.find_all(['ul', 'ol'])
        for lst in lists:
            list_text = lst.get_text(separator=' • ', strip=True)
            if len(list_text) > 100 and any(word in list_text.lower() for word in ['design', 'management', 'research', 'project']):
                curriculum_items.append(f"Course Structure: {list_text[:400]}")
        
        return curriculum_items[:10]  # Limit to 10 items
    
    def _extract_subjects_comprehensive(self, soup):
        """Extract comprehensive list of subjects taught"""
        subjects = set()
        
        full_text = soup.get_text().lower()
        
        # Comprehensive subject keywords for different domains
        subject_mapping = {
            # Business & Commerce
            'Accounting': ['accounting', 'financial accounting', 'cost accounting'],
            'Finance': ['finance', 'financial management', 'corporate finance'],
            'Marketing': ['marketing', 'digital marketing', 'consumer behavior'],
            'Economics': ['economics', 'microeconomics', 'macroeconomics'],
            'Business Management': ['business management', 'organizational behavior'],
            'Taxation': ['taxation', 'tax planning', 'income tax'],
            'Banking': ['banking', 'financial institutions', 'commercial banking'],
            'Statistics': ['statistics', 'business statistics', 'data analysis'],
            'Entrepreneurship': ['entrepreneurship', 'startup management', 'innovation'],
            
            # Design & Creative
            'Graphic Design': ['graphic design', 'visual design', 'typography'],
            'UI/UX Design': ['ui design', 'ux design', 'user experience', 'user interface'],
            'Animation': ['animation', '2d animation', '3d animation', 'motion graphics'],
            'Web Design': ['web design', 'responsive design', 'front-end'],
            'Photography': ['photography', 'digital photography', 'photo editing'],
            'Multimedia': ['multimedia', 'digital media', 'interactive media'],
            'Design Thinking': ['design thinking', 'human-centered design'],
            'Prototyping': ['prototyping', 'wireframing', 'mockups'],
            
            # Technology & Computing
            'Programming': ['programming', 'coding', 'software development'],
            'Data Science': ['data science', 'machine learning', 'artificial intelligence'],
            'Web Development': ['web development', 'javascript', 'html', 'css'],
            'Database Management': ['database', 'sql', 'data management'],
            
            # Sports & Physical Education
            'Sports Science': ['sports science', 'exercise science', 'kinesiology'],
            'Physical Education': ['physical education', 'sports training'],
            'Exercise Physiology': ['exercise physiology', 'human physiology'],
            'Sports Psychology': ['sports psychology', 'mental training'],
            'Anatomy': ['anatomy', 'human anatomy', 'biomechanics'],
            
            # General Academic
            'Research Methods': ['research methodology', 'research methods'],
            'Project Management': ['project management', 'agile methodology'],
            'Communication Skills': ['communication', 'presentation skills'],
            'Ethics': ['ethics', 'professional ethics', 'moral philosophy']
        }
        
        # Check for each subject
        for subject, keywords in subject_mapping.items():
            if any(keyword in full_text for keyword in keywords):
                subjects.add(subject)
        
        return list(subjects)
    
    def _extract_duration(self, soup):
        """Extract course duration"""
        text = soup.get_text().lower()
        
        duration_patterns = [
            r'(\d+)\s*years?',
            r'duration[:\-]?\s*(\d+\s*years?)',
            r'(\d+)\s*semesters?'
        ]
        
        for pattern in duration_patterns:
            match = re.search(pattern, text)
            if match:
                return match.group(0)
        
        return "Duration not specified"
    
    def _extract_eligibility(self, soup):
        """Extract eligibility criteria"""
        text = soup.get_text()
        
        eligibility_patterns = [
            r'eligibility[:\-]?\s*([^.]+(?:\.[^.]+){0,3})',
            r'qualification[:\-]?\s*([^.]+(?:\.[^.]+){0,3})',
            r'10\+2[^.]*(?:\.[^.]*){0,2}'
        ]
        
        for pattern in eligibility_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(0)[:300]  # Limit length
        
        return "Please check official website for eligibility"
    
    def _extract_career_prospects(self, soup):
        """Extract career opportunities and prospects"""
        career_info = []
        text = soup.get_text()
        
        career_patterns = [
            r'career[^.]*(?:\.[^.]*){0,5}',
            r'opportunities[^.]*(?:\.[^.]*){0,3}',
            r'jobs?[^.]*(?:\.[^.]*){0,3}',
            r'employment[^.]*(?:\.[^.]*){0,3}'
        ]
        
        for pattern in career_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            for match in matches:
                if len(match) > 50:
                    career_info.append(match[:200])
        
        return career_info[:3]  # Top 3 career-related info
    
    def _extract_specializations(self, soup):
        """Extract available specializations"""
        text = soup.get_text().lower()
        specializations = []
        
        spec_patterns = [
            r'specialization[^.]*(?:\.[^.]*){0,3}',
            r'specialisation[^.]*(?:\.[^.]*){0,3}',
            r'concentration[^.]*(?:\.[^.]*){0,2}'
        ]
        
        for pattern in spec_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            specializations.extend([m[:150] for m in matches if len(m) > 20])
        
        return specializations[:3]
    
    def _extract_course_highlights(self, soup):
        """Extract key course highlights"""
        highlights = []
        
        # Look for bullet points and lists
        lists = soup.find_all(['ul', 'ol'])
        for lst in lists:
            items = lst.find_all('li')
            for item in items[:5]:  # First 5 items from each list
                text = item.get_text(strip=True)
                if 20 < len(text) < 150:  # Reasonable length
                    highlights.append(text)
        
        return highlights[:8]  # Top 8 highlights
    
    def _extract_fees_information(self, soup):
        """Extract fee structure if available"""
        text = soup.get_text().lower()
        
        fee_patterns = [
            r'fees?[^.]*(?:\.[^.]*){0,2}',
            r'cost[^.]*(?:\.[^.]*){0,2}',
            r'tuition[^.]*(?:\.[^.]*){0,2}'
        ]
        
        for pattern in fee_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match and any(char.isdigit() for char in match.group(0)):
                return match.group(0)[:200]
        
        return "Please contact university for fee details"
    
    def _extract_admission_process(self, soup):
        """Extract admission process information"""
        text = soup.get_text()
        
        admission_patterns = [
            r'admission[^.]*(?:\.[^.]*){0,4}',
            r'application[^.]*(?:\.[^.]*){0,3}',
            r'entrance[^.]*(?:\.[^.]*){0,2}'
        ]
        
        for pattern in admission_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(0)[:300]
        
        return "Check official website for admission details"
    
    def _extract_all_visible_content(self, soup):
        """Extract all visible content for comprehensive context"""
        # Get main content area
        main_content = soup.find('main') or soup.find('body')
        if main_content:
            text = main_content.get_text(separator=' ', strip=True)
            # Clean up and limit length
            text = ' '.join(text.split())  # Normalize whitespace
            return text[:3000]  # Limit to 3000 chars for context
        return ""

# Global scraper instance
_realtime_scraper = RealtimeCourseScraper()

def scrape_course_page_realtime(course_url):
    """
    Public function to scrape a course page in real-time
    Returns detailed course information
    """
    return _realtime_scraper.scrape_course_details(course_url)

def format_scraped_content_for_ai(scraped_data):
    """
    Format scraped content for AI consumption
    Returns a well-structured text for the AI advisor
    """
    if not scraped_data:
        return "Unable to retrieve detailed course information at this time."
    
    formatted_content = f"""
DETAILED COURSE INFORMATION:

Course Title: {scraped_data.get('title', 'N/A')}

Description: {scraped_data.get('description', 'N/A')[:800]}

Duration: {scraped_data.get('duration', 'N/A')}

Eligibility: {scraped_data.get('eligibility', 'N/A')}

SUBJECTS COVERED:
{', '.join(scraped_data.get('subjects', ['Information not available']))}

CURRICULUM DETAILS:
{chr(10).join(scraped_data.get('curriculum', ['Detailed curriculum not available'])[:5])}

COURSE HIGHLIGHTS:
{chr(10).join([f"• {h}" for h in scraped_data.get('highlights', [])[:5]])}

CAREER PROSPECTS:
{chr(10).join(scraped_data.get('career_prospects', ['Career information not available'])[:2])}

SPECIALIZATIONS:
{chr(10).join(scraped_data.get('specializations', ['No specializations listed'])[:3])}

ADMISSION PROCESS: {scraped_data.get('admission_process', 'Check official website')}

For the most current information, visit: {scraped_data.get('url', 'N/A')}
"""
    
    return formatted_content