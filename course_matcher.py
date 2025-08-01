import json
import os
import openai
from dotenv import load_dotenv

# Import FAISS matcher
try:
    from embedding_matcher import get_enhanced_recommendations
    FAISS_AVAILABLE = True
    print("✅ FAISS embeddings system loaded successfully!")
except ImportError as e:
    FAISS_AVAILABLE = False
    print(f"⚠️ FAISS not available: {e}. Using fallback keyword matching.")

# Load API key from .env
load_dotenv()
openai.api_key = os.getenv("MISTRAL_API_KEY")

# Set Mistral endpoint (official API)
openai.api_base = "https://api.mistral.ai/v1"

def load_courses(path="courses.json"):
    with open(path, "r") as f:
        return json.load(f)

def get_smart_course_recommendations(profile, courses, chat_history=[]):
    """Get course recommendations using FAISS (with fallback)"""
    
    if FAISS_AVAILABLE:
        try:
            # Use FAISS-based semantic matching
            recommended_courses, context_course = get_enhanced_recommendations(
                profile, courses, chat_history
            )
            
            return recommended_courses, context_course
            
        except Exception as e:
            print(f"⚠️ FAISS failed, using fallback: {e}")
            # Fall back to keyword matching
            return filter_and_match_courses_fallback(courses, profile), None
    else:
        # Use original keyword matching
        return filter_and_match_courses_fallback(courses, profile), None

def filter_and_match_courses_fallback(courses, profile):
    """Fallback keyword-based matching (preserves original logic)"""
    degree_level = profile.get("degree_level", "Bachelor's Degree")
    interests = profile.get("interests", [])
    activities = profile.get("activities", [])
    
    # First filter by degree level
    filtered_courses = []
    for course in courses:
        course_name = course.get('course', '').lower()
        
        if degree_level == "Bachelor's Degree":
            bachelor_keywords = ['bachelor', 'b.com', 'b.sc', 'b.tech', 'b.des', 'b.p.ed', 'undergraduate']
            if any(keyword in course_name for keyword in bachelor_keywords):
                filtered_courses.append(course)
        
        elif degree_level == "Master's Degree":
            master_keywords = ['master', 'm.com', 'm.sc', 'm.tech', 'm.des', 'm.p.ed', 'postgraduate']
            if any(keyword in course_name for keyword in master_keywords):
                filtered_courses.append(course)
    
    # Enhanced matching with MEDIUM weight for activities
    if interests or activities:
        highly_matched_courses = []
        moderately_matched_courses = []
        unmatched_courses = []
        
        for course in filtered_courses:
            course_text = (course.get('course', '') + ' ' + course.get('degree', '')).lower()
            
            interest_match = False
            activity_match = False
            
            # Check interest matching
            for interest in interests:
                interest_lower = interest.lower()
                if interest_lower in course_text or any(word in course_text for word in interest_lower.split()):
                    interest_match = True
                    break
            
            # Check activity matching - MEDIUM WEIGHTAGE
            activity_course_mapping = {
                "leadership": ["management", "business", "administration", "leadership"],
                "technical projects": ["computer", "technology", "engineering", "software"],
                "creative arts": ["design", "art", "creative", "visual", "communication"],
                "sports": ["sports", "physical education", "athletics", "fitness"],
                "community service": ["social work", "psychology", "counseling", "humanities"],
                "academic excellence": ["research", "science", "mathematics", "academic"],
                "performance": ["music", "performing arts", "media", "communication"],
                "business": ["business", "commerce", "management", "finance", "entrepreneurship"]
            }
            
            for activity in activities:
                activity_lower = activity.lower()
                for activity_type, course_keywords in activity_course_mapping.items():
                    if activity_type in activity_lower:
                        if any(keyword in course_text for keyword in course_keywords):
                            activity_match = True
                            break
                if activity_match:
                    break
            
            # Prioritize based on both interest and activity matches
            if interest_match and activity_match:
                highly_matched_courses.append(course)
            elif interest_match or activity_match:
                moderately_matched_courses.append(course)
            else:
                unmatched_courses.append(course)
        
        return highly_matched_courses + moderately_matched_courses + unmatched_courses
    
    return filtered_courses[:10]

