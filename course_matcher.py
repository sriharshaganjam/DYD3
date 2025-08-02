import json
import os
import openai
from dotenv import load_dotenv
import re
from difflib import SequenceMatcher

# Import enhanced embedding system
try:
    from enhanced_embedding_matcher import get_enhanced_recommendations, add_scraped_data_to_embeddings, semantic_search_scraped_content
    ENHANCED_FAISS_AVAILABLE = True
    print("✅ Enhanced FAISS embeddings system loaded successfully!")
except ImportError as e:
    ENHANCED_FAISS_AVAILABLE = False
    print(f"⚠️ Enhanced FAISS not available: {e}. Trying standard FAISS...")
    try:
        from embedding_matcher import get_enhanced_recommendations
        FAISS_AVAILABLE = True
        print("✅ Standard FAISS embeddings system loaded successfully!")
    except ImportError as e2:
        FAISS_AVAILABLE = False
        print(f"⚠️ No FAISS available: {e2}. Using fallback keyword matching.")

load_dotenv()
openai.api_key = os.getenv("MISTRAL_API_KEY")
openai.api_base = "https://api.mistral.ai/v1"

def load_courses(path="courses.json"):
    with open(path, "r") as f:
        return json.load(f)

# Import real-time scraper
try:
    from realtime_scraper import scrape_course_page_realtime, format_scraped_content_for_ai
    REALTIME_SCRAPER_AVAILABLE = True
    print("✅ Real-time scraper loaded successfully!")
except ImportError as e:
    REALTIME_SCRAPER_AVAILABLE = False
    print(f"⚠️ Real-time scraper not available: {e}")

def get_smart_course_recommendations(profile, courses, chat_history=[]):
    if ENHANCED_FAISS_AVAILABLE:
        try:
            recommended_courses, _ = get_enhanced_recommendations(profile, courses, chat_history)
            return recommended_courses
        except Exception as e:
            print(f"⚠️ Enhanced FAISS failed, trying standard FAISS: {e}")
            if FAISS_AVAILABLE:
                try:
                    from embedding_matcher import get_enhanced_recommendations as standard_recommendations
                    recommended_courses, _ = standard_recommendations(profile, courses, chat_history)
                    return recommended_courses
                except Exception as e2:
                    print(f"⚠️ Standard FAISS also failed: {e2}")
                    return filter_and_match_courses_fallback(courses, profile)
            else:
                return filter_and_match_courses_fallback(courses, profile)
    elif FAISS_AVAILABLE:
        try:
            from embedding_matcher import get_enhanced_recommendations as standard_recommendations
            recommended_courses, _ = standard_recommendations(profile, courses, chat_history)
            return recommended_courses
        except Exception as e:
            print(f"⚠️ Standard FAISS failed, using fallback: {e}")
            return filter_and_match_courses_fallback(courses, profile)
    else:
        return filter_and_match_courses_fallback(courses, profile)

def filter_and_match_courses_fallback(courses, profile):
    degree_level = profile.get("degree_level", "Bachelor's Degree")
    interests = [i.lower() for i in profile.get("interests", [])]
    bachelor_keywords = ['bachelor', 'b.com', 'b.sc', 'b.tech', 'b.des']
    master_keywords = ['master', 'm.com', 'm.sc', 'm.tech', 'm.des']

    filtered_by_degree = [
        course for course in courses
        if (degree_level == "Bachelor's Degree" and any(k in course.get('course', '').lower() for k in bachelor_keywords)) or \
           (degree_level == "Master's Degree" and any(k in course.get('course', '').lower() for k in master_keywords))
    ]
    if not interests: return filtered_by_degree[:10]
    matched_courses = [
        course for course in filtered_by_degree
        if any(interest in (course.get('course', '') + ' ' + ' '.join(course.get('subjects', []))).lower() for interest in interests)
    ]
    return matched_courses if matched_courses else filtered_by_degree[:10]

def extract_suggested_courses_from_chat(chat_history):
    suggested_courses = set()
    course_pattern = r'\*\*(.*?)\*\*'
    for message in chat_history:
        if message.get("role") == "assistant":
            content = message.get("content", "")
            matches = re.findall(course_pattern, content)
            for course_name in matches:
                if len(course_name.split()) > 2 and any(term in course_name for term in ["Bachelor", "Master", "B.Com", "B.Des", "M.Des", "B.Sc"]):
                    suggested_courses.add(course_name.strip())
    return list(suggested_courses)

