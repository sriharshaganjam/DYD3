# course_diagnostic.py - Check what's in your courses.json
import json
from collections import Counter

def analyze_courses():
    """Analyze the courses.json file to see what's being loaded"""
    
    try:
        with open("courses.json", "r") as f:
            courses = json.load(f)
    except FileNotFoundError:
        print("❌ courses.json not found. Please run the scraper first.")
        return
    
    print(f"📊 Total courses found: {len(courses)}")
    print("\n" + "="*50)
    
    # Analyze by degree category
    degree_categories = Counter()
    source_urls = Counter()
    
    print("🎓 COURSES BY CATEGORY:")
    print("-" * 30)
    
    for course in courses:
        degree = course.get('degree', 'Unknown')
        source_url = course.get('source_url', 'Unknown')
        
        degree_categories[degree] += 1
        source_urls[source_url] += 1
    
    for category, count in degree_categories.most_common():
        print(f"  {category}: {count} courses")
    
    print(f"\n🔗 COURSES BY SOURCE URL:")
    print("-" * 30)
    
    for url, count in source_urls.most_common():
        print(f"  {count} courses from: {url}")
    
    # Check for engineering courses specifically
    print(f"\n🔍 ENGINEERING COURSE CHECK:")
    print("-" * 30)
    
    engineering_courses = []
    for course in courses:
        course_name = course.get('course', '').lower()
        degree_name = course.get('degree', '').lower()
        
        if any(eng_word in course_name or eng_word in degree_name 
               for eng_word in ['engineering', 'engineer', 'b.tech', 'btech', 'm.tech', 'mtech']):
            engineering_courses.append({
                'name': course.get('course', ''),
                'degree': course.get('degree', ''),
                'url': course.get('source_url', '')
            })
    
    if engineering_courses:
        print(f"⚠️  Found {len(engineering_courses)} engineering courses:")
        for i, course in enumerate(engineering_courses[:5], 1):  # Show first 5
            print(f"  {i}. {course['name']}")
            print(f"     Category: {course['degree']}")
            print(f"     Source: {course['url']}")
            print()
        if len(engineering_courses) > 5:
            print(f"  ... and {len(engineering_courses) - 5} more")
    else:
        print("✅ No engineering courses found")
    
    # Check for sports courses
    print(f"\n🏃 SPORTS COURSE CHECK:")
    print("-" * 30)
    
    sports_courses = []
    for course in courses:
        course_name = course.get('course', '').lower()
        degree_name = course.get('degree', '').lower()
        
        if any(sports_word in course_name or sports_word in degree_name 
               for sports_word in ['sports', 'sport', 'physical education', 'athletics', 'fitness']):
            sports_courses.append({
                'name': course.get('course', ''),
                'degree': course.get('degree', ''),
                'url': course.get('source_url', '')
            })
    
    if sports_courses:
        print(f"✅ Found {len(sports_courses)} sports courses:")
        for i, course in enumerate(sports_courses, 1):
            print(f"  {i}. {course['name']}")
            print(f"     Category: {course['degree']}")
            print(f"     Source: {course['url']}")
            print()
    else:
        print("❌ No sports courses found")
    
    # Sample of all courses
    print(f"\n📋 SAMPLE COURSES (first 10):")
    print("-" * 30)
    
    for i, course in enumerate(courses[:10], 1):
        print(f"  {i}. {course.get('course', 'No name')}")
        print(f"     Category: {course.get('degree', 'No category')}")
        print(f"     URL: {course.get('source_url', 'No URL')}")
        print()

if __name__ == "__main__":
    analyze_courses()