def extract_suggested_courses_from_chat(chat_history):
    """Extract the courses that were most recently suggested to the student"""
    # Look for the most recent assistant message with course suggestions
    for message in reversed(chat_history):
        if message.get("role") == "assistant":
            content = message.get("content", "")
            
            # Look for course mentions in the format **Course Name**
            import re
            course_pattern = r'\*\*([^*]+(?:Bachelor|Master|B\.Com|B\.Des|B\.Sc|M\.Com|M\.Des|M\.Sc)[^*]*)\*\*'
            matches = re.findall(course_pattern, content, re.IGNORECASE)
            
            if matches and len(matches) <= 4:  # Should be 3 courses max
                # Clean up the matches
                suggested_courses = []
                for match in matches[:3]:  # Take only first 3
                    clean_course = match.strip()
                    if len(clean_course) > 10:  # Ensure it's a substantial course name
                        suggested_courses.append(clean_course)
                
                if suggested_courses:
                    print(f"🎯 Found {len(suggested_courses)} suggested courses: {suggested_courses}")
                    return suggested_courses
    
    return []

def identify_course_from_user_query(user_message, suggested_courses):
    """Identify which of the suggested courses the user is asking about"""
    if not user_message or not suggested_courses:
        return None
    
    user_message_lower = user_message.lower()
    
    # Create variations of course names for better matching
    course_variations = {}
    for course in suggested_courses:
        course_lower = course.lower()
        variations = [course_lower]
        
        # Add key words from course name
        words = course_lower.split()
        for word in words:
            if len(word) > 3:  # Only meaningful words
                variations.append(word)
        
        # Add specific course type variations
        if "bachelor of commerce" in course_lower or "b.com" in course_lower:
            variations.extend(["commerce", "b.com", "bcom", "business"])
        elif "physical education" in course_lower and "sports" in course_lower:
            variations.extend(["sports", "physical education", "athletics", "pe"])
        elif "design" in course_lower:
            variations.extend(["design", "creative", "graphic"])
        
        course_variations[course] = variations
    
    # Find best match
    best_match = None
    max_matches = 0
    
    for course, variations in course_variations.items():
        match_count = sum(1 for variation in variations if variation in user_message_lower)
        if match_count > max_matches:
            max_matches = match_count
            best_match = course
    
    if best_match and max_matches > 0:
        print(f"🎯 User asking about: {best_match}")
        return best_match
    
    return None

def extract_domain_request(user_message):
    """Extract specific domain/field the user is requesting - flexible for any domain"""
    if not user_message:
        return None
    
    message_lower = user_message.lower()
    
    # Generic domain mappings - can be extended for any field
    domain_keywords = {
        "Technology": ["ai", "artificial intelligence", "technology", "tech", "computer", "software", "data science", "machine learning", "programming", "coding"],
        "Design": ["design", "creative", "art", "graphic", "ui", "ux", "visual", "animation", "multimedia"],
        "Business": ["business", "management", "finance", "commerce", "entrepreneurship", "marketing", "banking", "accounting"],
        "Sports": ["sports", "physical education", "athletics", "fitness", "pe", "exercise"],
        "Science": ["science", "research", "physics", "chemistry", "biology", "mathematics", "math", "engineering"],
        "Media": ["media", "journalism", "communication", "broadcasting", "film", "photography"],
        "Health": ["health", "medical", "healthcare", "nursing", "medicine", "therapy"],
        "Education": ["education", "teaching", "pedagogy", "academic", "learning"]
    }
    
    for domain, keywords in domain_keywords.items():
        if any(keyword in message_lower for keyword in keywords):
            return domain
    
    return None

def filter_courses_by_domain(courses, domain_request, degree_level):
    """Filter courses by requested domain - flexible for any field"""
    filtered_courses = []
    
    # First filter by degree level
    degree_filtered = []
    for course in courses:
        course_name = course.get('course', '').lower()
        
        if degree_level == "Bachelor's Degree":
            bachelor_keywords = ['bachelor', 'b.com', 'b.sc', 'b.tech', 'b.des', 'b.p.ed', 'undergraduate']
            if any(keyword in course_name for keyword in bachelor_keywords):
                degree_filtered.append(course)
        elif degree_level == "Master's Degree":
            master_keywords = ['master', 'm.com', 'm.sc', 'm.tech', 'm.des', 'm.p.ed', 'postgraduate']
            if any(keyword in course_name for keyword in master_keywords):
                degree_filtered.append(course)
    
    # Domain filtering keywords - comprehensive for any field
    domain_keywords = {
        "Technology": ["technology", "computer", "data", "software", "tech", "ai", "artificial", "intelligence", "programming", "coding"],
        "Design": ["design", "creative", "art", "graphic", "visual", "animation", "ui", "ux", "multimedia"],
        "Business": ["business", "management", "finance", "commerce", "entrepreneurship", "marketing", "banking", "accounting"],
        "Sports": ["sports", "physical", "athletics", "fitness", "exercise", "pe"],
        "Science": ["science", "research", "physics", "chemistry", "biology", "mathematics", "engineering"],
        "Media": ["media", "journalism", "communication", "broadcasting", "film", "photography"],
        "Health": ["health", "medical", "healthcare", "nursing", "medicine", "therapy"],
        "Education": ["education", "teaching", "pedagogy", "academic", "learning"]
    }
    
    relevant_keywords = domain_keywords.get(domain_request, [])
    
    for course in degree_filtered:
        course_text = (course.get('course', '') + ' ' + course.get('degree', '') + ' ' + ' '.join(course.get('subjects', []))).lower()
        
        if any(keyword in course_text for keyword in relevant_keywords):
            filtered_courses.append(course)
    
    # If no domain-specific courses found, return general courses
    return filtered_courses if filtered_courses else degree_filtered[:10]