def find_exact_course_in_database(user_query, all_courses):
    """
    🎯 NEW: Find the exact course the user is asking about from courses.json
    This prevents hallucination by only returning courses that actually exist
    """
    if not user_query or not all_courses:
        return None
    
    user_query_lower = user_query.lower()
    
    # Clean user query
    cleaned_query = user_query_lower.strip()
    
    # First pass: Direct name matching
    for course in all_courses:
        course_name = course.get('course', '').lower()
        
        # Clean course name for comparison
        cleaned_course_name = re.sub(r'\s*\|\s*.*', '', course_name)  # Remove "| University" parts
        cleaned_course_name = re.sub(r'\s*at\s+jain.*', '', cleaned_course_name)
        cleaned_course_name = cleaned_course_name.strip()
        
        # Check for direct matches
        if cleaned_course_name in cleaned_query or cleaned_query in cleaned_course_name:
            print(f"🎯 Found exact course match: {course.get('course', '')}")
            return course
    
    # Second pass: Keyword matching with higher threshold
    best_match = None
    best_score = 0
    
    for course in all_courses:
        course_name = course.get('course', '').lower()
        course_words = set(course_name.split())
        query_words = set(cleaned_query.split())
        
        # Calculate overlap
        common_words = course_words.intersection(query_words)
        if len(common_words) >= 2:  # At least 2 words must match
            score = len(common_words) / max(len(course_words), len(query_words))
            if score > best_score:
                best_score = score
                best_match = course
    
    if best_match and best_score > 0.4:  # Higher threshold to avoid false matches
        print(f"🎯 Found course match with score {best_score:.2f}: {best_match.get('course', '')}")
        return best_match
    
    print(f"❌ No exact course found for query: {user_query}")
    return None

def identify_course_from_user_query(user_message, suggested_courses):
    """
    ⭐ UPDATED: This robust logic cleans the course titles before matching them
    against the user's message. This correctly handles conversational filler.
    """
    if not user_message or not suggested_courses:
        return None

    user_message_lower = user_message.lower()

    # Helper function to strip university-specific suffixes and junk words
    def clean_course_name(name):
        name = name.lower()
        # Remove text after a pipe, "at JAIN", "colleges in", etc.
        name = re.sub(r'\|.*', '', name)
        name = re.sub(r'at jain.*', '', name)
        name = re.sub(r'colleges in.*', '', name)
        # Remove common prefixes/suffixes
        name = name.replace("best ", "").replace(" b.com", "bachelor of commerce").strip()
        return name

    for course in suggested_courses:
        # Clean the official course title to get its core name
        cleaned_suggested_course = clean_course_name(course)
        
        # If the core name is found within the user's message, we have a winner.
        if cleaned_suggested_course in user_message_lower:
            print(f"🎯 Found a direct match: '{cleaned_suggested_course}' in user message. Matched course: '{course}'")
            return course

    # If no direct match, return None to trigger the clarification prompt
    return None

def check_if_asking_for_more_suggestions(user_message):
    message_lower = user_message.lower()
    more_suggestions_keywords = ["more courses", "other options", "alternatives", "different", "show me more", "suggest more", "what else", "anything else", "something different"]
    return any(keyword in message_lower for keyword in more_suggestions_keywords)

def check_if_asking_for_course_details(user_message):
    """
    🎯 NEW: Check if user is asking for more details about a specific course
    """
    message_lower = user_message.lower()
    detail_keywords = [
        "subjects", "curriculum", "syllabus", "what is taught", "what subjects",
        "more details", "tell me more", "elaborate", "explain",
        "course content", "modules", "topics covered", "study", "learn"
    ]
    return any(keyword in message_lower for keyword in detail_keywords)

# -------------------- Enhanced Context Management Functions --------------------

def is_greeting(user_input):
    """Detect if the input is a simple greeting"""
    greeting_words = ["hi", "hello", "hey", "good morning", "good afternoon", "good evening", "greetings"]
    input_lower = user_input.lower().strip()
    return (any(word in input_lower for word in greeting_words) and 
            len(user_input.split()) <= 3)