def check_if_asking_for_more_suggestions(user_message):
    """Check if user wants to see different/more course options - domain agnostic"""
    if not user_message:
        return False
    
    message_lower = user_message.lower()
    
    # Comprehensive keyword detection for ANY field
    more_suggestions_keywords = [
        # Direct requests for more
        "more courses", "more options", "additional courses", "other courses",
        "different courses", "alternatives", "other programs", "other options",
        "more programs", "additional programs", "further options", "extra courses",
        
        # Show/suggest patterns
        "show me more", "suggest more", "recommend more", "give me more",
        "can you suggest more", "any more", "what else", "anything else",
        "show other", "suggest other", "recommend other", "give me other",
        
        # Different/alternative patterns
        "different options", "alternative options", "other choices", "different field",
        "change course", "something different", "explore other", "look at other",
        "see more", "additional options", "further suggestions"
    ]
    
    # Generic patterns for "suggest some [any topic] courses"
    suggest_patterns = [
        r"suggest some .+ courses",
        r"recommend some .+ courses", 
        r"show me .+ courses",
        r"any .+ courses",
        r"more .+ courses",
        r"other .+ courses",
        r"different .+ courses",
        r"additional .+ courses",
        r"can you suggest .+ courses",
        r"give me .+ courses"
    ]
    
    # Check direct keywords
    keyword_match = any(keyword in message_lower for keyword in more_suggestions_keywords)
    
    # Check patterns with regex - this catches any field/domain
    import re
    pattern_match = any(re.search(pattern, message_lower) for pattern in suggest_patterns)
    
    return keyword_match or pattern_match

def prepare_initial_prompt(profile, courses):
    """Prepare the initial recommendation prompt - EXACTLY as many courses as available (max 3)"""
    profile_str = json.dumps(profile, indent=2)
    degree_level = profile.get("degree_level", "Bachelor's Degree")
    
    # Get smart recommendations (FAISS or fallback)
    relevant_courses, _ = get_smart_course_recommendations(profile, courses, [])
    
    # Create course catalog with REAL courses only - no hallucination
    course_catalog = ""
    seen_courses = set()
    selected_courses = []
    
    for c in relevant_courses:
        course_name = c.get('course', '')
        degree_name = c.get('degree', '')
        source_url = c.get('source_url', '')
        
        if (course_name, degree_name) in seen_courses or len(course_name.split()) < 3:
            continue
            
        seen_courses.add((course_name, degree_name))
        selected_courses.append(c)
        
        subjects = c.get('subjects', [])
        subjects_str = f" (Subjects: {', '.join(subjects)})" if subjects else ""
        
        course_catalog += f"- **{course_name}** from {degree_name}{subjects_str}\n  URL: {source_url}\n\n"
        
        if len(selected_courses) >= 3:  # Maximum 3 courses
            break

    # Check if we have any courses
    if not selected_courses:
        return f"""
You are an expert academic advisor helping students choose the right university course.

Student Profile: {profile_str}

CRITICAL: I'm sorry, but I don't have any {degree_level} courses available in our database that match your requirements at this time. 

This could be because:
1. Our course database is currently limited
2. No courses match your specific interests and academic background
3. The courses haven't been updated in our system yet

I recommend:
- Checking the university website directly for the most current course offerings
- Contacting the admissions office for personalized guidance
- Exploring different degree levels or related fields

I apologize that I cannot provide specific course recommendations right now.
"""

    # Check if profile needs clarification
    needs_clarification = profile.get("needs_clarification", False)
    clarifying_questions = profile.get("clarifying_questions", [])
    completeness_score = profile.get("completeness_score", 100)

    if needs_clarification and clarifying_questions:
        prompt = f"""
You are an expert academic advisor helping students choose the right university course.

Here is the student's current profile:
{profile_str}

IMPORTANT: The student's profile is only {completeness_score}% complete. Before giving course recommendations, you need to gather more information.

Your task:
1. Acknowledge what information you have about the student
2. Explain that you'd like to understand them better to give more personalized recommendations
3. Ask ONE of these clarifying questions (choose the most important one):
{chr(10).join([f"- {q}" for q in clarifying_questions[:2]])}

4. Be encouraging and explain that this will help you suggest the best-fit courses

Keep your response friendly and conversational. Don't recommend specific courses yet - focus on gathering more information first.
"""
    else:
        # Determine exact number of courses available
        num_courses = len(selected_courses)
        course_word = "course" if num_courses == 1 else "courses"
        
        prompt = f"""
You are an expert academic advisor helping students choose the right university course.

Here is the student's profile:
{profile_str}

AVAILABLE COURSES: I have found {num_courses} {degree_level} {course_word} that match your profile:
{course_catalog}

CRITICAL INSTRUCTIONS - NO HALLUCINATION:
1. Recommend ONLY the {num_courses} course(s) listed above - NEVER suggest courses not in this list
2. If curriculum or detailed information is not provided in the course data, say "specific curriculum details are not available in my current database"
3. For each course, explain WHY it matches their profile using only the information provided
4. Include the course URL for each recommendation
5. Use the EXACT course names as shown above
6. DO NOT invent or hallucinate any course content, subjects, or curriculum details
7. If asked about specific details not in the data, respond with "I don't have that specific information available right now"

ONLY work with the factual information provided. Never create fictional course details.

End by asking: "Would you like me to explain more about {'this course' if num_courses == 1 else 'any of these courses'}, or would you prefer to explore other options?"
"""

    return prompt