def is_confusion_expression(user_input):
    """Detect expressions of confusion or uncertainty"""
    confusion_phrases = [
        "i don't know", "i dont know", "don't know", "not sure", "i'm not sure", 
        "no idea", "unsure", "i don't understand", "don't understand",
        "confused", "help me", "explain", "i have no idea",
        "no clue", "clueless", "lost", "i'm lost", "help", "hmmm", "im lost", "im not sure"
    ]
    input_lower = user_input.lower().strip()
    return any(phrase in input_lower for phrase in confusion_phrases)

def get_conversation_context(chat_history):
    """Get recent conversation context to understand the flow"""
    if len(chat_history) >= 2:
        # Look at the last few exchanges
        recent_messages = chat_history[-4:]  # Last 4 messages
        recent_text = " ".join([msg.get("content", "") for msg in recent_messages])
        return recent_text
    return None

def build_system_message(profile, response_type="normal", scraped_content=None):
    """Build system message based on response type and user profile"""
    profile_str = json.dumps(profile, indent=2)
    
    base_rules = """CRITICAL ANTI-HALLUCINATION RULES:
1. ONLY recommend courses that are explicitly provided in the course database
2. NEVER make up course names, URLs, or details that aren't in the provided data
3. If you don't have information, say so clearly and suggest checking the official website
4. Always use exact course names as they appear in the database
5. Only provide URLs that are actually in the course data"""
    
    if response_type == "course_details_with_scraped":
        return f"""{base_rules}

You are a knowledgeable academic advisor at Jain University. You have just retrieved detailed, real-time information about a specific course the student asked about.

REAL-TIME COURSE INFORMATION:
{scraped_content}

Student Profile:
{profile_str}

INSTRUCTIONS:
1. Present the scraped course information in a clear, engaging way
2. Highlight how this course aligns with the student's profile and interests
3. Point out specific subjects or aspects that match their background
4. Be enthusiastic about the opportunities this course offers
5. Invite follow-up questions about specific aspects
6. If any information seems incomplete, mention that they can visit the course page for more details"""
    
    elif response_type == "confusion_with_context":
        return f"""{base_rules}

You are a supportive academic advisor at Jain University helping a student who has expressed confusion or uncertainty. The student needs encouragement and gentle guidance.

ADDITIONAL RULES:
1. The student has indicated they don't know something or are confused - this is NORMAL and part of the decision-making process
2. Provide hints, clues, and encouragement to guide them toward understanding their options
3. Break down complex course information into smaller, manageable pieces
4. Use the available course data to provide specific guidance and examples
5. Be patient, supportive, and encouraging
6. Ask guiding questions to help them think through their interests and goals
7. Never make them feel bad for not knowing - confusion about career choices is natural!
8. Help them explore their interests and strengths to find the right course

Student Profile:
{profile_str}

The student is expressing uncertainty about course selection - help them explore their options step by step."""
    
    elif response_type == "greeting":
        return f"""{base_rules}

You are a friendly, warm, and encouraging academic advisor at Jain University. You're meeting a prospective student for the first time.

ADDITIONAL RULES:
1. Provide a warm, welcoming greeting
2. Briefly introduce yourself as their academic advisor
3. Show enthusiasm about helping them find the right course
4. Ask an engaging question to start understanding their interests and goals
5. Keep the tone conversational and supportive
6. Don't overwhelm them with too much information initially

Student Profile:
{profile_str}

This is the beginning of your conversation with this student - make them feel welcome and excited about exploring their academic options."""
    
    else:  # normal response
        return f"""{base_rules}

You are a friendly, patient, and encouraging academic advisor at Jain University. Your goal is to help students feel confident and informed about their course choices.

ADDITIONAL RULES:
1. Use the student's profile and conversation history to provide personalized advice
2. Be supportive and conversational, not robotic
3. Recommend courses based on their interests, strengths, and degree level
4. Provide clear explanations for why certain courses might be good fits
5. Always include relevant URLs when discussing specific courses
6. Ask follow-up questions to better understand their needs
7. Maintain context from previous parts of the conversation

Student Profile:
{profile_str}

Continue the conversation naturally, building on what has been discussed previously."""

def create_course_catalog_string(courses):
    """
    🎯 NEW: Create a properly formatted course catalog string that prevents hallucination
    """
    if not courses:
        return "No matching courses found in our database."
    
    course_catalog_str = ""
    for course in courses:
        course_name = course.get('course', 'Unknown Course')
        course_url = course.get('source_url', 'URL not available')
        course_subjects = course.get('subjects', [])
        
        course_catalog_str += f"- **{course_name}**\n"
        if course_subjects:
            course_catalog_str += f"  Key Subjects: {', '.join(course_subjects[:5])}\n"
        course_catalog_str += f"  URL: {course_url}\n\n"
    
    return course_catalog_str

def prepare_initial_prompt_with_context(profile, all_courses):
    """Enhanced initial prompt that sets up proper conversational context"""
    profile_str = json.dumps(profile, indent=2)
    relevant_courses = get_smart_course_recommendations(profile, all_courses)[:3]
    
    if not relevant_courses:
        return "I'm sorry, but I couldn't find any courses that perfectly match your unique profile in our database at the moment. It might be helpful to check the Jain University official website directly for the most current offerings."

    course_catalog_str = create_course_catalog_string(relevant_courses)

    return f"""
    Here is the student's profile:
    {profile_str}

    Here are the top 3 courses from our database that seem like a great fit:
    {course_catalog_str}

    INSTRUCTIONS:
    1. Greet the student warmly and introduce yourself as their academic advisor
    2. Recommend ONLY the courses listed above. Use the exact course names in bold (`**Course Name**`)
    3. For each course, explain WHY it's a good match for their profile (interests, strengths)
    4. Include the course URL for each recommendation
    5. Conclude by asking: "I'd be happy to tell you more about any of these programs. Do any of them catch your eye, or would you like to explore some other possibilities?"
    """

def prepare_enhanced_context_prompt(profile, all_courses, chat_history):
    """Enhanced context-aware prompt preparation with real-time scraping support"""
    if not chat_history:
        return prepare_initial_prompt_with_context(profile, all_courses)
    
    latest_user_message = chat_history[-1].get("content", "")
    suggested_courses_from_history = extract_suggested_courses_from_chat(chat_history)
    conversation_context = get_conversation_context(chat_history)
    
    # Check different types of input
    is_greeting_input = is_greeting(latest_user_message)
    is_confusion_input = is_confusion_expression(latest_user_message)
    is_asking_for_details = check_if_asking_for_course_details(latest_user_message)
    specific_course_requested = identify_course_from_user_query(latest_user_message, suggested_courses_from_history)
    asking_for_more = check_if_asking_for_more_suggestions(latest_user_message)

    # 🎯 NEW: Handle requests for course details with real-time scraping
    if is_asking_for_details or specific_course_requested:
        # Try to find the exact course the user is asking about
        target_course = None
        
        if specific_course_requested:
            # Find the course from suggested courses
            target_course = next((c for c in all_courses if c.get('course', '').lower() == specific_course_requested.lower()), None)
        else:
            # Try to identify course from the user's question
            target_course = find_exact_course_in_database(latest_user_message, all_courses)
        
        if target_course and REALTIME_SCRAPER_AVAILABLE:
            # Scrape the course page for detailed information
            course_url = target_course.get('source_url', '')
            if course_url:
                print(f"🔍 Scraping detailed information for: {target_course.get('course', '')}")
                scraped_data = scrape_course_page_realtime(course_url)
                
                if scraped_data:
                    # 🎯 NEW: Add scraped data to FAISS embeddings for future semantic search
                    if ENHANCED_FAISS_AVAILABLE:
                        embedding_success = add_scraped_data_to_embeddings(course_url, scraped_data)
                        if embedding_success:
                            print("✅ Scraped data added to FAISS embeddings for semantic search")
                        else:
                            print("⚠️ Failed to add scraped data to embeddings")
                    
                    formatted_content = format_scraped_content_for_ai(scraped_data)
                    
                    return f"""
                    The student is asking for detailed information about **{target_course.get('course', '')}**.
                    
                    You have just retrieved comprehensive, real-time information about this course.
                    
                    REAL-TIME SCRAPED CONTENT:
                    {formatted_content}
                    
                    CONVERSATION CONTEXT: {conversation_context}
                    
                    INSTRUCTIONS:
                    1. Present this detailed information in an engaging, well-organized way
                    2. Highlight how this course aligns with their profile and interests
                    3. Point out specific subjects, career prospects, or features that match their background
                    4. Be enthusiastic about the opportunities this course offers
                    5. Encourage them to ask follow-up questions about specific aspects
                    6. Let them know this information is current and comprehensive
                    """

        # Fallback if scraping fails or course not found
        if target_course:
            available_info = f"""Course: **{target_course.get('course', '')}**
Description: {target_course.get('description', 'A detailed description is not available.')}
Key Subjects: {', '.join(target_course.get('subjects', ['N/A']))}
URL: {target_course.get('source_url', 'Not available.')}"""
            
            return f"""
            The student is asking about **{target_course.get('course', '')}**.
            
            Conversation context: {conversation_context}
            
            AVAILABLE INFORMATION FROM DATABASE:
            {available_info}

            INSTRUCTIONS:
            1. Acknowledge their interest and provide the available information
            2. If detailed curriculum information isn't available in our database, let them know we're working to get more details
            3. Always provide the URL for complete details
            4. Ask follow-up questions about what specifically interests them
            5. Suggest how this course aligns with their profile and goals
            6. Keep the conversation engaging by asking about their next steps
            """
        else:
            return f"""
            The student is asking for course details, but I cannot identify which specific course from our database they're referring to.
            
            User's message: "{latest_user_message}"
            Previously suggested courses: {', '.join(suggested_courses_from_history)}
            
            INSTRUCTIONS:
            1. Politely ask them to clarify which specific course they'd like to know more about
            2. List the courses that have been discussed so far to help them choose
            3. Mention that you can provide detailed information once they specify the course
            4. Keep the tone helpful and encouraging
            """

    # Handle greetings in conversation
    if is_greeting_input and len(chat_history) <= 2:
        return f"""
        The student has just greeted you. This might be their first interaction or they're re-engaging.
        
        Previous conversation context: {conversation_context or "This appears to be a new conversation"}
        
        INSTRUCTIONS:
        1. Respond warmly to their greeting
        2. If this seems like a continuation, acknowledge the previous discussion
        3. If this seems new, introduce yourself and ask about their interests
        4. Keep the response brief and welcoming
        5. Guide them toward discussing their academic goals
        """

    # Handle confusion with educational context
    if is_confusion_input:
        context_courses = get_smart_course_recommendations(profile, all_courses)[:5]
        course_catalog_str = create_course_catalog_string(context_courses)
        
        return f"""
        The student is expressing confusion or uncertainty about their course selection.
        
        Conversation context: {conversation_context}
        Previously suggested courses: {', '.join(suggested_courses_from_history)}
        
        Available course options that match their profile:
        {course_catalog_str}
        
        INSTRUCTIONS:
        1. Acknowledge their uncertainty with empathy - this is normal!
        2. Help them break down their decision-making process
        3. Ask guiding questions about their interests and career goals
        4. Provide encouragement and support
        5. Offer to explore specific aspects of courses they might be interested in
        6. Use their profile information to suggest areas they might want to consider
        """

    # Handle requests for more suggestions
    if asking_for_more:
        all_relevant_courses = get_smart_course_recommendations(profile, all_courses)
        suggested_names_lower = {c.lower() for c in suggested_courses_from_history}
        new_courses = [c for c in all_relevant_courses if c.get('course', '').lower() not in suggested_names_lower][:3]

        if not new_courses:
            return f"""
            The student wants to see more options, but we've already shown the best matches.
            
            Conversation context: {conversation_context}
            Previously suggested: {', '.join(suggested_courses_from_history)}
            
            INSTRUCTIONS:
            1. Explain that the previously suggested courses are the strongest matches
            2. Offer to dive deeper into any of the already suggested courses
            3. Ask if they'd like to explore slightly different fields
            4. Suggest refining their interests or goals to find other options
            5. Keep the tone encouraging and helpful
            """

        course_catalog_str = create_course_catalog_string(new_courses)
        return f"""
        The student wants to explore more course options.
        
        Conversation context: {conversation_context}
        Previously suggested: {', '.join(suggested_courses_from_history)}
        
        NEW COURSE OPTIONS FROM OUR DATABASE:
        {course_catalog_str}

        INSTRUCTIONS:
        1. Enthusiastically present these new alternatives
        2. Explain why these might also be good fits based on their profile
        3. Compare or contrast with previously discussed options if relevant
        4. Ask which aspects of these new options appeal to them
        5. Keep building on the conversation naturally
        """
    # 🎯 NEW: Check if this is a general question that could benefit from semantic search
    if not is_greeting_input and not is_confusion_input and not asking_for_more and not specific_course_requested:
        # Try to use semantic search if enhanced FAISS is available
        if ENHANCED_FAISS_AVAILABLE:
            try:
                semantic_results = semantic_search_scraped_content(latest_user_message, top_k=3)
                if semantic_results:
                    # Format results for AI consumption
                    search_results = []
                    for result in semantic_results:
                        course_name = result['course_name']
                        enhanced_data = result['enhanced_data']
                        similarity = result['similarity']
                        
                        search_results.append(f"""
Course: **{course_name}** (Relevance: {similarity:.2f})
Subjects: {', '.join(enhanced_data.get('subjects', [])[:5])}
Curriculum: {' '.join(enhanced_data.get('curriculum', [])[:2])[:200]}...
Career Prospects: {' '.join(enhanced_data.get('career_prospects', [])[:1])[:150]}...
""")
                    
                    semantic_results_text = f"""
SEMANTIC SEARCH RESULTS from previously scraped course data:

{chr(10).join(search_results)}

These results are based on detailed course information that was previously scraped and embedded for semantic search.
"""
                    
                    return f"""
            The student asked: "{latest_user_message}"
            
            I found relevant information from previously scraped course details:
            
            {semantic_results_text}
            
            Conversation context: {conversation_context}
            
            INSTRUCTIONS:
            1. Use the semantic search results to provide a comprehensive answer
            2. Reference specific courses and their detailed information
            3. Connect the findings to the student's profile and interests
            4. Offer to get more detailed information about any specific course mentioned
            5. Ask follow-up questions to better understand their needs
            """
            except Exception as e:
                print(f"❌ Error in semantic search: {e}")
                # Continue to general conversation handling

    # Handle general conversation continuation
    return f"""
    The student's message: "{latest_user_message}"
    
    Conversation context: {conversation_context}
    Previously suggested courses: {', '.join(suggested_courses_from_history)}
    
    INSTRUCTIONS:
    1. Respond naturally to their message, maintaining conversational flow
    2. Use the conversation context to provide relevant, personalized advice
    3. If their message is unclear, ask for clarification while keeping them engaged
    4. Reference previous parts of the conversation to show you're listening
    5. Guide them toward helpful next steps in their course selection process
    6. Keep the tone supportive and encouraging throughout
    """