def prepare_context_prompt(profile, courses, chat_history):
    """Prepare contextual response focusing on the suggested courses"""
    profile_str = json.dumps(profile, indent=2)
    
    # Get recent user message
    user_messages = [msg for msg in chat_history if msg.get("role") == "user"]
    latest_user_message = user_messages[-1].get("content", "") if user_messages else ""
    
    # Extract the courses that were suggested
    suggested_courses = extract_suggested_courses_from_chat(chat_history)
    
    # Check what the user is asking for
    asking_for_more = check_if_asking_for_more_suggestions(latest_user_message)
    specific_course = identify_course_from_user_query(latest_user_message, suggested_courses)
    
    if asking_for_more:
        # User wants different options - provide NEW courses
        
        # Check if they're asking for a specific domain
        domain_request = extract_domain_request(latest_user_message)
        
        if domain_request:
            # Filter courses by the requested domain
            relevant_courses = filter_courses_by_domain(courses, domain_request, profile.get("degree_level", "Bachelor's Degree"))
        else:
            # Get general recommendations
            relevant_courses, _ = get_smart_course_recommendations(profile, courses, [])
        
        # Skip already suggested courses and get NEW courses only
        new_courses = []
        for course in relevant_courses:
            course_name = course.get('course', '')
            if not any(suggested.lower() in course_name.lower() or course_name.lower() in suggested.lower() 
                      for suggested in suggested_courses):
                new_courses.append(course)
            if len(new_courses) >= 3:  # Maximum 3 new courses
                break
        
        # If we don't have enough new courses, use whatever we have
        if len(new_courses) == 0:
            return """
I apologize, but I don't have any additional courses in our database that are different from what I already recommended. 

The courses I previously suggested appear to be the best matches available for your profile in our current system.

I recommend:
- Checking the university website directly for more course options
- Speaking with admissions counselors for additional guidance
- Considering related fields or different specializations

Is there anything specific about the previously recommended courses you'd like to know more about?
"""
        
        # Build course catalog with available courses only
        course_catalog = ""
        for c in new_courses:
            course_name = c.get('course', '')
            degree_name = c.get('degree', '')
            source_url = c.get('source_url', '')
            subjects = c.get('subjects', [])
            subjects_str = f" (Subjects: {', '.join(subjects)})" if subjects else ""
            
            course_catalog += f"- **{course_name}** from {degree_name}{subjects_str}\n  URL: {source_url}\n\n"

        num_new_courses = len(new_courses)
        course_word = "course" if num_new_courses == 1 else "courses"
        domain_context = f" focusing on {domain_request}" if domain_request else ""
        
        prompt = f"""
You are an expert academic advisor at Jain University.

Student Profile: {profile_str}

CONTEXT: The student has asked for different/alternative course options{domain_context}. Here are {num_new_courses} NEW {course_word} that differ from what was previously suggested:

{course_catalog}

Student's request: {latest_user_message}

CRITICAL INSTRUCTIONS - NO HALLUCINATION:
1. Present ONLY these {num_new_courses} course(s) - NEVER suggest courses not in this list
2. Use **Course Name** format for each course
3. Explain how each course fits their profile using only available information
4. Include course URLs for each
5. DO NOT invent curriculum details, subjects, or course content not provided
6. If specific details aren't available, say "specific details are not available in my current database"

End by asking if they want more details about {'this course' if num_new_courses == 1 else 'any of these courses'} or want to see additional options.
"""
    
    elif specific_course:
        # User asking about one of the suggested courses
        
        # Find the actual course data for this specific course
        course_data = None
        for course in courses:
            if (specific_course.lower() in course.get('course', '').lower() or 
                course.get('course', '').lower() in specific_course.lower()):
                course_data = course
                break
        
        if not course_data:
            return f"""
I apologize, but I don't have detailed information about "{specific_course}" in my current database.

For the most accurate and up-to-date information about this course, I recommend:
- Visiting the official university website
- Contacting the admissions office directly
- Speaking with current students or faculty in that program

Is there anything else about the courses I previously recommended that I can help you with?
"""
        
        # Extract available information from course data
        subjects = course_data.get('subjects', [])
        curriculum = course_data.get('curriculum', [])
        description = course_data.get('description', '')
        source_url = course_data.get('source_url', '')
        
        # Build factual information string
        available_info = f"Course: {course_data.get('course', '')}\n"
        available_info += f"Category: {course_data.get('degree', '')}\n"
        
        if subjects:
            available_info += f"Subjects covered: {', '.join(subjects)}\n"
        
        if curriculum:
            available_info += f"Curriculum elements: {curriculum[:5]}\n"  # Show first 5 items
        
        if description:
            available_info += f"Description: {description}\n"
        
        available_info += f"More information: {source_url}"
        
        prompt = f"""
You are an expert academic advisor at Jain University.

Student Profile: {profile_str}

The student is asking specifically about: **{specific_course}**

AVAILABLE FACTUAL INFORMATION:
{available_info}

Student's question: {latest_user_message}

CRITICAL INSTRUCTIONS - NO HALLUCINATION:
1. Answer ONLY about {specific_course} using the factual information provided above
2. If they ask about curriculum, subjects, career prospects, etc. - use ONLY the information available
3. If specific information is not available in the data, say "I don't have that specific information available right now"
4. DO NOT invent or create any course details, curriculum, or other information
5. Refer them to the course URL for complete and current information
6. Be honest about limitations in your database

Your goal is to provide accurate information about {specific_course} based only on available data.
"""
    
    else:
        # General follow-up about the suggested courses
        suggested_courses_text = "\n".join([f"- {course}" for course in suggested_courses])
        
        prompt = f"""
You are an expert academic advisor at Jain University.

Student Profile: {profile_str}

CONTEXT: You have recommended these courses to the student:
{suggested_courses_text}

Student's current question: {latest_user_message}

CRITICAL INSTRUCTIONS - NO HALLUCINATION:
1. Answer their question relating only to the courses you previously recommended
2. Use ONLY factual information available in your database about these courses
3. If specific details (curriculum, subjects, career prospects) are not in your data, say "I don't have those specific details available right now"
4. DO NOT create or invent any course information
5. Recommend checking the university website or contacting admissions for detailed information
6. Be honest about the limitations of your current database

Stay focused on helping them understand these recommended courses using only available factual information.
"""

    return prompt

def get_recommendation_with_context(profile, courses, chat_history):
    """Get recommendation with full chat context and proper course memory"""
    if not chat_history:
        # Initial recommendation
        prompt = prepare_initial_prompt(profile, courses)
    else:
        # Contextual response
        prompt = prepare_context_prompt(profile, courses, chat_history)
    
    try:
        response = openai.ChatCompletion.create(
            model="mistral-tiny",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            max_tokens=800
        )
        
        return response["choices"][0]["message"]["content"]
    
    except Exception as e:
        return f"I apologize, but I'm having trouble connecting to generate recommendations right now. Error: {str(e)}. Please try again in a moment."

def get_recommendation(profile, courses):
    """Legacy function for backward compatibility"""
    return get_recommendation_with_context(profile, courses, [])