def test_api_connection():
    """Test basic API connectivity with enhanced debugging"""
    try:
        print("🧪 Testing Mistral API connection...")
        print(f"🔍 API Key present: {'Yes' if openai.api_key else 'No'}")
        print(f"🔍 API Key starts with: {openai.api_key[:15] if openai.api_key else 'None'}...")
        print(f"🔍 API Base: {openai.api_base}")
        
        test_response = openai.ChatCompletion.create(
            model="mistral-medium",
            messages=[{"role": "user", "content": "Hello, just testing the connection."}],
            temperature=0.1,
            max_tokens=50
        )
        print("✅ API connection successful!")
        print(f"✅ Response: {test_response['choices'][0]['message']['content']}")
        return True
    except Exception as e:
        print(f"❌ API connection failed: {e}")
        print(f"❌ Error type: {type(e).__name__}")
        
        # Try different models if mistral-medium fails
        backup_models = ["mistral-small", "mistral-tiny", "open-mistral-7b"]
        for model in backup_models:
            try:
                print(f"🔄 Trying backup model: {model}")
                backup_response = openai.ChatCompletion.create(
                    model=model,
                    messages=[{"role": "user", "content": "Test"}],
                    temperature=0.1,
                    max_tokens=10
                )
                print(f"✅ Backup model {model} works!")
                return True
            except Exception as backup_error:
                print(f"❌ {model} also failed: {backup_error}")
                continue
        
        return False

def get_recommendation_with_enhanced_context(profile, courses, chat_history):
    """Enhanced recommendation function with full context retention and real-time scraping"""
    
    # Debug: Print inputs to understand what we're working with
    print(f"🔍 DEBUG - Profile keys: {list(profile.keys()) if profile else 'None'}")
    print(f"🔍 DEBUG - Chat history length: {len(chat_history) if chat_history else 0}")
    print(f"🔍 DEBUG - Available courses: {len(courses) if courses else 0}")
    print(f"🔍 DEBUG - Real-time scraper available: {REALTIME_SCRAPER_AVAILABLE}")
    
    # Test API first
    if not test_api_connection():
        print("❌ API test failed, returning fallback message")
        return "I'm experiencing technical difficulties connecting to our AI service. Please check your API key and try again. In the meantime, feel free to browse the courses available on the Jain University website."
    
    # Determine response type and check for scraping needs
    response_type = "normal"
    scraped_content = None
    
    if chat_history:
        latest_message = chat_history[-1].get("content", "")
        print(f"🔍 DEBUG - Latest message: {latest_message[:100]}...")
        
        if is_greeting(latest_message) and len(chat_history) <= 2:
            response_type = "greeting"
        elif is_confusion_expression(latest_message):
            response_type = "confusion_with_context"
        elif check_if_asking_for_course_details(latest_message) and REALTIME_SCRAPER_AVAILABLE:
            # Check if we can identify and scrape a specific course
            target_course = find_exact_course_in_database(latest_message, courses)
            if target_course and target_course.get('source_url'):
                print(f"🔍 Attempting real-time scraping for: {target_course.get('course')}")
                scraped_data = scrape_course_page_realtime(target_course.get('source_url'))
                if scraped_data:
                    scraped_content = format_scraped_content_for_ai(scraped_data)
                    response_type = "course_details_with_scraped"
                    print("✅ Real-time scraping successful!")
    
    print(f"🔍 DEBUG - Response type: {response_type}")
    
    # Build the system message
    system_message = build_system_message(profile, response_type, scraped_content)
    print(f"🔍 DEBUG - System message length: {len(system_message)}")
    
    # Prepare the context-aware prompt
    context_prompt = prepare_enhanced_context_prompt(profile, courses, chat_history)
    print(f"🔍 DEBUG - Context prompt length: {len(context_prompt)}")
    
    # Build the complete message history for the AI
    messages = [{"role": "system", "content": system_message}]
    
    # Add conversation history (maintaining context)
    for msg in chat_history[:-1]:  # All messages except the latest one
        messages.append({"role": msg["role"], "content": msg["content"]})
    
    # Add the context-aware prompt for the current response
    if chat_history:
        messages.append({"role": "user", "content": context_prompt})
    else:
        # For initial conversation, use the context prompt directly
        messages = [{"role": "system", "content": system_message + "\n\n" + context_prompt}]
    
    print(f"🔍 DEBUG - Total messages to send: {len(messages)}")
    
    # Try multiple models in order of preference
    models_to_try = ["mistral-medium", "mistral-small", "mistral-tiny", "open-mistral-7b"]
    
    for model in models_to_try:
        try:
            print(f"🔍 DEBUG - Attempting API call with model: {model}")
            response = openai.ChatCompletion.create(
                model=model,
                messages=messages,
                temperature=0.6,
                max_tokens=800
            )
            print(f"✅ API call successful with model: {model}")
            return response["choices"][0]["message"]["content"]
            
        except Exception as e:
            print(f"❌ Model {model} failed: {e}")
            print(f"❌ Error type: {type(e).__name__}")
            continue
    
    # If all models fail, try the original fallback approach
    try:
        print("🔄 Attempting fallback with simpler prompt...")
        fallback_prompt = prepare_initial_prompt(profile, courses)
        simple_response = openai.ChatCompletion.create(
            model="mistral-medium",
            messages=[{"role": "user", "content": fallback_prompt}],
            temperature=0.6,
            max_tokens=800
        )
        print("✅ Fallback successful!")
        return simple_response["choices"][0]["message"]["content"]
    except Exception as fallback_error:
        print(f"❌ FALLBACK ALSO FAILED: {fallback_error}")
        return "I'm sorry, but I'm having technical difficulties at the moment. Please check that your MISTRAL_API_KEY is correctly set in your .env file and try again. You can also visit the Jain University website directly to explore course options."

# Legacy function for the initial prompt (keeping for fallback)
def prepare_initial_prompt(profile, all_courses):
    """Legacy function for basic course recommendations"""
    relevant_courses = get_smart_course_recommendations(profile, all_courses)[:3]
    if not relevant_courses:
        return "I'm sorry, but I couldn't find any courses that perfectly match your unique profile in our database at the moment."

    course_catalog_str = create_course_catalog_string(relevant_courses)

    return f"""You are a friendly academic advisor at Jain University. 

Based on the student's profile, here are 3 recommended courses:
{course_catalog_str}

Please recommend these courses warmly and explain why they're good matches. Include the URLs and ask which interests them most."""

# Maintain backward compatibility with the original function name
def get_recommendation_with_context(profile, courses, chat_history):
    """Wrapper function to maintain backward compatibility"""
    return get_recommendation_with_enhanced_context(profile, courses, chat_history)